"""Harness runner: drives any model through the FC slice + generalization slice.

Talks to any OpenAI-compatible endpoint (vLLM, llama.cpp server, SGLang).
The harness never touches weights and knows nothing about the base model:
it only needs a served model name. Writes raw model responses to outputs/
(auditable receipts) and a scored report.json.

Base-agnostic by construction — swapping the base model (e.g. serving a
new release) is a config change, not a code change:
  PILSNER_MODEL=<served name> python -m eval.runner

Scoring (all mechanical, no judge):
  call items:
    - correct if the model emitted exactly one tool call for the expected
      tool, and EXECUTING the call against the real tool returns the
      expected output (result-equality, with numeric tolerance)
    - wrong_tool / bad_args / no_call_where_needed = failure
  no_call items:
    - correct if the model emitted NO tool call (hallucination guard)
  gen items:
    - correct if the model's final answer matches the computed answer
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from .generator import generate_fc_items, save_items
from .gen_slice import generate_gen_slice, save_slice
from .tools import ToolSpec

BASE_URL = os.environ.get("PILSNER_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("PILSNER_MODEL", "model")
SEED = int(os.environ.get("PILSNER_SEED", "1"))
OUT_DIR = Path(os.environ.get("PILSNER_OUT", "outputs"))
MAX_TOKENS = int(os.environ.get("PILSNER_MAX_TOKENS", "512"))
CATALOG = os.environ.get("PILSNER_CATALOG", "mixed")


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    body: dict = {"model": MODEL, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.0}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def extract_tool_call(resp: dict) -> tuple[str | None, dict | None]:
    """Return (tool_name, args) from a chat completion, or (None, None)."""
    msg = resp["choices"][0]["message"]
    if msg.get("tool_calls"):
        tc = msg["tool_calls"][0]
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        return fn.get("name"), args
    content = msg.get("content") or ""
    m = re.search(r"\{[^{}]*\"name\"\s*:\s*\"([^\"]+)\"[^{}]*\"arguments\"\s*:\s*(\{[^{}]*\})", content)
    if m:
        try:
            return m.group(1), json.loads(m.group(2))
        except json.JSONDecodeError:
            return m.group(1), {}
    return None, None


def args_equal(actual: dict, expected: dict) -> bool:
    """Exact match on scalars/lists with numeric tolerance for floats."""
    if set(actual.keys()) != set(expected.keys()):
        return False
    for k, ev in expected.items():
        av = actual.get(k)
        if isinstance(ev, float) and isinstance(av, (int, float)):
            if abs(av - ev) > 1e-6:
                return False
        elif isinstance(ev, list):
            if not isinstance(av, list) or av != ev:
                return False
        elif av != ev:
            return False
    return True


def outputs_equal(actual: str, expected: str) -> bool:
    try:
        a, e = float(actual), float(expected)
        return abs(a - e) <= 1e-6
    except (TypeError, ValueError):
        return actual.strip() == expected.strip()


def score_fc_item(item: dict, tools: list[ToolSpec], raw: dict) -> dict:
    tool, args = extract_tool_call(raw)
    if item["type"] == "no_call":
        ok = tool is None
        return {"id": item["id"], "ok": ok, "error": None if ok else f"called {tool!r} when none needed"}
    if tool is None:
        return {"id": item["id"], "ok": False, "error": "no tool call emitted"}
    if tool != item["expected_tool"]:
        return {"id": item["id"], "ok": False, "error": f"wrong tool: {tool!r} != {item['expected_tool']!r}"}
    spec = next((t for t in tools if t.name == tool), None)
    if spec is None:
        return {"id": item["id"], "ok": False, "error": f"unknown tool {tool!r}"}
    if not args_equal(args, item["expected_args"]):
        return {"id": item["id"], "ok": False, "error": f"bad args: {args} != {item['expected_args']}"}
    try:
        actual_out = spec.run(args)
    except Exception as exc:  # execution failed = the call does not work
        return {"id": item["id"], "ok": False, "error": f"exec failed: {exc}"}
    if not outputs_equal(str(actual_out), str(item["expected_output"])):
        return {"id": item["id"], "ok": False, "error": f"exec mismatch: {actual_out} != {item['expected_output']}"}
    return {"id": item["id"], "ok": True, "error": None}


def score_gen_item(item: dict, raw: dict) -> dict:
    content = (raw["choices"][0]["message"].get("content") or "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", content.replace(",", ""))
    if m is None:
        return {"id": item.get("id", "?"), "ok": False, "error": f"no number in: {content[:80]!r}"}
    ok = abs(float(m.group(0)) - float(item["expected"])) <= 1e-6
    return {"id": item.get("id", "?"), "ok": ok, "error": None if ok else f"got {m.group(0)}, want {item['expected']}"}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items, catalog = generate_fc_items(SEED, catalog_kind=CATALOG)
    gen_items = generate_gen_slice(SEED)
    save_items(items, catalog, OUT_DIR / f"fc_items_seed{SEED}.json")
    save_slice(gen_items, OUT_DIR / f"gen_items_seed{SEED}.json")
    tools = {t.name: t for t in catalog}

    fc_results, gen_results, receipts = [], [], []
    t0 = time.time()

    for item in items:
        messages = [
            {"role": "system", "content": "You are a precise assistant. Call a tool only when one is needed and you can fulfill the request."},
            {"role": "user", "content": item["query"]},
        ]
        raw = chat(messages, tools=[t.to_openai() for t in catalog])
        receipts.append({"id": item["id"], "query": item["query"], "response": raw})
        fc_results.append(score_fc_item(item, catalog, raw))

    for item in gen_items:
        messages = [
            {"role": "system", "content": "Solve the problem. Reply with only the numeric answer."},
            {"role": "user", "content": item["query"]},
        ]
        raw = chat(messages)
        receipts.append({"id": item["id"], "query": item["query"], "response": raw})
        gen_results.append(score_gen_item(item, raw))

    elapsed = time.time() - t0
    n_call = sum(1 for i in items if i["type"] == "call")
    n_nocall = len(items) - n_call
    fc_ok = sum(1 for r in fc_results if r["ok"])
    gen_ok = sum(1 for r in gen_results if r["ok"])

    report = {
        "model": MODEL,
        "seed": SEED,
        "catalog": CATALOG,
        "fc_accuracy": round(fc_ok / len(items), 4),
        "fc_call_accuracy": round(sum(1 for i, r in zip(items, fc_results) if i["type"] == "call" and r["ok"]) / max(n_call, 1), 4),
        "no_call_guard": round(sum(1 for i, r in zip(items, fc_results) if i["type"] == "no_call" and r["ok"]) / max(n_nocall, 1), 4),
        "gen_accuracy": round(gen_ok / max(len(gen_results), 1), 4),
        "items_total": len(items),
        "gen_items": len(gen_results),
        "elapsed_s": round(elapsed, 1),
        "errors": [r for r in fc_results + gen_results if not r["ok"]][:10],
    }
    with open(OUT_DIR / f"report_seed{SEED}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open(OUT_DIR / f"receipts_seed{SEED}.jsonl", "w", encoding="utf-8") as f:
        for r in receipts:
            f.write(json.dumps(r) + "\n")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
