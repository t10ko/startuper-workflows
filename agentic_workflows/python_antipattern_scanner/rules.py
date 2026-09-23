from __future__ import annotations

import re

from .models import LineRule, RuleDefinition

RULE_1 = RuleDefinition(
    rule_id="RULE_1",
    group_title="1. Over-casting instead of Strong Typing (The cast() Abuse)",
    message="Rule 1: cast() abuse. Define Protocol/BaseModel instead.",
    why="Casting masks underlying architectural issues and bypasses static analysis.",
    best_fix="Define a proper Protocol, TypedDict, or Pydantic BaseModel.",
)

RULE_2 = RuleDefinition(
    rule_id="RULE_2",
    group_title="2. String-based Type Hints inside cast()",
    message="Rule 2: String-based cast type hints are prohibited.",
    why="String types in cast() are poorly supported and usually a hack to avoid imports.",
    best_fix="Use actual type objects and ensure proper imports.",
)

RULE_4_5 = RuleDefinition(
    rule_id="RULE_4_5",
    group_title="4/5. Overzealous String Casting / str(path) abuse",
    message="Rule 4/5: Defensive str() casting on paths. Use path.as_posix() instead.",
    why="Defensive str() leads to brittle code; Paths should use .as_posix().",
    best_fix="Keep values as Path objects; use .as_posix() for string conversion.",
)

RULE_PROJECT_PATH_RELATIVITY = RuleDefinition(
    rule_id="RULE_PROJECT_PATH_RELATIVITY",
    group_title="3. Project asset paths must be project-relative",
    message=(
        "Rule 3: Project asset path accepts both absolute and relative forms. "
        "Fix the boundary contract."
    ),
    why=(
        "Project-owned asset paths must be portable project-relative references; "
        "absolute paths belong only in runtime IO after resolving against project_folder."
    ),
    best_fix=(
        "Persist and pass project asset paths as project-relative Path values. "
        "Resolve to an absolute filesystem path exactly at the IO boundary."
    ),
)

RULE_6 = RuleDefinition(
    rule_id="RULE_6",
    group_title="6. The getattr()/hasattr() Crutch",
    message="Rule 6: getattr()/hasattr() crutch. Use strong types or isinstance().",
    why="Using getattr() circumvents static analysis and suggests untyped objects.",
    best_fix="Use isinstance() checks or strongly type objects with Protocols.",
)

RULE_7 = RuleDefinition(
    rule_id="RULE_7",
    group_title="7. Unnecessary dict() Wrapping",
    message="Rule 7: Unnecessary dict() wrapping. Pass the dict directly or use .copy().",
    why="Redundant dict() wrapping adds overhead and masks intent.",
    best_fix="Pass the dictionary directly or use .copy().",
)

RULE_10 = RuleDefinition(
    rule_id="RULE_10",
    group_title="10. Optional Imports for Required Dependencies",
    message="Rule 10: Optional import for required dependency. Fail fast instead.",
    why="Required dependencies should fail fast, not be hidden in try/except.",
    best_fix="Import normally and let the environment configuration be verified.",
)

RULE_13 = RuleDefinition(
    rule_id="RULE_13",
    group_title="13. Wrong-Direction isinstance Check (str instead of Path)",
    message="Rule 13: Path variables should not branch on str. Fix the producer type.",
    why="Variables representing paths should be Path objects, not strings.",
    best_fix="Fix producer to return Path and remove isinstance(path, str) checks.",
)

RULE_14 = RuleDefinition(
    rule_id="RULE_14",
    group_title="14. Casting to Any",
    message="Rule 14: cast-to-Any is prohibited. Fix the producer type.",
    why="Casting to Any disables static analysis and violates repo policies.",
    best_fix="Fix the producer to return precise types.",
)

RULE_15 = RuleDefinition(
    rule_id="RULE_15",
    group_title="15. Ignore-Comment Escapes for Type/Lint Errors",
    message="Rule 15: Ignore-comment escape detected. Fix the root cause instead.",
    why="Ignore comments hide bad contracts and let regressions accumulate.",
    best_fix="Fix the underlying type contract instead of silencing the tool.",
)

RULE_16 = RuleDefinition(
    rule_id="RULE_16",
    group_title="16. Self-Alias Import Re-Export Trick",
    message="Rule 16: Self-alias import re-export trick detected.",
    why="Self-alias imports like 'as foo' are often lint-appeasement hacks.",
    best_fix="Use explicit public API assignments instead of alias tricks.",
)

RULE_17 = RuleDefinition(
    rule_id="RULE_17",
    group_title="17. Inline Pydantic TypeAdapter Instantiation",
    message="Rule 17: Inline TypeAdapter instantiation inside function. Hoist to module scope.",
    why="Instantiating TypeAdapter is expensive; it should be done once at module scope.",
    best_fix="Create the TypeAdapter once at module scope and reuse it.",
)

RULE_OBJECT_PLACEHOLDER = RuleDefinition(
    rule_id="RULE_OBJECT_PLACEHOLDER",
    group_title="4. Loose Type Placeholders (object)",
    message="Rule 4 object placeholder. Use a concrete DTO or boundary alias.",
    why="object hides payload structure and forces downstream narrowing or casts.",
    best_fix=(
        "Do not replace JSONDict/JSONValue with dict[str, "
        "object]. Use a Pydantic DTO/domain model in business logic, or keep "
        "a named JSON boundary alias at true raw JSON boundaries."
    ),
)

RULE_ANY_PLACEHOLDER = RuleDefinition(
    rule_id="RULE_ANY_PLACEHOLDER",
    group_title="4. Loose Type Placeholders (Any)",
    message="Rule 4 Any placeholder. Use a concrete DTO or Protocol.",
    why="Any disables static analysis and lets loose payloads flow inward.",
    best_fix="Replace Any with a strict model, Protocol, or precise generic type.",
)

RULE_JSON_RAW_ALIAS = RuleDefinition(
    rule_id="RULE_JSON_RAW_ALIAS",
    group_title="4. Raw JSON aliases require boundary review",
    message="Rule 4 raw JSON alias. Confirm this is a true transport boundary.",
    why="JSONValue, JSONDict, and PrimitiveValue hide exact payload shape.",
    best_fix=(
        "Use raw JSON aliases only at parse or SDK boundaries. "
        "Use DTO/domain models inside business logic."
    ),
)

RULE_JSON_RECURSIVE_PAYLOAD = RuleDefinition(
    rule_id="RULE_JSON_RECURSIVE_PAYLOAD",
    group_title="4. Recursive JSON payload bleed",
    message="Rule 4 recursive JSON payload. Validate into a DTO at ingress.",
    why="Containers of JSONValue force downstream isinstance narrowing.",
    best_fix="Validate the payload once at the boundary and pass typed models inward.",
)

RULE_DEFENSIVE_DICT_PROBING = RuleDefinition(
    rule_id="RULE_DEFENSIVE_DICT_PROBING",
    group_title="5. Defensive payload dict probing",
    message="Rule 5 defensive dict probing. Validate the payload at ingress.",
    why="Payload .get(), setdefault(), KeyError repair, or dict checks mask contracts.",
    best_fix="Use a Pydantic DTO or TypeAdapter at the public entry point.",
)

RULE_OS_PATH = RuleDefinition(
    rule_id="RULE_OS_PATH",
    group_title="3. pathlib-only path handling",
    message="Rule 3 os.path/os.fspath usage. Use pathlib.Path APIs.",
    why="os path helpers bypass the repo's pathlib-only path contract.",
    best_fix="Keep paths as Path values and use Path methods at IO boundaries.",
)

RULE_INLINE_PROMPT_PATH = RuleDefinition(
    rule_id="RULE_INLINE_PROMPT_PATH",
    group_title="11. Inline prompt path loading",
    message="Rule 11 inline prompt path. Use load_prompt().",
    why="Manual prompt paths bypass the canonical path-escape guard.",
    best_fix="Load prompt files through src.utils.prompts.load_prompt.",
)

RULE_NAIVE_TIME = RuleDefinition(
    rule_id="RULE_NAIVE_TIME",
    group_title="UTC datetime integrity",
    message="Rule UTC naive time call. Use src.utils.time.utc_now().",
    why="Direct datetime/date calls can create naive or local-time values.",
    best_fix="Use src.utils.time.utc_now() for current timestamps.",
)

RULE_PRINT_LOGGING = RuleDefinition(
    rule_id="RULE_PRINT_LOGGING",
    group_title="Logging hygiene",
    message="Rule logging print() usage. Use the project logger.",
    why="print() bypasses structured logging and trace context.",
    best_fix="Use from agentic_workflows.logger import logger or start_trace.",
)

RULE_ABSOLUTE_PROJECT_PATH_LITERAL = RuleDefinition(
    rule_id="RULE_ABSOLUTE_PROJECT_PATH_LITERAL",
    group_title="3. Absolute project path literal",
    message="Rule 3 absolute project path literal. Use project-relative paths.",
    why="Absolute project paths leak machine-specific state into code.",
    best_fix="Use Path values relative to project_folder for project assets.",
)

RULE_EXCEPTION_HYGIENE = RuleDefinition(
    rule_id="RULE_EXCEPTION_HYGIENE",
    group_title="18. Exception hygiene",
    message="Rule 18 exception hygiene candidate. Preserve failure context.",
    why="Broad, empty, or malformed handlers hide production failure causes.",
    best_fix="Catch specific exceptions and include exception type in degradation data.",
)

RULE_TEST_ENV_LEAKAGE = RuleDefinition(
    rule_id="RULE_TEST_ENV_LEAKAGE",
    group_title="Test environment leakage",
    message="Rule test environment leakage. Use pytest monkeypatch helpers.",
    why="Direct os.environ mutation can leak state across test cases.",
    best_fix="Use monkeypatch.setenv(), monkeypatch.delenv(), or MonkeyPatch.context().",
)

RULE_INTERNAL_MONKEYPATCH = RuleDefinition(
    rule_id="RULE_INTERNAL_MONKEYPATCH",
    group_title="Test internal monkeypatching",
    message="Rule test internal monkeypatch. Use dependency injection.",
    why="Monkeypatching src.* hides broken contracts and lowers mock fidelity.",
    best_fix="Pass collaborators explicitly or use real domain/Pydantic models.",
)

OBJECT_PLACEHOLDER_PATTERN = re.compile(
    r"(?:"
    r"\b[a-zA-Z_][a-zA-Z0-9_.]*\s*\[[^\]\n]*\bobject\b[^\]\n]*\]"
    r"|->\s*object\b"
    r"|:\s*object\b"
    r")"
)

LINE_RULES = [
    LineRule(RULE_1, re.compile(r"(?<![a-zA-Z0-9_])cast\s*\(")),
    LineRule(RULE_2, re.compile(r"cast\s*\(\s*['\"]")),
    LineRule(RULE_OBJECT_PLACEHOLDER, OBJECT_PLACEHOLDER_PATTERN),
    LineRule(RULE_6, re.compile(r"(?<![a-zA-Z0-9_])getattr\s*\(")),
    LineRule(RULE_6, re.compile(r"(?<![a-zA-Z0-9_])hasattr\s*\(")),
    LineRule(RULE_7, re.compile(r"(?<![a-zA-Z0-9_])dict\s*\(")),
    LineRule(
        RULE_10,
        re.compile(r"try:.*import\s+.*except\s+ImportError:.*= None", re.DOTALL),
    ),
    LineRule(
        RULE_13,
        re.compile(
            r"isinstance\s*\([^,\n]*(?:path|folder|dir|base_raw)[^,\n]*,\s*str\)",
            re.IGNORECASE,
        ),
    ),
    LineRule(RULE_14, re.compile(r"cast\s*\(\s*Any\s*,")),
    LineRule(RULE_15, re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|noqa)")),
    LineRule(RULE_16, re.compile(r"import\s+(?P<name>[a-zA-Z0-9_]+)\s+as\s+(?P=name)")),
    LineRule(RULE_17, re.compile(r"TypeAdapter\s*\(")),
]

PATH_STR_PATTERN = re.compile(
    r"str\s*\(\s*(.*(path|folder|slug|dir|file|base_raw).*)\s*\)",
    re.IGNORECASE,
)

OPTIONAL_EMPTY_PATTERNS = {
    "dict": r".*=\s*(.*?\s+or\s+\{{\}}|{{.*?\s+or\s+\{{\}}}}|{{\s*.*\s+or\s+\{{\}}}}|.*\s+or\s*\{{\}}|{name}\s+or\s*\{{\}})",
    "list": r".*=\s*.*\s*or\s*\[\]",
    "tuple": r".*=\s*.*\s*or\s*\(\)",
    "str": r".*=\s*.*\s*or\s*\"\"",
    "coalesce": r".*=\s*(?P<param>{name})\s*or\s*(\{{\}}|\[\]|\"\"|\(\))",
}

ALLOW_COMMENT = "antipattern: allow"

CALLABLE_MARKERS = (
    "Callable",
    "Awaitable",
    "Iterable",
    "handler",
    "callback",
    "factory",
    "pre_download",
    "filter_fn",
)
ISINSTANCE_ARG_COUNT = 2

BOUNDARY_ERROR_TEXT = (
    "invalid",
    "missing",
    "required",
    "must have",
    "forbidden",
    "not found",
    "unknown",
)
