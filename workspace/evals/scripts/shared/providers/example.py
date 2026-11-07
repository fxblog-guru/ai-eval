"""Provider adapter — the one function the runner calls.

Copy this to `providers/<your-system>.py`, point `adapter:` in your suite at it, and make it
call YOUR system. Everything else in the bundle is provider-agnostic because this is the only
place that knows how to reach the system under evaluation.

Contract:

    call(case_input: dict) -> {
        "output": dict,      # what the system returned
        "steps":  list,      # ordered spans: [{type, name, input, output, ms}, ...]
        "meta":   dict,      # model id, prompt version, tokens, cost -- whatever it emits
        "verdicts": dict,    # optional: {evaluator_id: bool}, for the shipped scaffold only
    }

`steps` is not optional for anything but the simplest system. The tool call that returned
nothing and the retrieval that fetched the wrong chunk are usually the whole story, and a trace
flattened to input/output hides them.
"""

from __future__ import annotations

import os
from typing import Any


def call(case_input: dict[str, Any]) -> dict[str, Any]:
    """Stub adapter: echoes the input so the scaffold runs end to end before wiring a real system.

    Replace the body. Keep the return shape.
    """
    message = str(case_input.get("message", ""))

    # --- where your system goes -------------------------------------------------
    # from anthropic import Anthropic
    # client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    # resp = client.messages.create(
    #     model=os.environ["EVAL_MODEL"],          # pinned by the suite, never "latest"
    #     temperature=float(os.environ.get("EVAL_TEMPERATURE", "0")),
    #     max_tokens=1024,
    #     system=Path(os.environ["PROMPT_PATH"]).read_text(),
    #     messages=[{"role": "user", "content": message}],
    # )
    # text = resp.content[0].text
    # ----------------------------------------------------------------------------

    text = f"[stub adapter] received {len(message)} characters"

    return {
        "output": {"text": text},
        "steps": [
            {"type": "llm", "name": "generate", "input": {"message": message},
             "output": {"text": text}, "ms": 0}
        ],
        "meta": {
            "model": os.environ.get("EVAL_MODEL", "stub"),
            "prompt_version": os.environ.get("PROMPT_VERSION", "stub"),
            # Fill these from your provider's usage report. The runner adds them up against
            # EVAL-PROFILE §Budget and aborts past a ceiling; left as None, it says the budget
            # was NOT ENFORCED for the run instead of counting a stub's zeros as real spend.
            "tokens_in": None,
            "tokens_out": None,
            "cost": None,
        },
        # The scaffold's placeholder so `runner.py --suite task-example` completes. A real
        # adapter returns no `verdicts`: assertions and judges decide, not the adapter.
        "verdicts": {"stub-always-passes": True},
    }
