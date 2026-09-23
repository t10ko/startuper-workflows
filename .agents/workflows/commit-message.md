---
description: Return conventional commit message
---

Generate a professional Conventional Commit message for the current changes.

- **Structure**: <type>(<scope>): <summary> followed by a list of bulleted changes. Each bullet point should be a one-liner describing a single change.
- **Constraints**:
  - NEVER include file paths or directory names.
  - Use the imperative mood (e.g., "Add feature," not "Added feature").
  - Focus on the functional intent and "why" of the changes.
- **Scope**: Identify the specific logic or UI component being modified (e.g., logic, ui, deps, docs).
- **Format**: Provide ONLY the commit message inside a single code block.
- **Subagents**: For broad staged diffs only, use
  `.agents/AGENTS.md` with internal diff scouts for
  independent change clusters. Lead chooses the final theme; final output stays
  one fenced code block.
