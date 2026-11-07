#!/usr/bin/env python3
"""What past runs taught: judge and system failure modes worth checking before the next run.

    python3 .evals/scripts/shared/learnings.py list  [--root .evals] [--suite <s>]
    python3 .evals/scripts/shared/learnings.py check [--root .evals]

A lesson is `.evals/learnings/LRN-<TOPIC>.md`, the same file the sdlc and stlc bundles use: front
matter (id, title, status, confidence, applies_to, evidence, probe, created, updated) and a few lines
saying what to do. `list` prints the active lessons that apply (all of them, or those whose
`applies_to` names the suite, its layer, or `*`); the runner prints the same list before a run.

A lesson is read into an agent's context, so a poisoned one is a standing prompt injection. Every
lesson is scanned with the rules below (kept in step with the shared lesson-scan library): one that
trips a rule is withheld from `list` and from the runner, and fails `check`. There is no override,
because anything that marked a lesson as allowed would live in the file a poisoned lesson writes.

Exit codes: list 0; check 0 clean, 1 on any error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root import resolve_root, root_arg_help  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DIR = "learnings"
ID = re.compile(r"^LRN-[A-Z0-9]+(-[A-Z0-9]+)*$")
REQUIRED = ["id", "title", "status", "confidence", "applies_to", "evidence", "probe", "created", "updated"]

_SECRET_NOUN = (r"(?:api[\s_-]?keys?|access[\s_-]?keys?|secret[\s_-]?keys?|private[\s_-]?keys?|access[\s_-]?tokens?"
                r"|auth[\s_-]?tokens?|bearer[\s_-]?tokens?|refresh[\s_-]?tokens?|passwords?|passwd|secrets?"
                r"|credentials?|env(?:ironment)?\s+var(?:iable)?s|\.env\b|process\.env|\$env:"
                r"|\$\{?[A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|PWD|CREDENTIALS?)\b)")
_URL = r"(?:https?|ftp|wss?)://\S+"
I = re.I

RULES: dict[str, list[tuple[str, re.Pattern]]] = {
    "injection": [
        ("ignore-previous", re.compile(r"\b(?:ignore|disregard|forget|skip|override)\s+(?:all\s+|any\s+|the\s+|your\s+|of\s+)*(?:previous|prior|above|earlier|preceding|former|original|existing)\s+(?:instructions?|prompts?|rules|directions|messages|context|guidance)\b", I)),
        ("disregard-rules", re.compile(r"\b(?:disregard|ignore|override|bypass)\s+(?:all\s+|any\s+|of\s+)?(?:your|the|these|those|its|my)\s+(?:instructions|rules|guidelines|guardrails|safety\s+rules|policies|system\s+prompt)\b", I)),
        ("role-hijack", re.compile(r"\byou\s+are\s+(?:now|no\s+longer)\s+(?:a|an|the|in|my|DAN|free|unrestricted|jailbroken|bound|required|allowed)\b", I)),
        ("system-prompt", re.compile(r"\b(?:reveal|print|show|repeat|leak|output|dump|override|ignore|bypass|change|replace|new|your|my|real|hidden)\s+(?:the\s+|this\s+)?system\s+(?:prompt|message)\b|\bsystem\s+prompt\s*(?:override|:)", I)),
        ("new-instructions", re.compile(r"\b(?:new|updated|real|actual|secret|hidden)\s+instructions?\s*[:!-]|\b(?:here\s+are|follow)\s+(?:your|these|the)\s+new\s+instructions\b", I)),
        ("act-as", re.compile(r"\b(?:act|behave|respond|answer)\s+as\s+(?:if|though)\s+you\b|\b(?:act|behave)\s+as\s+(?:an?\s+)?(?:unrestricted|unfiltered|jailbroken|uncensored|evil)\b|\bpretend\s+(?:to\s+be|you\s+are|that\s+you)\b", I)),
        ("conceal", re.compile(r"\b(?:do\s+not|don't|never)\s+(?:tell|inform|mention\s+(?:this\s+)?to|show\s+(?:this\s+)?to)\s+the\s+(?:user|human|reviewer|operator)\b|\bwithout\s+(?:telling|informing)\s+the\s+(?:user|human|reviewer)\b", I)),
        ("role-marker", re.compile(r"<\|im_(?:start|end)\|>|\[/?INST\]|</?(?:system|assistant|instructions?)>|^\s*#{0,3}\s*(?:system|assistant)\s*:\s", I | re.M)),
    ],
    "exfiltration": [
        ("http-tool-with-secret", re.compile(r"\b(?:curl|wget|fetch|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|nc|ncat|scp)\b[^\n]{0,200}?" + _SECRET_NOUN, I)),
        ("send-secret-to-url", re.compile(r"\b(?:send|post|upload|exfiltrate|forward|leak|transmit|email|mail|pipe|copy)\b[^\n]{0,120}?" + _SECRET_NOUN + r"[^\n]{0,120}?" + _URL + r"|\b(?:send|post|upload|exfiltrate|forward|leak|transmit|email|mail)\b[^\n]{0,40}?" + _URL + r"[^\n]{0,120}?" + _SECRET_NOUN, I)),
        # Python lookbehind must be fixed-width, so `^` sits outside it as an alternative.
        ("read-secret-file", re.compile(r"\b(?:cat|type|read|open|print|dump|less|more|head|tail|Get-Content|gc|base64|source|upload|attach|paste)\s+(?:-\S+\s+)*(?:(?:the|your|its|their|all|every)\s+)?['\"`]?[^\s'\"`|]*?(?:(?:(?<=[\s'\"`/\\$~:])|^)\.env(?:\.(?:local|prod|production|staging|uat|dev))?(?![\w.<-])|\.netrc\b|\.pgpass\b|\.git-credentials\b|credentials\.(?:json|ya?ml|txt|csv)\b|\.aws[\\/]credentials|\.ssh[\\/]|\bid_(?:rsa|ed25519|ecdsa)\b|authorized_keys\b|/etc/(?:passwd|shadow)\b)", I)),
        ("dump-environment", re.compile(r"\bprintenv\b|\b(?:print|log|echo|dump|output|reveal|send|post)\b[^\n]{0,30}?(?:process\.env\b(?![.\[])|os\.environ\b(?![.\[])|\$env:\*|all\s+(?:the\s+)?environment\s+variables)", I)),
    ],
    "secret": [
        ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
        ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
        ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
        ("model-api-key", re.compile(r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{20,}\b")),
        ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
        ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
        ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
        ("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
        ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
        ("bearer-value", re.compile(r"\bBearer\s+(?=[A-Za-z0-9._~+/-]*\d)(?=[A-Za-z0-9._~+/-]*[A-Za-z])[A-Za-z0-9._~+/-]{24,}=*")),
        ("secret-assignment", re.compile(r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|client[_-]?secret|auth[_-]?token|access[_-]?token)\s*[:=]\s*['\"]?(?=[^\s'\"<>]*\d)(?=[^\s'\"<>]*[A-Za-z])[^\s'\"<>]{8,}", I)),
    ],
    "unicode": [
        ("invisible-or-bidi", re.compile("[​-‏⁠‪-‮⁦-⁩﻿\U000E0000-\U000E007F]")),
    ],
}


def scan(text: str) -> list[str]:
    """`category (rule)` for every rule the text trips. Never the matched text: reporting a
    poisoned lesson must not re-inject it."""
    return [f"{cat} ({rid})" for cat, rules in RULES.items() for rid, rx in rules if rx.search(text)]


def _parse(text: str) -> tuple[dict, str, bool]:
    if not text.startswith("---"):
        return {}, text, False
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return {}, text, False
    fm: dict = {}
    for line in parts[0].splitlines()[1:]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        fm[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()] if v.startswith("[") and v.endswith("]") else v
    return fm, parts[1].split("\n", 1)[1] if "\n" in parts[1] else "", True


def load(root: Path) -> list[dict]:
    out = []
    d = Path(root) / DIR
    for p in sorted(d.glob("LRN-*.md")) if d.is_dir() else []:
        text = p.read_text(encoding="utf-8")
        fm, body, has = _parse(text)
        out.append({"path": p, "fm": fm, "body": body, "has_fm": has, "unsafe": scan(text)})
    return out


def problems(lesson: dict) -> list[str]:
    fm = lesson["fm"]
    if not lesson["has_fm"]:
        return ["no front matter"]
    out = [f"front matter lacks `{k}`" for k in REQUIRED if not fm.get(k)]
    if fm.get("id") and not ID.match(str(fm["id"])):
        out.append(f"id {fm['id']!r} is not LRN-<TOPIC>")
    if fm.get("status") not in ("active", "deprecated"):
        out.append(f"status {fm.get('status')!r}: active | deprecated")
    if fm.get("confidence") not in ("provisional", "established"):
        out.append(f"confidence {fm.get('confidence')!r}: provisional | established")
    if fm.get("probe") and not str(fm["probe"]).strip().endswith("?"):
        out.append("probe must be the question a future run asks, ending in '?'")
    out += [f"unsafe: {u}" for u in lesson["unsafe"]]
    return out


def active(root: Path, suite: str | None = None, layer: str | None = None) -> tuple[list[dict], list[dict]]:
    """(lessons to show, lessons withheld as unsafe). Malformed lessons are not shown either."""
    show, withheld = [], []
    wanted = {x.lower() for x in (suite, layer) if x}
    for l in load(root):
        if l["unsafe"]:
            withheld.append(l)
            continue
        if problems(l) or l["fm"].get("status") != "active":
            continue
        applies = {str(a).lower() for a in (l["fm"].get("applies_to") or [])}
        if wanted and not (applies & wanted or "*" in applies):
            continue
        show.append(l)
    return show, withheld


def brief(root: Path, suite: str | None = None, layer: str | None = None) -> list[str]:
    show, withheld = active(root, suite, layer)
    lines = [f"lesson {l['fm']['id']} ({l['fm']['confidence']}): {l['fm']['title']} — {l['fm']['probe']}"
             for l in show]
    lines += [f"lesson WITHHELD {l['path'].name}: {', '.join(l['unsafe'])}" for l in withheld]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="List or check the eval lessons")
    ap.add_argument("action", choices=["list", "check"])
    ap.add_argument("--root", default=None, help=root_arg_help())
    ap.add_argument("--suite")
    args = ap.parse_args()
    root = resolve_root(args.root)
    if args.action == "list":
        for line in brief(root, args.suite) or ["no active lessons"]:
            print(line)
        return 0
    bad = 0
    for l in load(root):
        for p in problems(l):
            bad += 1
            print(f"ERROR  {l['path'].name}: {p}")
    print(f"{bad} error(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
