"""Shared JSON value types (stdlib-only replacement for the app's src.types)."""

from __future__ import annotations

from typing import TypeAlias, Union

JSONValue: TypeAlias = Union[
    None,
    bool,
    int,
    float,
    str,
    list["JSONValue"],
    dict[str, "JSONValue"],
]

JSONDict: TypeAlias = dict[str, "JSONValue"]

PrimitiveValue: TypeAlias = Union[None, bool, int, float, str]
