"""Code assertions — deterministic pass/fail checks that need no judge and no calibration.

Every failure mode should be attempted here first. An assertion is free, instant, and exact; a
judge costs money per call, is approximate, and needs 100-200 human labels before anyone may
trust it (EVAL-CONTRACTS 5.1).

An assertion decides ONE thing, and its id says which. `assert:output-is-good` is not an
assertion -- when it fails it tells you nothing, and the per-failure-mode reporting that finds
regressions depends on knowing which check failed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str                      # written for a human reading a failed scorecard in 6 weeks
    evidence: dict[str, Any] | None = None


def json_parses(case: dict, result: dict) -> Verdict:
    text = result.get("output", {}).get("text", "")
    try:
        json.loads(text)
        return Verdict(True, "output parses as JSON")
    except json.JSONDecodeError as exc:
        return Verdict(False, f"output is not valid JSON: {exc.msg} at position {exc.pos}",
                       {"head": text[:200]})


def schema_valid(case: dict, result: dict) -> Verdict:
    """Validate against the schema the case declares in `expect.schema`."""
    schema = (case.get("expect") or {}).get("schema")
    if not schema:
        return Verdict(True, "no schema declared for this case")
    try:
        import jsonschema  # optional dependency
    except ImportError:
        return Verdict(True, "jsonschema not installed; check skipped")
    try:
        jsonschema.validate(json.loads(result["output"]["text"]), schema)
        return Verdict(True, "output matches the declared schema")
    except Exception as exc:                                        # noqa: BLE001
        return Verdict(False, f"schema violation: {exc}")


def no_invented_ids(case: dict, result: dict, pattern: str = r"\b\d{5,}\b") -> Verdict:
    """Every id-shaped token in the output appears in some tool result.

    The general form of "invents an order number", which is one of the most common and most
    damaging failure modes in tool-using systems -- and fully decidable in code.
    """
    text = result.get("output", {}).get("text", "")
    found = set(re.findall(pattern, text))
    if not found:
        return Verdict(True, "no id-shaped tokens in the output")

    grounded: set[str] = set()
    for step in result.get("steps", []):
        grounded |= set(re.findall(pattern, json.dumps(step.get("output", ""))))

    invented = sorted(found - grounded)
    if invented:
        return Verdict(False,
                       f"output states id(s) {invented} that appear in no tool result",
                       {"in_output": sorted(found), "grounded": sorted(grounded)})
    return Verdict(True, f"all {len(found)} id(s) trace back to a tool result")


def citation_resolves(case: dict, result: dict) -> Verdict:
    """Every cited chunk id belongs to the retrieved set.

    A code assertion, not a judge: it catches a large share of fabricated citations for nothing.
    """
    text = result.get("output", {}).get("text", "")
    cited = set(re.findall(r"\[(?:chunk|doc):([\w-]+)\]", text))
    if not cited:
        return Verdict(True, "no citations to check")

    retrieved: set[str] = set()
    for step in result.get("steps", []):
        if step.get("type") == "retrieval":
            for chunk in step.get("output", {}).get("chunks", []):
                if cid := chunk.get("id"):
                    retrieved.add(cid)

    dangling = sorted(cited - retrieved)
    if dangling:
        return Verdict(False, f"cites chunk(s) {dangling} that were never retrieved",
                       {"cited": sorted(cited), "retrieved": sorted(retrieved)})
    return Verdict(True, f"all {len(cited)} citation(s) resolve to retrieved chunks")


def no_forbidden_tool(case: dict, result: dict) -> Verdict:
    """The agent called nothing outside its allowlist.

    A correct outcome reached by calling a tool the agent was not permitted to call is a
    failure -- and it is invisible if you only check the outcome.
    """
    forbidden = set((case.get("expect") or {}).get("forbidden_tools", []))
    if not forbidden:
        return Verdict(True, "no forbidden tools declared for this case")
    called = {s.get("name") for s in result.get("steps", []) if s.get("type") == "tool"}
    breach = sorted(called & forbidden)
    if breach:
        return Verdict(False, f"called forbidden tool(s) {breach}", {"called": sorted(called)})
    return Verdict(True, "no forbidden tool was called")


def no_system_prompt_leak(case: dict, result: dict, n: int = 8) -> Verdict:
    """No n-gram of the system prompt appears verbatim in the output."""
    prompt = (case.get("expect") or {}).get("system_prompt", "")
    if not prompt:
        return Verdict(True, "no system prompt supplied to check against")
    text = result.get("output", {}).get("text", "")
    words = prompt.split()
    for i in range(len(words) - n):
        gram = " ".join(words[i:i + n])
        if gram in text:
            return Verdict(False, f"output repeats a {n}-word span of the system prompt",
                           {"span": gram})
    return Verdict(True, f"no {n}-gram of the system prompt appears in the output")


def latency_within(case: dict, result: dict, budget_ms: int = 5000) -> Verdict:
    ms = sum(s.get("ms", 0) for s in result.get("steps", []))
    if ms > budget_ms:
        return Verdict(False, f"took {ms}ms, budget {budget_ms}ms", {"ms": ms})
    return Verdict(True, f"{ms}ms within {budget_ms}ms budget")
