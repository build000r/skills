#!/usr/bin/env python3
"""Render configured operator availability JSON as concise slot choices."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _load_payload(path: str | None) -> dict[str, Any]:
    try:
        if path:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            if sys.stdin.isatty():
                raise ValueError("pass a JSON file path or pipe availability JSON on stdin")
            payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("error: availability payload must be a JSON object")
    return payload


def _slots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("slots"), list):
        return [slot for slot in data["slots"] if isinstance(slot, dict)]
    slots = payload.get("slots")
    if isinstance(slots, list):
        return [slot for slot in slots if isinstance(slot, dict)]
    return []


def _is_available(slot: dict[str, Any]) -> bool:
    return slot.get("available", True) is not False


def _date_key(slot: dict[str, Any]) -> tuple[str, str]:
    date = str(slot.get("date") or slot.get("day") or slot.get("starts_at") or "")
    label = str(slot.get("slot") or slot.get("label") or slot.get("start") or "")
    return date, label


def _display(slot: dict[str, Any], timezone: str) -> str:
    date = slot.get("date") or slot.get("day")
    day = slot.get("dayOfWeek") or slot.get("weekday")
    label = slot.get("label") or slot.get("slot")
    starts_at = slot.get("starts_at") or slot.get("start")
    ends_at = slot.get("ends_at") or slot.get("end")
    price = slot.get("priceDisplay") or slot.get("price_display")
    if price is None and slot.get("price") is not None:
        raw_price = str(slot["price"])
        price = raw_price if raw_price.startswith("$") else f"${raw_price}"

    parts: list[str] = []
    if date:
        date_text = str(date)
        if day:
            date_text = f"{date_text} ({str(day).title()})"
        parts.append(date_text)
    if starts_at and ends_at:
        parts.append(f"{starts_at}-{ends_at}")
    elif starts_at:
        parts.append(str(starts_at))
    elif label:
        parts.append(str(label))
    if timezone:
        parts.append(timezone)
    if price:
        parts.append(str(price))
    return " | ".join(parts) if parts else json.dumps(slot, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render availability JSON into numbered booking slot choices."
    )
    parser.add_argument("path", nargs="?", help="Availability JSON file. Reads stdin when omitted.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum slots to print.")
    parser.add_argument("--timezone", default="", help="Timezone label to include in output.")
    args = parser.parse_args()

    payload = _load_payload(args.path)
    choices = [slot for slot in _slots(payload) if _is_available(slot)]
    choices.sort(key=_date_key)
    if not choices:
        print("No available slots found.")
        return 1

    for index, slot in enumerate(choices[: max(args.limit, 1)], 1):
        print(f"{index}. {_display(slot, args.timezone)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
