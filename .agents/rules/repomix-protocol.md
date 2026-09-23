# Codebase Structural Analysis & Repomix Protocol

- **Broad Codebase Analysis:** When analyzing multi-module dependencies, cross-system architectural patterns, or conducting broad codebase onboarding, use the `pack_codebase` MCP tool.
- **Tree-sitter Compression Invariant:** ALWAYS ensure the `compress` parameter is set to `true` (or rely on `repomix.config.json` defaults) to extract Tree-sitter AST structures and prevent context overflow.
- **Output Storage:** Save or reference repomix dumps inside `tmp/repomix-output.xml` (or `tmp/`) to keep the working tree clean.
- **Targeted Search Priority:** For single-file edits, localized bug fixes, or specific symbol lookups, use `rg` (ripgrep) and `view_file` instead of full codebase packing to minimize token usage.
