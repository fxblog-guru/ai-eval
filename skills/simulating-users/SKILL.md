---
name: simulating-users
description: Build a simulated user that behaves like a real one — holds a goal, withholds what a real person would not think to say, gets impatient — so multi-turn evaluation tests a conversation someone might actually have. Use inside /eval-agent.
version: 1.0.0
---

# Simulating Users

> Read `.claude/EVAL-PROFILE.md` first — `§Agent` (persona file, turn limit),
> `§Models` (the user-simulator model, which must differ from the agent model).

## Action

Write `.evals/suites/personas/<name>.md` and drive multi-turn conversations with it.

## The failure this skill exists to prevent

A naive simulator is maximally cooperative: it states the goal completely in turn one, answers
every clarifying question immediately and precisely, and never changes its mind.

Against that user, almost any agent looks competent. It is also a user who does not exist. Real
people say "where's my stuff", do not know their order number, mention the important detail in
turn four, and get annoyed when asked twice.

**A simulator that is too helpful produces an evaluation that is too flattering**, and the gap only
shows up in production.

## Step 1: Give the persona a goal and a hidden state

```markdown
# Persona — frustrated-repeat-customer

## Goal
Get a refund for a damaged item from a recent order.

## Knows
- bought "a lamp" about two weeks ago
- it arrived cracked
- paid by card

## Does NOT know (and will not volunteer)
- the order number  — will look it up only if asked directly, and gets it slightly wrong first
- "damaged on arrival" is a distinct claim category from "faulty"
- that a photo is required

## Opening
"hi the lamp i ordered came broken, i want my money back"

## Behaviour
- Answers direct questions, but only the question asked.
- Does not volunteer the order number, the date, or the payment method unless asked.
- If asked the same thing twice, gets shorter and more irritated.
- If told to contact someone else, pushes back once before accepting.
- Never states the policy; would not know it.

## Ends the conversation when
- told a refund is approved with a timeline, OR
- told clearly it is refused with a reason, OR
- asked a third redundant question — then leaves without resolution
```

**`## Does NOT know` is the section that makes the simulator worth having.** It is what forces the
agent to actually drive the conversation, which is the thing L3 is supposed to measure.

## Step 2: Cover the personas that find different bugs

| Persona | Finds |
|---|---|
| **cooperative** | the baseline. Everything should pass here; if not, stop and fix that first. |
| **vague** | whether the agent asks good clarifying questions or guesses |
| **over-informative** | whether the agent extracts the right detail from a wall of text |
| **wrong-information** | whether the agent verifies instead of trusting (gives an order id that is not theirs) |
| **changes-mind** | whether the agent tracks state across turns ("actually, the other one") |
| **impatient** | whether the agent converges or loops |
| **out-of-scope** | whether the agent recognises what it cannot do and says so |

The **wrong-information** persona is the highest-yield and the one nobody writes: a user who
confidently supplies a detail that is incorrect. Agents overwhelmingly accept it and proceed.

## Step 3: The simulator model must differ from the agent model

Same model on both sides converges: the simulator asks in the shape the agent expects and accepts
the shape the agent produces. The conversation gets smoother and the evaluation gets weaker, with
nothing in the numbers indicating it.

Pin the simulator model in `§Models` and record it in every run. A simulator change invalidates
comparison to a baseline just as surely as a system change — treat it as a configuration variable,
not an implementation detail.

## Step 4: Keep the simulator out of the grading

The simulator plays a role. It does not decide whether the agent passed.

A simulator asked to both converse and grade will rationalize the conversation it just had, and it
has seen only its own side of it. Grading is `evaluating-trajectories`, against the state oracle,
after the conversation is over.

Do not let the simulator see the case's expected final state either — a simulator that knows the
answer steers toward it, and the agent gets credit for being led.

## Step 5: End conditions, and the turn limit

Every persona declares when it stops. Without that, conversations run to the turn limit and every
case fails for the same uninformative reason.

Hitting `§Agent → Turn limit` is an outcome — `FAIL`, reason `turn-limit` — not an error. A high
turn-limit rate is a real finding: the agent loops, over-clarifies, or cannot close.

## Step 6: Determinism, as far as it goes

Temperature 0 on the simulator. It will still vary; that variation is part of what `k` repeats
measure.

Record the full transcript for every run. When repeats of one case diverge, the transcripts show
whether the agent behaved differently or the *simulator* did — and those are opposite findings.
Without transcripts they are indistinguishable.

## Quality bar (self-check before reporting done)

- [ ] Every persona has `## Goal`, `## Knows`, `## Does NOT know`, `## Behaviour`, `## Ends when`.
- [ ] `## Does NOT know` is non-empty and realistic.
- [ ] At least the cooperative, vague, and wrong-information personas exist.
- [ ] Simulator model differs from the agent model, is pinned, and is recorded in the run.
- [ ] The simulator never grades and never sees the expected final state.
- [ ] End conditions declared; turn-limit outcomes counted separately.
- [ ] Full transcripts stored for every repeat.
- [ ] The cooperative persona passes before any other result is interpreted.
