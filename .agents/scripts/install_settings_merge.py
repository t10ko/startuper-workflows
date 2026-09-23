#!/usr/bin/env python3
"""Merge the agentic-workflows hook wiring into a target settings.json.

Owns exactly these entries, identified by their command strings:
- every hook whose command references `.agents/hooks/<name>.py`
- the response-contract re-injection (command references
  `.agents/rules/response-contract.md`)

Those entries are removed from the target before ours are appended, so
re-running this script repairs and updates instead of duplicating. The
target's other hooks, permissions, and settings are untouched. A backup of
the previous file is kept as settings.json.bak.<timestamp> whenever content
changes. permissions.deny lists are unioned.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

OWNED_MARKERS = (".agents/hooks/", ".agents/rules/response-contract.md")


def _is_owned(hook_entry: dict) -> bool:
    command = str(hook_entry.get("command", ""))
    return any(marker in command for marker in OWNED_MARKERS)


def _strip_owned(settings: dict) -> None:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            entries = group.get("hooks")
            if isinstance(entries, list):
                kept = [e for e in entries if not (isinstance(e, dict) and _is_owned(e))]
                if kept:
                    group = {**group, "hooks": kept}
                    kept_groups.append(group)
                # a group whose entries were all ours is dropped entirely
            else:
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]


def _take_owned(source: dict) -> dict:
    hooks = source.get("hooks", {})
    if not isinstance(hooks, dict):
        return {}
    return {event: groups for event, groups in hooks.items() if isinstance(groups, list)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    target_path = args.target
    original_text = (
        target_path.read_text(encoding="utf-8") if target_path.exists() else None
    )
    target = json.loads(original_text) if original_text is not None else {}

    _strip_owned(target)
    owned_hooks = _take_owned(source)
    if owned_hooks:
        hooks = target.setdefault("hooks", {})
        for event, groups in owned_hooks.items():
            existing = hooks.setdefault(event, [])
            existing.extend(json.loads(json.dumps(groups)))

    deny = source.get("permissions", {}).get("deny", [])
    if deny:
        existing_deny = target.setdefault("permissions", {}).setdefault("deny", [])
        for entry in deny:
            if entry not in existing_deny:
                existing_deny.append(entry)

    merged_text = json.dumps(target, indent=2) + "\n"
    if merged_text == original_text:
        print(f"  settings already merged in {target_path.as_posix()}")
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if original_text is not None:
        backup = target_path.with_name(
            f"{target_path.name}.bak.{time.strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(target_path, backup)
        note = f" (previous version kept at {backup.name})"
    else:
        note = ""
    target_path.write_text(merged_text, encoding="utf-8")
    print(f"  settings merged into {target_path.as_posix()}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
