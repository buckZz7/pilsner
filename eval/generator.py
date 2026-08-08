"""Synthetic function-calling eval generator.

The anti-contamination core: every eval item is *generated* from an
invented tool catalog with a deterministic expected result. Seeds rotate
per eval round, so no submission can memorize the set — it literally does
not exist until the round starts. Independent of any model or base:
catalogs and queries are invented here.

Item types:
  - "call": a query that one tool can answer. Expected = (tool, args).
  - "no_call": a query NO tool can answer. Expected = no tool call.
             (the hallucination guard)
Difficulty is controlled by catalog size (distractors present) and
whether the query needs careful parameter extraction.
"""
from __future__ import annotations

import json
import random
from typing import Any

from .tools import ToolSpec, build_catalog

_CITIES = ["Austin", "Paris", "Tokyo", "Berlin", "Nairobi", "Lima", "Oslo", "Cairo"]
_DATES = ["2026-08-14", "2026-08-15", "2026-09-01", "2026-09-02", "2026-10-05"]
_TICKERS = ["AAPL", "TSLA", "MSFT", "NVDA"]
_TABLES = ["customers", "orders"]
_FIRST = ["Ana", "Ben", "Cara", "Diego", "Elena", "Felix"]
_LAST = ["Rivera", "Kim", "Okafor", "Silva", "Novak", "Larsson"]


def _weather_query(rng: random.Random) -> tuple[str, dict]:
    city, date = rng.choice(_CITIES), rng.choice(_DATES)
    return (
        f"What is the weather in {city} on {date}?",
        {"city": city, "date": date},
    )


def _calc_query(rng: random.Random) -> tuple[str, dict]:
    a, b = rng.randint(10, 99), rng.randint(2, 9)
    op = rng.choice(["+", "-", "*", "/"])
    expr = f"{a} {op} {b}"
    return (f"Calculate {expr}.", {"expression": expr})


def _flight_query(rng: random.Random) -> tuple[str, dict]:
    o, d = rng.sample(_CITIES, 2)
    date = rng.choice(_DATES)
    return (
        f"Find flights from {o} to {d} on {date}.",
        {"origin": o, "destination": d, "date": date},
    )


def _email_query(rng: random.Random) -> tuple[str, dict]:
    name = f"{rng.choice(_FIRST).lower()}@{rng.choice(_LAST).lower()}.com"
    subject = "Project update"
    body = "Please review the latest draft."
    return (
        f"Send an email to {name} with subject '{subject}' and body '{body}'.",
        {"to": name, "subject": subject, "body": body},
    )


def _db_query(rng: random.Random) -> tuple[str, dict]:
    table = rng.choice(_TABLES)
    cols = rng.sample(["id", "name", "city", "total"], k=rng.randint(1, 2))
    filt = "total > 100"
    return (
        f"Query the {table} table for columns {', '.join(cols)} where {filt}.",
        {"table": table, "columns": cols, "filter": filt},
    )


def _note_query(rng: random.Random) -> tuple[str, dict]:
    text = f"Remember to {rng.choice(['call Dana', 'buy milk', 'review PR', 'book venue'])}"
    return (f"Add a note: {text}", {"text": text})


def _stock_query(rng: random.Random) -> tuple[str, dict]:
    t = rng.choice(_TICKERS)
    return (f"What is the current price of {t}?", {"ticker": t})


def _no_call_queries(rng: random.Random) -> list[tuple[str, None]]:
    return [
        (f"Write a haiku about {rng.choice(_CITIES)}.", None),
        ("Who won the 2026 World Cup?", None),
        ("Tell me a recipe for pasta.", None),
        (f"Translate 'hello' into {rng.choice(['French', 'Swahili', 'Japanese'])}.", None),
        ("What is the meaning of life?", None),
    ]


_QUERY_BUILDERS = [
    _weather_query,
    _calc_query,
    _flight_query,
    _email_query,
    _db_query,
    _note_query,
    _stock_query,
]


def generate_fc_items(seed: int, n_call: int = 80, n_no_call: int = 20, catalog_kind: str = "mixed") -> tuple[list[dict], list[ToolSpec]]:
    """Generate a seeded eval set. Returns (items, catalog)."""
    rng = random.Random(seed)
    catalog = build_catalog(catalog_kind)
    items: list[dict] = []

    for _ in range(n_call):
        builder = rng.choice(_QUERY_BUILDERS)
        query, expected_args = builder(rng)
        tool = _catalog_tool_for(catalog, builder)
        items.append(
            {
                "id": f"{seed}:call:{len(items)}",
                "type": "call",
                "query": query,
                "expected_tool": tool.name,
                "expected_args": expected_args,
                "expected_output": _safe_output(tool, expected_args),
            }
        )

    for query, _ in rng.sample(_no_call_queries(rng), min(n_no_call, 5)):
        items.append(
            {
                "id": f"{seed}:nocall:{len(items)}",
                "type": "no_call",
                "query": query,
                "expected_tool": None,
                "expected_args": None,
                "expected_output": None,
            }
        )

    rng.shuffle(items)
    return items, catalog


_BUILDER_TO_TOOL = {
    "_weather_query": "get_weather",
    "_calc_query": "calculate",
    "_flight_query": "search_flights",
    "_email_query": "send_email",
    "_db_query": "db_query",
    "_note_query": "add_note",
    "_stock_query": "get_stock_price",
}


def _catalog_tool_for(catalog: list[ToolSpec], builder) -> ToolSpec:
    tool_name = _BUILDER_TO_TOOL[builder.__name__]
    return next(t for t in catalog if t.name == tool_name)


def _safe_output(tool: ToolSpec, args: dict) -> Any:
    try:
        return tool.run(dict(args))
    except Exception:
        return None


def save_items(items: list[dict], catalog: list[ToolSpec], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "seed": items[0]["id"].split(":")[0],
                "catalog": [t.to_openai() for t in catalog],
                "items": items,
            },
            f,
            indent=2,
        )
