#!/usr/bin/env bash
# Self-check for the agentic-fx-ai-eval bundle itself (not for projects that install it).
#
# Guards the contracts: the shipped linter must accept the reference seed and must catch every
# violation in tests/fixture; every shipped script must parse and behave; every agent, command,
# and skill must carry the frontmatter the harness reads; and every skill an agent names must
# exist.
#
#   bash tests/selfcheck.sh

set -uo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
FAILURES=0

pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
head2() { printf '\n\033[1m%s\033[0m\n' "$1"; }

LINT="workspace/evals/scripts/shared/lint_evals.py"

# --------------------------------------------------------------------- 1. scripts parse
head2 "1. every shipped script parses"
while IFS= read -r f; do
  if $PY -m py_compile "$f" 2>/dev/null; then pass "$f"; else fail "$f does not parse"; fi
done < <(find workspace -name '*.py' -not -path '*/__pycache__/*' | sort)

# --------------------------------------------------------------------- 2. the seed lints clean
head2 "2. the shipped seed satisfies its own contracts"
if out=$($PY "$LINT" --root workspace/evals 2>&1); then
  pass "workspace/evals lints clean"
else
  fail "workspace/evals does not lint clean:"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# --------------------------------------------------------------------- 3. the fixture is caught
head2 "3. the linter catches every violation in tests/fixture"
EXPECTED_CODES="E001,E002,E003,E004,E006,E007,E008,E009,E010,E011,E012,E013,E014,E015,E016,E017,E018,E019,E020,E021,E022,E023,E024"
EXPECTED_ERRORS=29

result=$($PY "$LINT" --root tests/fixture/evals --json 2>/dev/null | $PY -c '
import json, sys
f = json.load(sys.stdin)
errs = [x for x in f if x["severity"] == "error"]
print(",".join(sorted({x["code"] for x in errs})))
print(len(errs))
')
got_codes=$(printf '%s' "$result" | sed -n 1p)
got_errors=$(printf '%s' "$result" | sed -n 2p)

if [ "$got_codes" = "$EXPECTED_CODES" ]; then
  pass "all 23 violation classes caught"
else
  fail "violation classes differ"
  printf '        expected: %s\n        got:      %s\n' "$EXPECTED_CODES" "$got_codes"
fi

if [ "$got_errors" = "$EXPECTED_ERRORS" ]; then
  pass "exactly $EXPECTED_ERRORS errors, as expected"
else
  fail "expected $EXPECTED_ERRORS errors, got $got_errors"
fi

if $PY "$LINT" --root tests/fixture/evals >/dev/null 2>&1; then
  fail "linter exited 0 on a fixture full of errors"
else
  pass "linter exits non-zero on errors"
fi

# --------------------------------------------------------------------- 4. statistics
head2 "4. the statistics are correct where it matters"
$PY - <<'PYEOF' && pass "wilson, pass^k, bias correction, McNemar" || fail "statistics are wrong"
import sys
sys.path.insert(0, "workspace/evals/scripts/shared")
import stats

# Wilson stays inside [0,1] where the normal approximation does not.
r = stats.wilson(97, 100)
assert r.hi <= 1.0, r
r = stats.wilson(40, 40)
assert r.lo < 1.0 and r.hi == 1.0, "a zero-width interval would claim certainty from 40 samples"

# Gates compare the lower bound; an interval spanning the threshold is NOT-EVALUABLE.
assert stats.wilson(25, 30).gate(0.80) == "NOT-EVALUABLE"
assert stats.wilson(84, 100).gate(0.80) == "NOT-EVALUABLE"  # interval spans it
assert stats.wilson(60, 100).gate(0.80) == "FAIL"           # entirely below it
assert stats.wilson(336, 400).gate(0.80) == "PASS"

# pass^k is stricter than pass^1, always.
outcomes = [[True, True, True], [True, False, True], [False, False, False]]
assert stats.pass_at_1(outcomes).p > stats.pass_hat_k(outcomes).p
assert stats.classify([True, False, True]) == "FLAKY"
assert stats.classify([True, True]) == "PASS"
assert stats.classify([False, False]) == "FAIL"

# Bias correction refuses to run when the judge cannot separate the classes.
assert stats.bias_correct(0.84, tpr=0.90, fpr=0.10) is not None
assert stats.bias_correct(0.84, tpr=0.55, fpr=0.20) is None

# Fail is the positive class, and accuracy is deliberately absent.
c = stats.Confusion(tp=45, fp=5, tn=45, fn=5)
assert abs(c.tpr - 0.9) < 1e-9 and abs(c.tnr - 0.9) < 1e-9
assert not hasattr(c, "accuracy")
v, why = stats.judge_verdict(c, min_tpr=0.8, min_tnr=0.8, min_kappa=0.6)
assert v == "VALIDATED", why
v, why = stats.judge_verdict(stats.Confusion(tp=4, fp=3, tn=20, fn=9),
                             min_tpr=0.8, min_tnr=0.8, min_kappa=0.6)
assert v == "UNVALIDATED" and why

# A paired comparison with few discordant pairs reports no power rather than a finding.
p = stats.paired({f"c{i}": True for i in range(100)},
                 {f"c{i}": i > 2 for i in range(100)})
assert p.b == 3 and p.c == 0 and not p.has_power
PYEOF

# --------------------------------------------------------------------- 5. runner
head2 "5. the runner completes a dry run on the seed"
if out=$(cd workspace/evals && $PY scripts/shared/runner.py --suite task-example --root . --dry-run 2>&1); then
  if printf '%s' "$out" | grep -q "no model calls made"; then
    pass "dry run completes without calling a model"
  else
    fail "dry run did not report that it made no model calls"
  fi
else
  fail "dry run failed:"; printf '%s\n' "$out" | sed 's/^/        /'
fi

# --------------------------------------------------------------------- 5b. derived state
head2 "5b. state.json derives from the artifacts, and --check notices when it no longer does"
BS="workspace/evals/scripts/shared/build_state.py"
TMP=$(mktemp -d)
cp -r workspace/evals "$TMP/evals"
# Run folders are git-ignored, so a clean clone has none and a working copy may have some. Drop
# them: the expected phase must not depend on whether this machine ever ran the seed.
find "$TMP/evals/runs" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
if $PY "$BS" --root "$TMP/evals" --quiet && $PY "$BS" --root "$TMP/evals" --check --quiet; then
  pass "the seed builds an index that --check accepts"
else
  fail "the seed index does not build or does not check"
fi
state_field() { $PY -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(eval(sys.argv[2]))" "$@"; }
[ "$(state_field "$TMP/evals/state.json" "d['schema']")" = "1" ] && pass "schema is 1" || fail "schema is not 1"
[ "$(state_field "$TMP/evals/state.json" "d['phase']")" = "Validate" ] && pass "the seed, with no runs, is at phase Validate" || fail "the seed phase is wrong"
printf '\n' >> "$TMP/evals/taxonomy/FM-001-invented-order-id.md"
if $PY "$BS" --root "$TMP/evals" --check --quiet 2>/dev/null; then
  fail "--check accepted an index older than an edited artifact"
else
  pass "--check fails once an artifact changes"
fi
rm -rf "$TMP"
TMP=$(mktemp -d)
cp -r tests/fixture/evals "$TMP/evals"
$PY "$BS" --root "$TMP/evals" --quiet
[ "$(state_field "$TMP/evals/state.json" "d['next_command']")" = "/eval-validate JDG-tone-v1" ] \
  && pass "the broken fixture points at the unvalidated judge" || fail "the broken fixture's next command is wrong"
rm -rf "$TMP"
if out=$(cd workspace/evals && $PY scripts/shared/status.py --root . --brief 2>&1) && printf '%s' "$out" | grep -q '^\[agentic-fx-ai-eval\] example-system'; then
  pass "status.py --brief prints the session line"
else
  fail "status.py --brief did not print the session line: $out"
fi

# --------------------------------------------------------------------- 6. frontmatter
head2 "6. agents, commands, and skills carry their frontmatter"
check_frontmatter() {
  local file=$1; shift
  local missing=""
  head -20 "$file" | grep -q '^---$' || { fail "$file has no frontmatter"; return; }
  for key in "$@"; do
    awk '/^---$/{n++; next} n==1' "$file" | grep -q "^$key:" || missing="$missing $key"
  done
  [ -z "$missing" ] && pass "$file" || fail "$file missing:$missing"
}
for f in agents/*.md; do check_frontmatter "$f" name description tools model; done
for f in commands/*.md; do check_frontmatter "$f" description; done
for f in skills/*/SKILL.md; do check_frontmatter "$f" name description version; done

# --------------------------------------------------------------------- 7. skill names match dirs
head2 "7. every skill's name matches its directory, and every referenced skill exists"
for f in skills/*/SKILL.md; do
  dir=$(basename "$(dirname "$f")")
  name=$(awk '/^---$/{n++; next} n==1 && /^name:/{print $2; exit}' "$f")
  [ "$dir" = "$name" ] && pass "$dir" || fail "$f declares name '$name' in directory '$dir'"
done

for f in agents/*.md; do
  awk '/^---$/{n++; next} n==1 && /^skills:/{s=1; next} n==1 && s && /^  - /{print $2} n==1 && s && !/^  - /{s=0}' "$f" |
  while read -r skill; do
    [ -z "$skill" ] && continue
    if [ -f "skills/$skill/SKILL.md" ]; then
      pass "$(basename "$f") -> $skill"
    else
      fail "$(basename "$f") names skill '$skill', which does not exist"
    fi
  done
done

# --------------------------------------------------------------------- 8. contract references
head2 "8. the bundle's own documents are consistent"
for f in EVAL-PROFILE.md EVAL-CONTRACTS.md README.md; do
  [ -f "$f" ] && pass "$f present" || fail "$f is missing"
done

# Every command that delegates must name an agent that exists.
for f in commands/*.md; do
  grep -oE 'Delegate to \`?[a-z-]+\`?' "$f" 2>/dev/null | sed -E 's/Delegate to `?//; s/`//' |
  while read -r agent; do
    [ -z "$agent" ] && continue
    [ -f "agents/$agent.md" ] && pass "$(basename "$f") -> $agent" \
      || fail "$(basename "$f") delegates to '$agent', which has no agent file"
  done
done

# --------------------------------------------------------------------- 9. activity log
head2 "9. the activity log, and the runner's verdict, error count, budget, redaction and bias correction"
# Run as scripts, not `-m unittest tests/...`: that form needs the working directory on sys.path,
# which `python -I` removes.
for t in tests/test_activity.py tests/test_runner.py tests/test_calibrate.py tests/test_settings.py tests/test_compare_bench.py tests/test_economy.py tests/test_baseline.py tests/test_learnings.py tests/test_update_line.py tests/test_root.py tests/test_layers.py; do
  if out=$($PY "$t" 2>&1); then
    pass "$t"
  else
    fail "$t:"; printf '%s\n' "$out" | tail -20 | sed 's/^/        /'
  fi
done

# --------------------------------------------------------------------- summary
printf '\n'
if [ "$FAILURES" -eq 0 ]; then
  printf '\033[32mselfcheck passed\033[0m — contracts hold.\n'
  exit 0
fi
printf '\033[31mselfcheck failed\033[0m — %d problem(s).\n' "$FAILURES"
exit 1
