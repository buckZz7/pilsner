"""Deterministic mock APIs used for execution verification.

Every tool validates its arguments and raises ValueError on bad input,
so a hallucinated parameter FAILS execution. Results are deterministic:
the same arguments always produce the same output, which is what makes
result-equality scoring possible without any judge.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Any


class ToolSpec:
    """An OpenAI-style tool definition + its Python implementation."""

    def __init__(self, name: str, description: str, parameters: dict, fn) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, args: dict) -> Any:
        """Execute with validation. Raises on bad args."""
        return self.fn(**args)


def _fmt_date(d: str) -> str:
    """Validate YYYY-MM-DD and return it; raises on bad format."""
    _dt.date.fromisoformat(d)
    return d


def _make_tool(name: str, desc: str, props: dict, required: list[str], fn) -> ToolSpec:
    return ToolSpec(name, desc, {"type": "object", "properties": props, "required": required}, fn)


def build_catalog(kind: str = "mixed") -> list[ToolSpec]:
    """Build a deterministic tool catalog. `kind` selects the tool set
    so different eval rounds can sample different catalogs."""
    weather = _make_tool(
        "get_weather",
        "Get the current weather for a city on a date.",
        {
            "city": {"type": "string", "description": "City name, e.g. Austin"},
            "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
        },
        ["city", "date"],
        lambda city, date: f"weather({city},{_fmt_date(date)}): 24C, sunny",
    )

    calc = _make_tool(
        "calculate",
        "Evaluate a numeric expression. Use only + - * / ( ) and numbers.",
        {"expression": {"type": "string", "description": "Arithmetic expression"}},
        ["expression"],
        lambda expression: _safe_eval(expression),
    )

    flights = _make_tool(
        "search_flights",
        "Search available flights between two cities on a date.",
        {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
        },
        ["origin", "destination", "date"],
        lambda origin, destination, date: json.dumps(
            {"flights": [{"flight": "UA123", "price_usd": 320, "date": _fmt_date(date)}]}
        ),
    )

    email = _make_tool(
        "send_email",
        "Send an email to a recipient.",
        {
            "to": {"type": "string", "format": "email"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        ["to", "subject", "body"],
        lambda to, subject, body: (
            json.dumps({"ok": True, "to": to, "subject": subject})
            if "@" in to and subject and body
            else (_ for _ in ()).throw(ValueError(f"invalid email: {to!r}"))
        ),
    )

    db = _make_tool(
        "db_query",
        "Run a SQL query against the sales database.",
        {
            "table": {"type": "string", "enum": ["customers", "orders"]},
            "columns": {"type": "array", "items": {"type": "string"}},
            "filter": {"type": "string"},
        },
        ["table", "columns", "filter"],
        lambda table, columns, filter: json.dumps(
            {"rows": [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Globex"}]}
        ),
    )

    notes = _make_tool(
        "add_note",
        "Add a note to the user's notebook.",
        {"text": {"type": "string"}},
        ["text"],
        lambda text: json.dumps({"ok": True, "stored": len(text) > 0})
        if text
        else (_ for _ in ()).throw(ValueError("empty note")),
    )

    stock = _make_tool(
        "get_stock_price",
        "Get the current stock price of a ticker symbol.",
        {"ticker": {"type": "string"}},
        ["ticker"],
        lambda ticker: f"price({ticker.upper()}): 145.30",
    )

    catalogs = {
        "mixed": [weather, calc, flights, email, db, notes, stock],
        "travel": [weather, flights, notes, stock],
        "office": [email, db, notes, calc],
        "finance": [stock, calc, db, weather],
    }
    return catalogs.get(kind, catalogs["mixed"])


def _safe_eval(expr: str) -> float:
    """Evaluate a restricted arithmetic expression. Raises on anything else."""
    expr = expr.strip()
    if not re.fullmatch(r"[-+*/()0-9.\s]+", expr):
        raise ValueError(f"unsafe expression: {expr!r}")
    return float(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 - regex-whitelisted
