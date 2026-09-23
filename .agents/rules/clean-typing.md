---
trigger: glob
globs: "**/*.py"
paths:
  - "**/*.py"
---

# Clean Typing Rules

These rules enforce clean, honest typing as required by
the active review workflow.

- Do not use `Any` in project source.
- Do not use `object` as a type hint in project source.
- Do not use `cast(...)` to hide Pyright or Ruff issues.
- Fix actual producer/consumer contracts instead of lying to type checker.
- If runtime value is `dict`, annotate it as `dict[...]`; if it must be model,
  construct model with `model_validate(...)` or normal initializer.
- Use `pathlib.Path`; do not use `os.path` or `str` path handling in project source.
- Do not use `hasattr(x, "model_dump")` as a guard.
- Validate LLM tool outputs with dedicated Pydantic DTOs and `model_validate(...)`.
- Prefer `Protocol`, `TypedDict`, generics, or concrete model types over loose
  unions that blur contract boundaries.
- Do not leave Pyright suppressions or type ignores in place when proper typing
  fix is possible.
