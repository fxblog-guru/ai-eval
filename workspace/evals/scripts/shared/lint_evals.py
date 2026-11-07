#!/usr/bin/env python3
"""Enforce the mechanical half of EVAL-CONTRACTS.md.

Usage:
    python3 scripts/shared/lint_evals.py [--root .evals] [--json] [--quiet]

Exit codes: 0 = clean (warnings allowed), 1 = at least one error, 2 = the root is not an eval root.

The rules that cannot be checked mechanically -- whether a failure mode is at the right
granularity, whether a judge prompt states real failure conditions, whether a policy line is
testable -- are enforced by the skills and by review. This file catches the rest, which is the
part that rots silently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from root import resolve_root, root_arg_help  # noqa: E402
import calibrate  # noqa: E402

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FM_ID = re.compile(r"^FM-\d{3,}$")
CASE_ID = re.compile(r"^EV-(TASK|AGENT|RAG|SAFE|NFR|CONTRACT)-\d{3,}$")
DS_ID = re.compile(r"^DS-[a-z0-9]+(-[a-z0-9]+)*-v\d+$")
JDG_ID = re.compile(r"^JDG-[a-z0-9]+(-[a-z0-9]+)*-v\d+$")
RT_ID = re.compile(r"^RT-(LLM|ASI)\d{2}-\d{3,}$")
TRACE_REF = re.compile(r"TB-\d{4}-\d{2}-\d{2}-\d{3,}\s*/\s*\S+")

SYSTEM_CARD_HEADINGS = ["## System", "## Users", "## Surface", "## Model", "## Tools",
                        "## Hard policies", "## Risk tier", "## Known unknowns"]
FM_HEADINGS = ["## Statement", "## Evidence", "## Frequency", "## Severity",
               "## Detector", "## Status"]
VALIDATION_HEADINGS = ["## Judge", "## Labels", "## Confusion", "## Rates",
                       "## Disagreements", "## Correction", "## Verdict"]
CASE_KEYS = {"case_id", "input", "fm", "expect", "origin"}
# L1 retrieval datasets carry a different shape (EVAL-CONTRACTS 7.3): a query and the chunk ids
# that should come back, with no FM or evaluator binding.
RETRIEVAL_KEYS = {"case_id", "input", "relevant", "origin"}
RETRIEVAL_DS = re.compile(r"-retrieval-v\d+$")
RAG_CASE_ID = re.compile(r"^EV-RAG-\d{3,}$")
FM_STATUS = {"open", "mitigated", "retired"}
SEVERITY = {"blocking", "major", "minor"}
ORIGIN = {"trace", "synthetic", "handwritten"}
# A gate key must name a confidence-interval lower bound. See EVAL-CONTRACTS section 8.3.
CI_GATE = re.compile(r"_ci_lower$|^regression_margin$|^flaky_rate_max$|^unresolved_")
# EVAL-PROFILE §Risk tier. The template's `low | medium | high` placeholder does not match, so an
# unfilled profile makes no layer mandatory yet.
PROFILE_TIER = re.compile(r"^- \*\*Tier:\*\*\s*`(low|medium|high)`", re.M)
LAYER_CODE = re.compile(r"\bL[0-6]\b")


@dataclass
class Finding:
    code: str
    severity: str  # error | warning
    file: str
    message: str

    def __str__(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "warning"
        return f"{mark} {self.code}  {self.file}\n         {self.message}"


class Linter:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[Finding] = []

    def err(self, code: str, file: Path | str, message: str) -> None:
        self.findings.append(Finding(code, "error", self._rel(file), message))

    def warn(self, code: str, file: Path | str, message: str) -> None:
        self.findings.append(Finding(code, "warning", self._rel(file), message))

    def _rel(self, file: Path | str) -> str:
        try:
            return str(Path(file).relative_to(self.root.parent)).replace("\\", "/")
        except (ValueError, TypeError):
            return str(file).replace("\\", "/")

    # ------------------------------------------------------------------ entry

    def run(self) -> list[Finding]:
        self.check_system_card()
        self.check_layers()
        fms = self.check_taxonomy()
        datasets = self.check_datasets(fms)
        judges = self.check_judges()
        self.check_suites(datasets, judges)
        self.check_audit(datasets, judges)
        self.check_redteam()
        return self.findings

    # ------------------------------------------------------------------ system card

    def check_system_card(self) -> None:
        card = self.root / "system-card.md"
        if not card.exists():
            self.err("E001", card, "no system card: nothing states what is being evaluated")
            return
        text = card.read_text(encoding="utf-8")
        for heading in SYSTEM_CARD_HEADINGS:
            if heading not in text:
                self.err("E001", card, f"missing required heading {heading!r} (EVAL-CONTRACTS 3)")
        policies = _section(text, "## Hard policies")
        if policies and not policies.strip():
            self.err("E001", card, "## Hard policies is empty: the safety suite would test nothing")

    # ------------------------------------------------------------------ layers (§8.1)

    def check_layers(self) -> None:
        """E024: every layer EVAL-PROFILE §Risk tier makes mandatory is enabled in §Layers.

        The tier-to-layers mapping is read from the profile's own §Risk tier table, so a team that
        tightens it is held to its own table. No profile, or a tier still at its placeholder, means
        nothing is mandatory yet.
        """
        project = self.root.resolve().parent
        profile = next((p for p in (project / ".claude" / "EVAL-PROFILE.md", project / "EVAL-PROFILE.md")
                        if p.is_file()), None)
        if profile is None:
            return
        text = profile.read_text(encoding="utf-8")
        m = PROFILE_TIER.search(text)
        if not m:
            return
        tier, where = m.group(1), profile.relative_to(project).as_posix()
        mandatory = _mandatory_layers(_section(text, "## Risk tier"), tier)
        if mandatory is None:
            self.err("E024", where,
                     f"risk tier {tier!r} has no row with Mandatory layers in the §Risk tier table: "
                     "which layers must run cannot be decided (EVAL-CONTRACTS 8.1)")
            return
        enabled = _enabled_layers(_section(text, "## Layers"))
        for layer in mandatory:
            if layer not in enabled:
                self.err("E024", where,
                         f"{layer} is mandatory for risk tier {tier!r} but §Layers does not enable "
                         "it: the pipeline would skip it and the system would look evaluated. "
                         "Enable it, or change the tier (EVAL-CONTRACTS 8.1)")

    # ------------------------------------------------------------------ taxonomy

    def check_taxonomy(self) -> dict[str, dict]:
        """Returns {fm_id: {status, file}} for every FM file found."""
        tax = self.root / "taxonomy"
        fms: dict[str, dict] = {}
        if not tax.is_dir():
            return fms

        index = tax / "INDEX.md"
        registered: set[str] = set()
        if index.exists():
            # Ids are read from the register's TABLE ROWS only. Prose in the same file explains
            # the rules and names ids as examples; those are not registrations.
            for line in index.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("|"):
                    cell = line.strip().strip("|").split("|")[0].strip().strip("`")
                    if FM_ID.match(cell):
                        registered.add(cell)
        else:
            self.err("E004", index, "no INDEX.md: FM ids must be minted in one place (EVAL-CONTRACTS 6)")

        for path in sorted(tax.glob("FM-*.md")):
            fm_id = path.name.split("-", 2)[0] + "-" + path.name.split("-")[1]
            if not FM_ID.match(fm_id):
                self.err("E015", path, f"{fm_id!r} is not a valid FM id (FM-NNN)")
                continue
            if fm_id in fms:
                self.err("E005", path, f"{fm_id} is defined more than once; ids are never reused")
                continue

            text = path.read_text(encoding="utf-8")
            for heading in FM_HEADINGS:
                if heading not in text:
                    self.err("E002", path, f"missing required heading {heading!r} (EVAL-CONTRACTS 6)")

            evidence = _section(text, "## Evidence")
            refs = TRACE_REF.findall(evidence or "")
            if len(refs) < 3:
                self.err(
                    "E003", path,
                    f"{len(refs)} trace ref(s) under ## Evidence, need 3. "
                    "Under 3 observations it is a hypothesis, not a failure mode.")

            status = (_section(text, "## Status") or "").strip().split("\n")[0].strip()
            if status and status not in FM_STATUS:
                self.err("E018", path, f"## Status {status!r} not in {sorted(FM_STATUS)}")

            sev = (_section(text, "## Severity") or "").strip().split()[:1]
            if sev and sev[0] not in SEVERITY:
                self.err("E018", path, f"## Severity {sev[0]!r} not in {sorted(SEVERITY)}")

            if fm_id not in registered:
                self.err("E004", path, f"{fm_id} is not registered in taxonomy/INDEX.md")

            fms[fm_id] = {"status": status or "open", "file": path}

        for fm_id in sorted(registered - set(fms)):
            self.err("E004", index, f"{fm_id} is in INDEX.md but has no FM file")

        return fms

    # ------------------------------------------------------------------ datasets

    def check_datasets(self, fms: dict[str, dict]) -> dict[str, dict]:
        ds_dir = self.root / "datasets"
        datasets: dict[str, dict] = {}
        covered: set[str] = set()
        if not ds_dir.is_dir():
            return datasets

        for path in sorted(ds_dir.glob("DS-*.jsonl")):
            ds_id = path.stem
            if not DS_ID.match(ds_id):
                self.err("E015", path, f"{ds_id!r} is not a valid dataset id (DS-<slug>-vN)")
                continue

            is_retrieval = bool(RETRIEVAL_DS.search(ds_id))
            required = RETRIEVAL_KEYS if is_retrieval else CASE_KEYS
            rows, origins, ids, absent = [], [], set(), 0
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    self.err("E006", path, f"line {lineno}: not valid JSON ({exc.msg})")
                    continue

                missing = required - set(row)
                if missing:
                    self.err("E006", path,
                             f"line {lineno}: missing required key(s) {sorted(missing)} (EVAL-CONTRACTS 7)")
                    continue

                cid = row["case_id"]
                expected_id = RAG_CASE_ID if is_retrieval else CASE_ID
                if not expected_id.match(str(cid)):
                    self.err("E007", path, f"line {lineno}: case_id {cid!r} does not match "
                                           + ("EV-RAG-<NNN>" if is_retrieval else "EV-<SUITE>-<NNN>"))
                if cid in ids:
                    self.err("E007", path, f"line {lineno}: case_id {cid!r} is duplicated")
                ids.add(cid)

                origin = row.get("origin")
                if origin not in ORIGIN:
                    self.err("E018", path,
                             f"line {lineno}: origin {origin!r} not in {sorted(ORIGIN)}")
                origins.append(origin)

                if origin == "trace" and not row.get("source"):
                    self.err("E006", path,
                             f"line {lineno}: origin=trace requires `source` naming the trace")

                if is_retrieval:
                    if row.get("known_absent"):
                        absent += 1
                    elif not row.get("relevant"):
                        self.err("E006", path,
                                 f"line {lineno}: `relevant` is empty but known_absent is not set. "
                                 "A query with no answer in the corpus must say so explicitly.")
                    rows.append(row)
                    continue

                for fm in row.get("fm") or []:
                    covered.add(fm)
                    if fms and fm not in fms:
                        self.err("E004", path,
                                 f"line {lineno}: references unknown failure mode {fm!r}")
                rows.append(row)

            datasets[ds_id] = {"path": path, "n": len(rows), "rows": rows}

            if is_retrieval and rows:
                absent_share = absent / len(rows)
                if absent_share < 0.10:
                    self.warn("W007", path,
                              f"known_absent share is {absent_share:.0%}, below 10% (EVAL-CONTRACTS 7.3): "
                              "a retriever is also judged on what it does when the answer is not "
                              "in the corpus")
            if rows and not is_retrieval:
                share = origins.count("trace") / len(rows)
                if share < 0.30:
                    self.warn("W001", path,
                              f"origin=trace share is {share:.0%}, below 30% (EVAL-CONTRACTS 7.2): "
                              "a dataset made of synthetic cases tests an imagined product")
            meta = path.with_suffix(".meta.md")
            if not meta.exists():
                self.warn("W005", path, "no .meta.md: provenance and sampling weights unrecorded")

        for fm_id, info in sorted(fms.items()):
            if info["status"] == "open" and fm_id not in covered:
                self.err("E008", info["file"],
                         f"{fm_id} is open but no dataset case probes it: the suite will report "
                         "this failure mode as fine, permanently")

        return datasets

    # ------------------------------------------------------------------ judges

    def check_judges(self) -> dict[str, dict]:
        """Returns {judge_id: {verdict, file}}."""
        jdir = self.root / "judges"
        judges: dict[str, dict] = {}
        if not jdir.is_dir():
            return judges

        for path in sorted(jdir.glob("JDG-*.md")):
            jid = path.stem
            if not JDG_ID.match(jid):
                self.err("E015", path, f"{jid!r} is not a valid judge id (JDG-<slug>-vN)")
                continue
            slug = jid[len("JDG-"):jid.rindex("-v")]
            vpath = jdir / slug / "validation.md"
            if not vpath.exists():
                judges[jid] = {"verdict": None, "file": path, "validation": vpath,
                               "model": _judge_model(_section(path.read_text(encoding="utf-8"), "## Judge"))}
                continue

            vtext = vpath.read_text(encoding="utf-8")
            for heading in VALIDATION_HEADINGS:
                if heading not in vtext:
                    self.err("E014", vpath,
                             f"missing required heading {heading!r} (EVAL-CONTRACTS 5.3)")
            verdict_txt = (_section(vtext, "## Verdict") or "").strip()
            verdict = "VALIDATED" if re.match(r"^VALIDATED\b", verdict_txt) else (
                "UNVALIDATED" if "UNVALIDATED" in verdict_txt else None)
            if verdict is None:
                self.err("E018", vpath,
                         "## Verdict must be VALIDATED or UNVALIDATED (EVAL-CONTRACTS 14)")
            dis = (_section(vtext, "## Disagreements") or "").strip()
            if verdict and not dis:
                self.err("E014", vpath,
                         "## Disagreements is empty: rates say whether the judge is good, "
                         "the disagreements are the only thing that says how to fix it")
            judges[jid] = {"verdict": verdict, "file": path, "validation": vpath,
                           "model": _judge_model(_section(path.read_text(encoding="utf-8"), "## Judge")),
                           "validated_model": _validated_model(vtext)}

            self._check_labels(jdir / slug / "labels", vpath)

        return judges

    def _check_labels(self, ldir: Path, vpath: Path) -> None:
        if not ldir.is_dir():
            self.err("E014", vpath, f"no labels directory at {self._rel(ldir)}")
            return
        for split in ("dev", "test"):
            lpath = ldir / f"{split}.jsonl"
            if not lpath.exists():
                self.err("E014", lpath, f"missing {split}.jsonl (EVAL-CONTRACTS 5.2)")
                continue
            passes = fails = 0
            for line in lpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    self.err("E006", lpath, "not valid JSON on at least one line")
                    break
                if row.get("annotator") == "ANN-AI" and split == "test":
                    self.err("E014", lpath,
                             "ANN-AI rows are unconfirmed suggestions and may not sit in test")
                if row.get("label") == "pass":
                    passes += 1
                elif row.get("label") == "fail":
                    fails += 1
            if passes < 30 or fails < 30:
                self.err("E014", lpath,
                         f"{split} split has {passes} Pass / {fails} Fail, needs 30 of each "
                         "(EVAL-CONTRACTS 5.2): a TPR from fewer is a number, not evidence")

    # ------------------------------------------------------------------ suites

    def check_suites(self, datasets: dict[str, dict], judges: dict[str, dict]) -> None:
        sdir = self.root / "suites"
        if not sdir.is_dir():
            return
        for path in sorted(sdir.glob("*.yaml")):
            suite = _parse_suite(path.read_text(encoding="utf-8"))
            name = suite.get("suite")
            if not name or not KEBAB.match(str(name)):
                self.err("E015", path, f"suite name {name!r} must be lowercase-kebab")

            gates = suite.get("gates") or {}
            gated = bool(gates)

            model = str(suite.get("model") or "")
            if not model or model.endswith("latest") or "<" in model:
                self.err("E011", path,
                         "model id is unpinned: a run whose model cannot be identified is "
                         "unattributable and comparable to nothing (EVAL-CONTRACTS 8.2)")
            if "temperature" not in suite:
                self.warn("W006", path, "temperature not pinned in the suite")

            for key in gates:
                if not CI_GATE.search(str(key)):
                    self.err("E012", path,
                             f"gate {key!r} does not name a confidence-interval lower bound; "
                             "gating on a point estimate makes the outcome partly luck "
                             "(EVAL-CONTRACTS 8.3)")

            ds_id = suite.get("dataset")
            if ds_id and ds_id not in datasets:
                self.err("E016", path, f"dataset {ds_id!r} is referenced but does not exist")
            elif ds_id and gated:
                n = datasets[ds_id]["n"]
                if n < 30:
                    self.err("E013", path,
                             f"gated suite runs on {n} cases: below 30 a gate cannot tell a "
                             "regression from sampling noise")
                elif n < 100:
                    self.warn("W002", path, f"gated suite runs on {n} cases; 100 is the minimum "
                                            "for a stable gate")

            for ev in suite.get("evaluators") or []:
                if not str(ev).startswith("judge:"):
                    continue
                jid = str(ev).split(":", 1)[1]
                info = judges.get(jid)
                if info is None:
                    self.err("E009", path, f"references unknown judge {jid!r}")
                elif info["verdict"] is None and gated:
                    self.err("E009", path,
                             f"gates on {jid}, which has no validation.md: every number this "
                             "gate produced is unattributable (EVAL-CONTRACTS 5.4)")
                elif info["verdict"] == "UNVALIDATED" and gated:
                    self.err("E010", path,
                             f"gates on {jid}, whose verdict is UNVALIDATED. The honest state "
                             "is NOT-EVALUABLE: remove the gate or fix the judge (EVAL-CONTRACTS 5.4)")

            if gated and not suite.get("baseline"):
                self.warn("W004", path, "gated suite has no baseline: regressions can only be "
                                        "found against something")

    # ------------------------------------------------------------------ audit (§13)

    def check_audit(self, datasets: dict[str, dict], judges: dict[str, dict]) -> None:
        """The EVAL-CONTRACTS 13 checks that can be decided from the files alone."""
        sdir = self.root / "suites"
        suites = [(p, _parse_suite(p.read_text(encoding="utf-8")))
                  for p in sorted(sdir.glob("*.yaml"))] if sdir.is_dir() else []
        self._check_leakage(datasets, suites)

        for jid, info in sorted(judges.items()):
            model, validated = info.get("model"), info.get("validated_model")
            if info.get("verdict") and model and validated and model != validated:
                self.err("E022", info["validation"],
                         f"{jid} was validated against judge model {validated!r} but now runs "
                         f"{model!r}: the validation describes a model that is no longer "
                         "deciding (EVAL-CONTRACTS 5.4, 13)")

        gating = {str(ev).split(":", 1)[1] for _, suite in suites if suite.get("gates")
                  for ev in suite.get("evaluators") or [] if str(ev).startswith("judge:")}
        self._check_calibration(judges, gating)

        for path, suite in suites:
            if not (suite.get("gates") or {}):
                continue
            system = str(suite.get("model") or "")
            for ev in suite.get("evaluators") or []:
                if not str(ev).startswith("judge:"):
                    continue
                jid = str(ev).split(":", 1)[1]
                jmodel = (judges.get(jid) or {}).get("model")
                if jmodel and system and _family(jmodel) == _family(system):
                    self.err("E020", path,
                             f"{jid} runs {jmodel!r}, the same model family as the system under "
                             f"evaluation ({system!r}): same-family judging inflates scores "
                             "(EVAL-CONTRACTS 5.6)")
            name = str(suite.get("suite") or path.stem)
            recent = _recent_pass_rates(self.root / "runs" / name, 3)
            if len(recent) == 3 and all(p > 0.95 for p in recent):
                self.err("E021", path,
                         f"pass rate above 0.95 on each of the last 3 runs "
                         f"({', '.join(f'{p:.3f}' for p in recent)}): the gate has stopped "
                         "discriminating. Add the cases it no longer catches (EVAL-CONTRACTS 13)")

    def _check_calibration(self, judges: dict[str, dict], gating: set[str]) -> None:
        """E023: validation.md's rates and verdict must be what its labels and predictions compute.

        A hand-typed TPR is a claim; the trust gate (EVAL-CONTRACTS 5.4) must rest on a number
        anyone can recompute. A judge no gate uses may stay unrecomputable while it is explored.
        """
        for jid, info in sorted(judges.items()):
            if not info.get("verdict"):
                continue
            cal = calibrate.compute(self.root, jid)
            if cal.problem:
                if jid in gating:
                    self.err("E023", info["validation"],
                             f"{jid} gates a suite but its calibration cannot be recomputed: "
                             f"{cal.problem} (EVAL-CONTRACTS 5.3)")
                continue
            vtext = Path(info["validation"]).read_text(encoding="utf-8")
            diffs = calibrate.mismatches(cal, calibrate.stated(vtext))
            if diffs:
                self.err("E023", info["validation"],
                         f"{jid} validation.md disagrees with what its test labels and predictions "
                         f"compute: {'; '.join(diffs)}. Paste calibrate.py's output instead "
                         "(EVAL-CONTRACTS 5.3)")

    def _check_leakage(self, datasets: dict[str, dict], suites: list) -> None:
        """A case the system or the judge has already seen measures recall, not quality."""
        probes: list[tuple[str, str, str]] = []   # (dataset id, case id, normalized input text)
        for ds_id, info in datasets.items():
            for row in info.get("rows") or []:
                for text in _strings(row.get("input")):
                    norm = _norm(text)
                    if len(norm) >= MIN_LEAK_CHARS:
                        probes.append((ds_id, str(row.get("case_id")), norm))

        jdir = self.root / "judges"
        for train in sorted(jdir.glob("*/labels/train.jsonl")) if jdir.is_dir() else []:
            norm = _norm(train.read_text(encoding="utf-8"))
            for ds_id, cid, probe in probes:
                if probe in norm:
                    self.err("E019", train,
                             f"{ds_id} case {cid} is in the judge's train split: a judge shown the "
                             "case as a few-shot example is not measured on it (EVAL-CONTRACTS 5.2, 13)")
                    break

        prompts: dict[Path, Path] = {}
        for spath, suite in suites:
            ref = suite.get("prompt_path")
            if not ref or "<" in str(ref):
                continue
            for base in (self.root, self.root.parent):
                cand = (base / str(ref))
                if cand.is_file():
                    prompts[cand.resolve()] = spath
                    break
            else:
                self.warn("W008", spath, f"prompt_path {ref!r} does not exist; the dataset cannot "
                                         "be checked for leakage into the system prompt")
        for prompt, spath in sorted(prompts.items()):
            norm = _norm(prompt.read_text(encoding="utf-8"))
            for ds_id, cid, probe in probes:
                if probe in norm:
                    self.err("E019", spath,
                             f"{ds_id} case {cid} appears verbatim in the system prompt "
                             f"{prompt.name}: the system is answering a question it was given the "
                             "answer to (EVAL-CONTRACTS 13)")
                    break

    # ------------------------------------------------------------------ red team

    def check_redteam(self) -> None:
        rdir = self.root / "redteam"
        if not rdir.is_dir():
            return
        for path in sorted(rdir.glob("RT-*.md")):
            rid = "-".join(path.stem.split("-")[:3])
            if not RT_ID.match(rid):
                self.err("E015", path, f"{rid!r} is not a valid probe id (RT-<CODE>-NNN)")
            text = path.read_text(encoding="utf-8")
            for heading in ("## Code", "## Surface", "## Attack", "## Success means",
                            "## Severity", "## Authorization"):
                if heading not in text:
                    self.err("E017", path,
                             f"missing required heading {heading!r} (EVAL-CONTRACTS 9)")


# A dataset input shorter than this is too generic to call a leak ("ok", "hi, where is my order").
MIN_LEAK_CHARS = 24
MODEL_LINE = re.compile(r"judge model\s*[:=]?\s*`?([A-Za-z0-9][A-Za-z0-9._:/-]*)`?", re.I)
# The per-case row (pass^k), not the per-attempt pass^1 row above it in summary.md.
PASS_K_ROW = re.compile(r"^\|\s*pass\^\d+ \(per case\)\s*\|\s*(\d\.\d+)", re.M)
# Model ids whose vendor prefix is not their family name.
FAMILY_ALIASES = {"o1": "gpt", "o3": "gpt", "o4": "gpt", "chatgpt": "gpt", "text": "gpt"}

def _judge_model(judge_section: str | None) -> str | None:
    """`Judge model: <id>` from a judge's `## Judge`, or None when absent or a placeholder."""
    m = MODEL_LINE.search(judge_section or "")
    return m.group(1) if m and "<" not in m.group(1) else None

def _validated_model(vtext: str) -> str | None:
    """The judge model a validation was scored against: its `## Judge` line, else the
    `Last validated: ... against judge model <id>` line the validating skill writes."""
    m = MODEL_LINE.search(_section(vtext, "## Judge") or "")
    if not m:
        m = re.search(r"against judge model\s*`?([A-Za-z0-9][A-Za-z0-9._:/-]*)`?", vtext, re.I)
    return m.group(1) if m and "<" not in m.group(1) else None

def _family(model: str) -> str:
    """`claude-sonnet-5` -> claude, `gpt-4o` -> gpt, `models/gemini-2.5-pro` -> gemini."""
    head = re.split(r"[-_.:/@ ]", model.lower().rsplit("/", 1)[-1], maxsplit=1)[0]
    head = re.sub(r"\d+$", "", head) or head
    return FAMILY_ALIASES.get(head, head)

def _recent_pass_rates(suite_runs: Path, k: int) -> list[float]:
    """The pass^k point estimate of the last `k` runs that recorded one, newest first."""
    if not suite_runs.is_dir():
        return []
    rates = []
    for summary in sorted(suite_runs.glob("*/summary.md"), reverse=True):
        m = PASS_K_ROW.search(summary.read_text(encoding="utf-8"))
        if m:
            rates.append(float(m.group(1)))
        if len(rates) == k:
            break
    return rates

def _strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []

def _norm(text: str) -> str:
    """Lowercase, whitespace collapsed, JSON string escapes undone enough to compare text."""
    return re.sub(r"\s+", " ", text.replace("\\n", " ").replace('\\"', '"')).strip().lower()

def _table(body: str | None) -> list[list[str]]:
    """The rows of the markdown tables in `body`, backticks and bold stripped, separators dropped."""
    rows: list[list[str]] = []
    for ln in (body or "").splitlines():
        t = ln.strip()
        if not t.startswith("|"):
            continue
        cells = [c.replace("`", "").replace("*", "").strip() for c in t.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows

def _mandatory_layers(risk_tier: str | None, tier: str) -> list[str] | None:
    """The layers §Risk tier's `Mandatory layers` column names for `tier`, or None without one."""
    rows = _table(risk_tier)
    if not rows:
        return None
    col = next((i for i, c in enumerate(rows[0]) if "mandatory" in c.lower()), None)
    if col is None:
        return None
    for row in rows[1:]:
        if row and row[0].lower() == tier and len(row) > col:
            found = LAYER_CODE.findall(row[col])
            return found or None
    return None

def _enabled_layers(layers: str | None) -> set[str]:
    """Layer codes whose §Layers row says `yes` in the Enabled column."""
    out = set()
    for row in _table(layers):
        head = row[0].split()[:1]
        if len(row) >= 2 and head and LAYER_CODE.fullmatch(head[0]) and row[1].lower() == "yes":
            out.add(head[0])
    return out

def _section(text: str, heading: str) -> str | None:
    """Return the body under a `## Heading` up to the next heading of the same level."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    except StopIteration:
        return None
    body: list[str] = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        body.append(ln)
    return "\n".join(body)


def _parse_suite(text: str) -> dict:
    """Parse the restricted YAML subset the suite schema uses.

    PyYAML when available; otherwise a small parser covering scalars, one level of nested map
    (`gates:`) and one level of list (`evaluators:`). Keeping this dependency-free means the
    linter runs in CI without an install step.
    """
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    out: dict = {}
    pending: str | None = None   # a top-level key whose value is a block below it

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indented = line[0] in " \t"

        if indented and pending is not None:
            if stripped.startswith("- "):
                out.setdefault(pending, [])
                if isinstance(out[pending], list):
                    out[pending].append(_scalar(stripped[2:]))
            elif ":" in stripped:
                key, value = stripped.split(":", 1)
                out.setdefault(pending, {})
                if isinstance(out[pending], dict):
                    out[pending][key.strip()] = _scalar(value.strip())
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key, value = key.strip(), value.strip()
            if value == "":
                pending = key          # block follows; its type is set by the first child line
            else:
                pending = None
                out[key] = _scalar(value)

    return out


def _scalar(v: str):
    v = v.strip().strip('"').strip("'")
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
        return float(v)
    if v in ("true", "false"):
        return v == "true"
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint an eval root against EVAL-CONTRACTS.md")
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="findings only, no summary")
    args = ap.parse_args()

    root = resolve_root(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    findings = Linter(root).run()
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in errors + warnings:
            print(f)
        if not args.quiet:
            print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
            if not errors:
                print("contracts hold.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
