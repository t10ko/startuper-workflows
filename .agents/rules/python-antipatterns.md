---
trigger: glob
globs: "**/*.py"
paths:
  - "**/*.py"
---

# Python Antipatterns & Best Fixes

This document catalogs common antipatterns observed during development (especially during `ruff`/`pyright` hardening) and outlines project-preferred solutions.

## 0. The "Best Solution" Invariant (AGENTS.md Rule 14) [Repeated: 3 times]
**Principle:** "Best Fix" does NOT mean a surface-level patch. It means identifying why the type system or test failed at the source and refactoring the producer or the underlying model to support a strictly typed flow.
**Mistake Repeated:** Using `model_dump()`, `isinstance(raw, dict)`, or `# type: ignore` shims to satisfy a loose dictionary field or invariance mismatch instead of hardening the destination model or using a clean boundary cast. Dumping a validated provider/client DTO just so an internal helper can read raw keys is the same failure. **Fix the underlying stuff.**

## 0.1 Boundary Invariant (THE "FAIL-FAST" RULE)
**Principle:** Business logic MUST only operate on strongly typed models. Validation MUST happen at the absolute edge of a system (ingress).
**Mistake Repeated:** Calling `super().append(raw_dict)` before validating it. This poisons the internal state with un-validated data.
**Mistake Repeated:** Adding `if isinstance(x, dict)` branches in helper functions to "handle" raw data that should have been validated upstream.
**Best Fix:** Validate IMMEDIATELY at the entry point of a method or function. If the data is invalid, raise `ValidationError` and stop. Never pass raw dictionaries deep into internal helpers.

## 1. Cast & Type Escapes (Rule 1, 2, 14, 15)
**Symptoms:**
- `cast(ProperType, getattr(...))`, `cast("dict[str, Any]", payload)`, `cast(Any, x)`
- `cast(dict[str, object], getattr(...))`, `cast(QAReviewerProtocol, qa_reviewer)`
- `# type: ignore[arg-type]`, `# pyright: ignore`, `# noqa`
- `__hash__ = None  # type: ignore[assignment]` on mutable custom containers
**Why it's bad:** Hides root cause, disables static analysis, masks bad data flow. String literals inside `cast` are fragile. `cast(Any)` strictly prohibited (AGENTS.md). Ignores hide regressions and stifle refactoring.
**Best Fix:** Define `Protocol`, `TypedDict`, or Pydantic `BaseModel` for shape validation. Fix producer return types instead of lying at call sites. Use `Model.model_validate()` for loose boundaries. Never use string literals or `Any` as target. If an inspected third-party SDK signature is structurally incompatible with the internal protocol, keep exactly one concrete boundary cast with a `LEGIT_BOUNDARY` comment. Use ignore comments ONLY as last resort; keep them single-line, rule-specific, and documented. For mutable custom containers, prefer an explicit `__hash__()` method that raises `TypeError` over a suppressed `__hash__ = None` assignment.

## 2. Abstraction Overhead (Rule 3, 7)
**Symptoms:**
- `Mapping[str, ...]` or `Sequence[int]` instead of `dict` or `list`
- `dict(existing_dict)`, `{**dict(chunk), "id": 1}`, `normalized.append(dict(item))`
**Why it's bad:** In our repo, generic ABCs (`Mapping`, `Sequence`) add cognitive load, trigger invariance errors, and cause unnecessary `dict()` wrapping.
**Best Fix:** Use `dict` and `list` exclusively for structural hints. Other `collections.abc` (`Callable`, `Awaitable`, `Iterable`) are fine. Pass dictionaries directly; use `.copy()` if an explicit clone is required.

## 3. Defensive String & Path Handling (Rule 4, 5, 13)
**Symptoms:**
- `str(path)` (always use `path.as_posix()`), `str(project_folder / "assets")`
- `str(x or "")`, `Path(str(base))`, `str(choice.get("name", "")).lower()`
- `if isinstance(path, str): ...` then constructing `Path(path)`
- Excessive `if value.strip():` or `if (id and id.strip()):` inside business logic (masks loose boundary validation).
**Why it's bad:** `str(path)` leaks platform-specific separators (`\` on Windows), breaking portability in JSON/logs. Defensive `str()` and `isinstance` branching mask contract violations and `None` states. Excessive `.strip()` calls to check for empty/whitespace strings indicate that boundary validation failed to enforce strict `str | None` contracts, allowing whitespace strings to leak inward.
**Best Fix:** Use `path.as_posix()` only at conversion boundaries. Keep objects as `Path` or strong types until the system edge. Fix producers to return `Path` consistently. Use `pathlib` methods over string hacks.

## 3.1 Project Asset Path Relativity
**Principle:** Project-owned asset paths MUST be project-relative everywhere they are stored, passed through domain DTOs, exposed to LLM/HITL/API contracts, or written to manifests. Only `project_folder` is absolute. Absolute filesystem paths are allowed only as ephemeral runtime IO values after resolving a relative project path against `project_folder`.
**Symptoms:**
- `asset_path if asset_path.is_absolute() else project_folder / asset_path`
- `if requirement.path.is_absolute(): ... else: project_folder / requirement.path`
- Persisting discovered asset paths before normalizing them with a strict project-relative contract.
**Why it's bad:** Accepting both absolute and relative project asset paths creates a dual contract. It leaks machine-specific paths into portable project data, forces defensive `is_absolute()` branches downstream, and hides the real producer that emitted the wrong shape.
**Best Fix:** Normalize or reject at the boundary. Persist and pass project assets as relative `Path` values rooted at `project_folder`; resolve to absolute paths exactly at the filesystem IO boundary. If an external import source must be absolute, model it as a separate source-path field rather than overloading a project asset field.

## 4. Loose Type Placeholders (Rule 11, 12)
**Symptoms:**
- `chunks: list[dict[str, Any]]`, `dict[str, object]`, `Awaitable[object]`
- `project_context: Mapping[str, Any] | None`, `resolved_params: dict[str, object]`
- Protocol methods returning `object` for structured payloads
- `data: json.JSONValue` passed into business logic or function signatures beyond the raw parse boundary
- Replacing `JSONDict` or `JSONValue` with `dict[str, object]` to make Pyright quiet.
- `model_validator(mode="before")` signatures using `object` just to pre-check fields that the DTO already types.
**Why it's bad:** Disables analysis, spreads untyped escape hatches. `object` is just `Any` in stricter clothing; still pushes ambiguity downstream, forcing `getattr` or `cast` to recover fields. `json.JSONValue` is a recursive union — working with it in business logic requires constant `isinstance` narrowing, which is the same escape hatch as `Any`.
**Fix:** Define structure at the first boundary (parsing/deserialization) and pass precise types. Prefer Pydantic `BaseModel` over `TypedDict` for its superior validation, runtime checks, and metadata access. `json.JSONValue` is a last resort — valid only at the raw deserialization boundary (the output of `json.loads()` before shape validation). Never pass `JSONValue` into business logic; it requires constant `isinstance` narrowing and defeats static analysis just as `Any` does. `JSONDict` and `dict[str, object]` are not interchangeable: keep `JSONDict` or a named alias at true raw JSON/transport boundaries, and use DTO/domain models everywhere else. **Rule 4.1: If it's in logic, it's not a JSONValue. Rule 4.2: Replacing JSONDict with dict[str, object] is always a regression.**
Do not add raw `object` pre-validators when Pydantic field types already enforce the contract; strengthen the field type or adapter boundary instead.
**Rule 4.3: LLM Tool Schema Boundary Validation**: `json.to_llm_schema(Model)` returns raw JSON schema data. `ToolDefinition.input_schema` must receive `FunctionParametersSchema.model_validate(json.to_llm_schema(Model))` at the tool-definition boundary. Do not pass `JSONDict` schemas directly, cast them, or loosen `ToolDefinition`; validate once where the raw schema enters the LLM tool contract.

## 5. Attribute & Validation Crutches (Rule 6, 19) [Repeated: 1 time]
**Symptoms:**
- `getattr(decision, "path", None)`, `hasattr(task, "status")`, `getattr(record, "id", "")`
- `raw.get("k") if isinstance(raw, dict) else {}`, `packets = p if isinstance(p, list) else []`
**Why it's bad:** Circumvents static analysis. Signifies operation on untyped objects. Ternary fallback validation clutters business logic with manual data repair.
**Best Fix:** Strongly type via `Protocol` or `BaseModel`. Use `isinstance()` for domain-logic branching, not defensive recovery. Use module-level `TypeAdapter` or Pydantic DTOs to validate entire shapes in one step. If dynamic property access is architecturally required (e.g., in a flexible template system), ensure the object is a validated `BaseModel` and use its metadata (e.g., `model_fields`, `model_fields_set`) to guide access instead of bare `getattr` on unknown objects.

## 6. Contract & State Hygiene (Rule 8, 18, 20)
**Symptoms:**
- `status: str = Field(description="APPROVED or REJECTED")`
- `def normalize(title: str | None = None): title = title or ""`, `meta = metadata or {}`
- `event_keys = set(payload.context_keys)` where model field is a `list`
**Why it's bad:** Unenforced constraints allow invalid states. Repairing `None` inside functions spreads `Optional` bloat and manual cleanup downstream. Redundant conversion inside logic leaks model inaccuracy.
**Best Fix:** Use `Literal` or `Enum` for constraints. Make parameters required if the function needs them to work. Type Pydantic fields exactly as used in logic (e.g., `set[str]`). Optional HITL/history prompt context may be normalized into concrete schema fields only at the LLM request DTO boundary; keep the conversion there and classify it in postcheck.

## 7. Performance & Tooling (Rule 9, 17)
**Symptoms:**
- Manual recursive `to_dict` via `isinstance(v, (str, int...))`
- `TypeAdapter(Type).validate_python(x)` inside loops or function bodies
**Why it's bad:** Manual serialization is error-prone. Pydantic V2 `TypeAdapter` instantiation is computationally expensive (Rust/schema rebuild); doing it inline creates severe bottlenecks.
**Best Fix:** Use `TypeAdapter.model_dump(mode="json")`. Define `TypeAdapter` ONCE at module level (e.g., `ListAdapter = TypeAdapter(list[Model])`) and reuse.

## 8. Modular & Signature Hygiene (Rule 10, 16, 21, 22, 23) [Repeated: 3 times]
**Symptoms:**
- `try: import pkg except ImportError: ...` (for required deps)
- `from .foo import bar as bar` (self-alias re-export hack)
- Complex types (e.g., `dict[str, Callable[..., Coroutine[...]]]`) repeated in signatures
- `# noqa: E402` or local imports used to hide bootstrap-before-import ordering
- Wrapper APIs typed with `**kwargs: object` instead of explicit parameters copied from the strict wrapped API
- Duplicate declarations such as two `as_int()` or `as_float()` definitions in the same module
- Decomposed module parts scattered as prefixed siblings, e.g. `sdk_tool_actions.py`, `sdk_tool_definitions.py`, next to unrelated files
**Why it's bad:** Optional imports mask env issues. Re-export hacks confuse intent. Signature bloat (>40 chars) hides business logic and leads to divergence. Loose `**kwargs: object` wrappers push type errors into strict underlying APIs like `json.dumps()`. Duplicate declarations hide the active implementation and create Pyright redeclaration errors. Flat prefixed split files hide module ownership and make the parent package an unstructured junk drawer.
**Best Fix:** Fail fast on missing deps. Use explicit assignment for re-exports (`Error = std_json.JSONDecodeError`) or `__init__.py` with `__all__`. Use `TypeAlias` or `Protocol` (for complex callables) for any repeated/complex expression. Wrapper functions around strict APIs must expose explicit typed parameters matching the wrapped API instead of catch-all `**kwargs: object`. Remove duplicate declarations; keep one public implementation. When decomposing one module into multiple files, create a package named after the original module and expose the public API via `__init__.py`; do not scatter prefixed implementation files in the parent package. If bootstrap must run before loading an app module, isolate that boundary in a typed loader and validate the loaded symbol instead of suppressing ruff. If a persisted/shared model is needed by lower and higher layers, move it to the lower shared owner or an independent leaf module instead of local-importing upward. If a shared policy/helper is needed by lower and higher layers, extract it to a leaf module instead of local-importing upward with `# noqa`.

## 9. Rule 22: Signature Integrity
**Principle:** Always verify local signatures with `view_file` BEFORE planning mocks or tests. Never assume legacy parameter names (e.g., `on_checkpoint` vs `progress_detail_callback`).
**Mistake Repeated:** Writing tests that trigger `TypeError` due to stale parameter names.

## 10. Rule 23: Mock Fidelity [Repeated: 1 time]
**Principle:** Mocks used in tests for hardened classes MUST satisfy the ingress validation requirements (Rule 0.1).
**Best Fix:** Use real Pydantic models for test data wherever possible. If mocking, ensure the mock shape matches the expected Pydantic schema to avoid "Mock Pollution".

## 11. Inline Prompt Loading (Rule 11)
**Principle:** Prompt prose belongs in `.md` prompt files, not Python source. Prompt `.md` files must be loaded via the canonical utility `agentic_workflows.prompts.load_prompt`, never via ad-hoc `pathlib` path construction.
**Mistake Repeated:** Using `Path(__file__).parent / "prompts" / "<role>.md"` and calling `.read_text()` directly. This bypasses the path-escape security guard and `FileNotFoundError` diagnostic in `agentic_workflows/prompts.py`.
**Mistake Repeated:** Embedding long-lived system messages, runtime instructions, reviewer instructions, or retry-feedback templates directly inside agent initialization or Python business logic.
**Best Fix:** Move static prose to a `prompts/<name>.md` file beside the agent that owns it, then use `from agentic_workflows.prompts import load_prompt` and `load_prompt(__file__, "<name>.md")`. Use `PromptTemplate` for `{variable}` substitution. Never construct the `prompts/` path by hand in production code.

## 12. The "Fat Model" / Optional Overload (Rule 24)
**Principle:** A model should represent a single, clear state or concept. If a model has many mutually exclusive optional fields, it is masking multiple distinct types.
**Symptoms:**
- `class MultiModalContent(BaseModel): text: str | None = None; image_url: str | None = None`
- Pydantic models with `extra="allow"` combined with `| None = None` on almost all fields.
- Widespread use of `if obj.text is not None:` or `if obj.get("text"):` downstream to determine the model's true nature.
**Why it's bad:** It forces downstream business logic to perform defensive attribute checks to determine what the model actually represents, creating tight coupling and violating the Single Responsibility Principle. This is a failure of polymorphism and typing at the boundary.
**Best Fix:** Refactor into a Discriminated Union using Pydantic `Discriminator` or `Literal` type fields (e.g., `TextContentPart(type: Literal["text"], text: str)` and `ImageContentPart(type: Literal["image"], image_url: str)`). Ensure models are tight and express exact shapes.

## 13. Union Type Bleed into Strict SDK Models (Rule 25)
**Principle:** When translating from loose, highly-expressive internal schema definitions (like multi-type lists in JSON schemas) to restrictive, statically-typed external SDK models, validation and type narrowing must occur explicitly.
**Symptoms:**
- Passing a `list[str]` or `Union` directly to an SDK field that only accepts a single scalar `Type.STRING`.
- Using `.get(type_field)` where `type_field` was broadened from a `str` to `list[str]`.
**Why it's bad:** External SDKs often crash or fail static analysis if provided broader types than they support natively. Silent type mapping failures lead to malformed API requests.
**Best Fix:** Explicitly check for composite types (`isinstance(val, list)`) at the mapping boundary. Implement fallback logic (e.g., picking the first non-null type) to satisfy the strict SDK contract while accommodating the looser internal format.

## 14. Cast over Comprehension / Native Typing (Rule 1, 26)
**Principle:** If a variable can be typed natively to satisfy Pyright without a cast, it MUST be. A cast is an admission of failure in type inference or native typing.
**Mistake Repeated:** Slapping `cast(ListUnion, my_list)` on a list instead of natively declaring `my_list: ListUnion = []` from inception. Using `cast(list[str], [x for x in vals])` instead of natively filtering `[x for x in vals if x is not None]`.
**Why it's bad:** It's an illusion of safety. The runtime structure might still violate the intended contract, but Pyright is silenced.
**Best Fix:** Declare variables natively using the required SDK union or protocol type at inception. Filter out `None` values organically in comprehensions (`if x`) so Pyright infers the correct strict type without force.

## 15. SDK Schema Guessing (Rule 27)
**Principle:** Never guess the shape of a third-party SDK dictionary payload.
**Mistake Repeated:** Assuming `Responses API` tool choice follows the exact same nested format as `ChatCompletion` API because they belong to the same vendor, resulting in test suite crashes when the schemas diverge.
**Why it's bad:** Leads to silent drops, malformed requests, and immediate test regressions.
**Best Fix:** Introspect the SDK natively before hardcoding any literal dictionary shapes: write a scratch script under `verify/` that prints `inspect.getsource(ExternalModel)` and run it with `python3 verify/<script>.py` (AGENTS.md §8 forbids `python -c`). Map strictly to the discovered Pydantic/TypedDict fields.

## 16. The "Patch and Stop" / Incomplete Scope Remediation (Rule 28) [Repeated: 2 times]
**Principle:** If you find one instance of an antipattern, assume there are more in the same file.
**Mistake Repeated:** Fixing one `cast(Any, ...)` but leaving another `cast(SpecificType, ...)` two lines down. Fixing a `Mapping` to `dict` but leaving redundant `dict()` wrappers untouched.
**Mistake Repeated:** Replacing a raw payload flow with a DTO but leaving an unused raw `JSONValue` accessor in the same file.
**Why it's bad:** Wastes review cycles and forces human operators or subsequent agents to repeatedly point out remaining issues.
**Best Fix:** You must perform a rigorous `rg` sweep of the target file for the specific strings (`cast(`, `object`, `Any`, `Mapping[`, `dict(`, `model_dump(`, `getattr(`) *after* edits to ensure 100% eradication before declaring a file hardened. Scanner misses do not excuse touched-file leftovers.
