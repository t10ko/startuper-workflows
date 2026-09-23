#!/usr/bin/env bash
# Install the agentic-workflows system into a target repository.
#
# Usage: ./install.sh [--copy] [--force] [target-repo]
#   (default target: the current directory)
#
#   --copy   copy .agents/ into the target instead of symlinking. A copied
#            tree no longer tracks this repo's updates, and must keep
#            agentic_workflows/ vendored alongside to work — prefer the
#            default symlink mode.
#   --force  replace an existing .agents entry that was not installed by
#            this script (it is backed up first, never deleted).
#
# What it creates in the target:
#   .agents                    -> symlink to this repo's .agents (or --copy)
#   .agents.local.toml         consumer-local config overrides (if absent)
#   .claude/commands           -> ../.agents/workflows   (slash commands)
#   .claude/skills             -> ../.agents/skills      (skills)
#   .claude/rules/<rule>.md    per-file links, auto-loaded ambient rules
#   .claude/agents/<name>.md   per-file links (specialists + skill agents)
#   .zcode/commands            -> ../.agents/workflows
#   .claude/settings.json      merges this system's hook wiring + permissions
#
# Idempotent: re-running repairs missing links and re-merges settings.
# A backup of any settings.json it modifies is kept alongside.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="symlink"
FORCE=0
TARGET=""

for arg in "$@"; do
  case "$arg" in
    --copy) MODE="copy" ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) if [ -z "$TARGET" ]; then TARGET="$arg"; else echo "unexpected argument: $arg" >&2; exit 2; fi ;;
  esac
done
TARGET="${TARGET:-$PWD}"
TARGET="$(cd "$TARGET" && pwd)"

[ -d "$SRC/.agents" ] || { echo "error: $SRC/.agents not found; run from a checkout of this repo" >&2; exit 1; }
command -v python3 >/dev/null || { echo "error: python3 is required (hooks and scripts run on it)" >&2; exit 1; }

echo "Installing agentic-workflows"
echo "  source: $SRC"
echo "  target: $TARGET"
echo "  mode:   $MODE"

# --- .agents tree ---------------------------------------------------------
# Self-hosting (target == this repo) already has the real .agents tree.
if [ "$TARGET" != "$SRC" ]; then
  if [ -L "$TARGET/.agents" ]; then
    ln -sfn "$SRC/.agents" "$TARGET/.agents"
    echo "  .agents        -> $SRC/.agents (relinked)"
  elif [ -e "$TARGET/.agents" ]; then
    if [ "$MODE" = "copy" ]; then
      echo "  .agents        exists and is a real directory; --copy merge skipped (leaving as-is)"
    elif [ "$FORCE" -eq 1 ]; then
      STAMP="$(date +%Y%m%d-%H%M%S)"
      mv "$TARGET/.agents" "$TARGET/.agents.pre-agentic-workflows.$STAMP"
      echo "  .agents        backed up to .agents.pre-agentic-workflows.$STAMP, replacing with symlink"
      ln -s "$SRC/.agents" "$TARGET/.agents"
    else
      echo "  .agents        exists and is not ours; refusing (use --force to back it up and replace)" >&2
      exit 1
    fi
  else
    if [ "$MODE" = "copy" ]; then
      cp -R "$SRC/.agents" "$TARGET/.agents"
      echo "  .agents        copied"
    else
      ln -s "$SRC/.agents" "$TARGET/.agents"
      echo "  .agents        -> $SRC/.agents"
    fi
  fi
fi

# --- host projections -----------------------------------------------------
mkdir -p "$TARGET/.claude" "$TARGET/.zcode"

ln -sfn ../.agents/workflows "$TARGET/.claude/commands"
ln -sfn ../.agents/workflows "$TARGET/.zcode/commands"
if [ ! -e "$TARGET/.claude/skills" ] || [ -L "$TARGET/.claude/skills" ]; then
  ln -sfn ../.agents/skills "$TARGET/.claude/skills"
else
  echo "  .claude/skills exists and is not a symlink; leaving as-is" >&2
fi
echo "  .claude/commands, .claude/skills, .zcode/commands linked"

# rules: per-file links, excluding the inventory README and the
# block-git-mutations deny-list companion (deliberately NOT auto-loaded;
# workflows read it explicitly before git-mutating steps).
mkdir -p "$TARGET/.claude/rules"
for src_rule in "$SRC"/.agents/rules/*.md; do
  name="$(basename "$src_rule")"
  case "$name" in
    README.md|block-git-mutations.md) continue ;;
  esac
  ln -sfn "../../.agents/rules/$name" "$TARGET/.claude/rules/$name"
done
# prune stale links: projections whose canonical rule file no longer exists
for link in "$TARGET"/.claude/rules/*.md; do
  [ -L "$link" ] || continue
  if [ ! -e "$link" ]; then rm "$link"; echo "  pruned stale rule link $(basename "$link")"; fi
done
echo "  .claude/rules  linked ($(ls "$TARGET/.claude/rules" | wc -l | tr -d ' ') rules)"

# agents: specialists, skill-private agents (<skill>-<agent> naming), and
# the architect workflow projected as a dispatchable agent.
mkdir -p "$TARGET/.claude/agents"
for src_agent in "$SRC"/.agents/specialists/*.md; do
  name="$(basename "$src_agent")"
  ln -sfn "../../.agents/specialists/$name" "$TARGET/.claude/agents/$name"
done
for skill_agents_dir in "$SRC"/.agents/skills/*/agents; do
  [ -d "$skill_agents_dir" ] || continue
  skill="$(basename "$(dirname "$skill_agents_dir")")"
  for src_agent in "$skill_agents_dir"/*.md; do
    name="$(basename "$src_agent")"
    ln -sfn "../../.agents/skills/$skill/agents/$name" "$TARGET/.claude/agents/$skill-$name"
  done
done
if [ -f "$SRC/.agents/workflows/architect.md" ]; then
  ln -sfn "../../.agents/workflows/architect.md" "$TARGET/.claude/agents/architect.md"
fi
for link in "$TARGET"/.claude/agents/*.md; do
  [ -L "$link" ] || continue
  if [ ! -e "$link" ]; then rm "$link"; echo "  pruned stale agent link $(basename "$link")"; fi
done
echo "  .claude/agents linked ($(ls "$TARGET/.claude/agents" | wc -l | tr -d ' ') agents)"

# --- consumer-local config ------------------------------------------------
if [ ! -f "$TARGET/.agents.local.toml" ]; then
  cat > "$TARGET/.agents.local.toml" <<'TOML'
# Consumer-local overrides for the agentic-workflows system.
# This file is read INSTEAD of .agents/config.toml when present, and is
# machine-local: it lives outside any symlinked .agents tree on purpose.

# [worktrees]
# max_concurrent = 5

# [project]
# verify_cmd = "make verify"

# [spike]
# fixture = "path/to/fixture"
TOML
  echo "  .agents.local.toml written (uncomment and adjust as needed)"
else
  echo "  .agents.local.toml already present; left as-is"
fi

# --- settings.json merge --------------------------------------------------
python3 "$SRC/.agents/scripts/install_settings_merge.py" \
  --source "$SRC/.claude/settings.json" --target "$TARGET/.claude/settings.json"

echo
echo "Done. Next steps:"
echo "  1. Review $TARGET/.claude/settings.json (a .bak was kept if it changed)."
echo "  2. Set [project] verify_cmd in .agents.local.toml to your project's verify command."
echo "  3. For PR landing: authenticate once with 'gh auth login'."
echo "  4. Restart your Claude Code / ZCode session so projections are picked up."
