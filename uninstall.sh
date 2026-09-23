#!/usr/bin/env bash
# Uninstall the agentic-workflows system from a target repository.
#
# Usage: ./uninstall.sh [target-repo]
#
# Removes the projections, the settings.json entries this system owns, and
# (only if it is a symlink this script created) the .agents link. A --copy
# installed .agents tree and .agents.local.toml are left in place — delete
# those by hand after reviewing.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""
for arg in "$@"; do
  case "$arg" in
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
TARGET="${TARGET:-$PWD}"
TARGET="$(cd "$TARGET" && pwd)"

echo "Uninstalling agentic-workflows from $TARGET"

[ -d "$SRC/.agents" ] || { echo "error: run from a checkout of this repo" >&2; exit 1; }

if [ -f "$TARGET/.claude/settings.json" ]; then
  python3 - "$TARGET/.claude/settings.json" <<'PY'
import json, shutil, sys, time
from pathlib import Path
path = Path(sys.argv[1])
settings = json.loads(path.read_text(encoding="utf-8"))
markers = (".agents/hooks/", ".agents/rules/response-contract.md")
hooks = settings.get("hooks", {})
if isinstance(hooks, dict):
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            entries = group.get("hooks", []) if isinstance(group, dict) else []
            filtered = [e for e in entries if not (isinstance(e, dict) and any(m in str(e.get("command", "")) for m in markers))]
            if filtered:
                group = {**group, "hooks": filtered}
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
if isinstance(settings.get("permissions"), dict):
    pass  # deny entries (secret-file reads) are generic safety rails; left on uninstall
backup = path.with_name(f"{path.name}.bak.{time.strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(path, backup)
path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
print(f"  settings cleaned (previous version at {backup.name})")
PY
fi

for link in .claude/commands .claude/skills .zcode/commands; do
  if [ -L "$TARGET/$link" ]; then rm "$TARGET/$link"; echo "  removed $link"; fi
done
for dir in .claude/rules .claude/agents; do
  if [ -d "$TARGET/$dir" ]; then
    removed=0
    for f in "$TARGET/$dir"/*; do
      [ -L "$f" ] || continue
      dest="$(readlink "$f")"
      case "$dest" in
        *.agents/rules/*|*.agents/specialists/*|*.agents/skills/*|*.agents/workflows/*) rm "$f"; removed=$((removed+1)) ;;
      esac
    done
    [ "$removed" -gt 0 ] && echo "  removed $removed links from $dir"
    rmdir "$TARGET/$dir" 2>/dev/null || true
  fi
done

if [ -L "$TARGET/.agents" ]; then
  rm "$TARGET/.agents"
  echo "  removed .agents symlink"
else
  [ -d "$TARGET/.agents" ] && echo "  .agents is a real directory (a --copy install or your own tree); left in place"
fi
echo "  .agents.local.toml left in place (delete by hand if unwanted)"
echo "Done."
