/**
 * TypeScript provider adapter — for systems whose entry point lives in Node and cannot be
 * reached cleanly from Python.
 *
 * The runner, the statistics, the linter and the CTRF writer stay in Python. This file is a
 * thin bridge, and deliberately the only TypeScript in the bundle: keeping one implementation
 * of the statistics avoids the situation where a Wilson interval computed in CI disagrees with
 * one computed locally, which is exactly the kind of bug nobody finds.
 *
 * Run it as a subprocess from a Python adapter:
 *
 *   # .evals/scripts/shared/providers/node_system.py
 *   import json, subprocess
 *   def call(case_input: dict) -> dict:
 *       out = subprocess.run(
 *           ["npx", "tsx", ".evals/scripts/ts/adapter.ts"],
 *           input=json.dumps(case_input), capture_output=True, text=True, check=True)
 *       return json.loads(out.stdout)
 *
 * Contract: read one JSON object from stdin, write one JSON object to stdout. Nothing else may
 * go to stdout — log to stderr.
 */

export interface Step {
  type: "llm" | "tool" | "retrieval";
  name: string;
  input: unknown;
  output: unknown;
  ms: number;
}

export interface AdapterResult {
  output: Record<string, unknown>;
  /**
   * The ordered spans. Not optional for anything but the simplest system: the tool call that
   * returned nothing and the retrieval that fetched the wrong chunk are usually the whole story,
   * and a trace flattened to input/output hides them.
   */
  steps: Step[];
  meta: {
    model: string;
    prompt_version: string;
    tokens_in?: number;
    tokens_out?: number;
    cost?: number;
    [key: string]: unknown;
  };
}

export async function call(caseInput: Record<string, unknown>): Promise<AdapterResult> {
  const message = String(caseInput.message ?? "");
  const started = Date.now();

  // --- where your system goes ------------------------------------------------
  // const res = await myAssistant.handle({ message, userId: caseInput.user_id });
  // const text = res.text;
  // ---------------------------------------------------------------------------

  const text = `[stub adapter] received ${message.length} characters`;

  return {
    output: { text },
    steps: [
      { type: "llm", name: "generate", input: { message }, output: { text }, ms: Date.now() - started },
    ],
    meta: {
      // Pinned by the suite, never an alias ending in "latest": a provider can repoint an alias
      // with no change in this repo, which makes every historical comparison quietly wrong.
      model: process.env.EVAL_MODEL ?? "stub",
      prompt_version: process.env.PROMPT_VERSION ?? "stub",
      tokens_in: 0,
      tokens_out: 0,
      cost: 0,
    },
  };
}

async function main(): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  const caseInput = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
  process.stdout.write(JSON.stringify(await call(caseInput)));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    // stderr, so a crash cannot be mistaken for a result on stdout.
    console.error(err);
    process.exit(1);
  });
}
