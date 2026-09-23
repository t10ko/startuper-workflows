"""Shared JSON value types (stdlib-only replacement for the app's src.types)."""

from __future__ import annotations

type JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]

type JSONDict = dict[str, "JSONValue"]

type PrimitiveValue = None | bool | int | float | str
