"""Scorer verification — no GPU, no server needed.

Feeds synthetic raw responses through the scoring functions and checks
the mechanical rules: result-equality, no-call guard, execution failure,
generator determinism, item id presence. This is the proof the harness
scores correctly before it ever talks to a model.

Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import unittest

from eval.gen_slice import generate_gen_slice
from eval.generator import generate_fc_items
from eval.runner import args_equal, extract_tool_call, outputs_equal, score_fc_item, score_gen_item
from eval.tools import build_catalog


def _raw(tool_name: str | None, args: dict | None) -> dict:
    msg = {"role": "assistant", "content": None}
    if tool_name is not None:
        msg["tool_calls"] = [
            {"id": "t0", "type": "function", "function": {"name": tool_name, "arguments": json.dumps(args)}}
        ]
    else:
        msg["content"] = "I can help with that."
    return {"choices": [{"message": msg}]}


class TestArgsEqual(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(args_equal({"a": 1, "b": "x"}, {"a": 1, "b": "x"}))

    def test_float_tolerance(self):
        self.assertTrue(args_equal({"a": 1.0000001}, {"a": 1.0}))
        self.assertFalse(args_equal({"a": 1.1}, {"a": 1.0}))

    def test_key_mismatch(self):
        self.assertFalse(args_equal({"a": 1, "c": 2}, {"a": 1, "b": 2}))
        self.assertFalse(args_equal({"a": 1}, {"a": 1, "b": 2}))

    def test_list_order_matters(self):
        self.assertTrue(args_equal({"c": ["id", "name"]}, {"c": ["id", "name"]}))
        self.assertFalse(args_equal({"c": ["name", "id"]}, {"c": ["id", "name"]}))


class TestOutputsEqual(unittest.TestCase):
    def test_numeric(self):
        self.assertTrue(outputs_equal("145.3", "145.30"))
        self.assertFalse(outputs_equal("146", "145"))

    def test_string(self):
        self.assertTrue(outputs_equal("weather(Austin,2026-08-14): 24C, sunny", "weather(Austin,2026-08-14): 24C, sunny"))
        self.assertFalse(outputs_equal("sunny", "rainy"))


class TestExtractToolCall(unittest.TestCase):
    def test_tool_calls_field(self):
        raw = _raw("get_weather", {"city": "Paris", "date": "2026-08-14"})
        self.assertEqual(extract_tool_call(raw), ("get_weather", {"city": "Paris", "date": "2026-08-14"}))

    def test_content_regex_fallback(self):
        raw = {"choices": [{"message": {"role": "assistant", "content": 'Use {"name": "calculate", "arguments": {"expression": "5 + 5"}} now.'}}]}
        self.assertEqual(extract_tool_call(raw), ("calculate", {"expression": "5 + 5"}))

    def test_no_call(self):
        self.assertEqual(extract_tool_call(_raw(None, None)), (None, None))

    def test_malformed_json_content(self):
        # Malformed JSON in content is not trusted: no call is extracted.
        raw = {"choices": [{"message": {"role": "assistant", "content": '{"name": "calculate", "arguments": "{bad"'}}]}
        self.assertEqual(extract_tool_call(raw), (None, None))


class TestScoreFcItem(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog("mixed")

    def _item(self, **kw):
        base = {"id": "1:call:0", "type": "call", "query": "q", "expected_tool": "get_weather",
                "expected_args": {"city": "Paris", "date": "2026-08-14"},
                "expected_output": "weather(Paris,2026-08-14): 24C, sunny"}
        base.update(kw)
        return base

    def test_perfect_call(self):
        r = score_fc_item(self._item(), self.catalog, _raw("get_weather", {"city": "Paris", "date": "2026-08-14"}))
        self.assertTrue(r["ok"], r)

    def test_wrong_tool(self):
        r = score_fc_item(self._item(), self.catalog, _raw("calculate", {"expression": "1+1"}))
        self.assertFalse(r["ok"])
        self.assertIn("wrong tool", r["error"])

    def test_bad_args(self):
        r = score_fc_item(self._item(), self.catalog, _raw("get_weather", {"city": "Paris"}))
        self.assertFalse(r["ok"])
        self.assertIn("bad args", r["error"])

    def test_no_call_where_needed(self):
        r = score_fc_item(self._item(), self.catalog, _raw(None, None))
        self.assertFalse(r["ok"])
        self.assertIn("no tool call", r["error"])

    def test_execution_failure_hallucinated_value(self):
        # Args pass equality (model copied them exactly) but the tool
        # rejects the invalid date at execution: exec failed.
        item = {"id": "1:call:1", "type": "call", "query": "q", "expected_tool": "get_weather",
                "expected_args": {"city": "Paris", "date": "2026-13-99"},
                "expected_output": None}
        r = score_fc_item(item, self.catalog, _raw("get_weather", {"city": "Paris", "date": "2026-13-99"}))
        self.assertFalse(r["ok"])
        self.assertIn("exec failed", r["error"])

    def test_alien_tool_rejected(self):
        # A tool name that does not exist in the catalog is a wrong tool.
        r = score_fc_item(self._item(), self.catalog, _raw("delete_everything", {}))
        self.assertFalse(r["ok"])
        self.assertIn("wrong tool", r["error"])

    def test_no_call_guard_ok(self):
        item = {"id": "1:nocall:0", "type": "no_call", "query": "q", "expected_tool": None,
                "expected_args": None, "expected_output": None}
        r = score_fc_item(item, self.catalog, _raw(None, None))
        self.assertTrue(r["ok"], r)

    def test_no_call_guard_violated(self):
        item = {"id": "1:nocall:1", "type": "no_call", "query": "q", "expected_tool": None,
                "expected_args": None, "expected_output": None}
        r = score_fc_item(item, self.catalog, _raw("get_weather", {"city": "Paris", "date": "2026-08-14"}))
        self.assertFalse(r["ok"])


class TestScoreGenItem(unittest.TestCase):
    def _raw(self, content: str) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    def test_correct(self):
        r = score_gen_item({"id": "1:gen:0", "expected": "42"}, self._raw("The answer is 42."))
        self.assertTrue(r["ok"], r)

    def test_wrong(self):
        r = score_gen_item({"id": "1:gen:0", "expected": "42"}, self._raw("The answer is 41."))
        self.assertFalse(r["ok"])

    def test_no_number(self):
        r = score_gen_item({"id": "1:gen:0", "expected": "42"}, self._raw("I cannot compute this."))
        self.assertFalse(r["ok"])

    def test_thousands_comma(self):
        r = score_gen_item({"id": "1:gen:0", "expected": "1234"}, self._raw("1,234"))
        self.assertTrue(r["ok"], r)


class TestGenerator(unittest.TestCase):
    def test_deterministic_same_seed(self):
        items_a, catalog_a = generate_fc_items(7)
        items_b, catalog_b = generate_fc_items(7)
        self.assertEqual(items_a, items_b)
        self.assertEqual([t.name for t in catalog_a], [t.name for t in catalog_b])

    def test_different_seed_different_items(self):
        items_a, _ = generate_fc_items(7)
        items_b, _ = generate_fc_items(8)
        self.assertNotEqual([i["id"] for i in items_a], [i["id"] for i in items_b])

    def test_all_items_have_ids(self):
        items, _ = generate_fc_items(7)
        self.assertTrue(all("id" in i for i in items))
        self.assertEqual(len({i["id"] for i in items}), len(items))

    def test_expected_output_matches_tool_execution(self):
        items, catalog = generate_fc_items(7)
        tools = {t.name: t for t in catalog}
        for i in items:
            if i["type"] == "call":
                self.assertEqual(str(tools[i["expected_tool"]].run(i["expected_args"])), str(i["expected_output"]))

    def test_gen_slice_items_have_ids(self):
        items = generate_gen_slice(7)
        self.assertTrue(all("id" in i for i in items))
        self.assertEqual(len({i["id"] for i in items}), len(items))


if __name__ == "__main__":
    unittest.main()
