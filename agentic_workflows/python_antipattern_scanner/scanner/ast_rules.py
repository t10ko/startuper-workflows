from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeGuard

from agentic_workflows.ast_callee import callee_name, import_aliases
from agentic_workflows.python_antipattern_scanner.models import RuleFinding
from agentic_workflows.python_antipattern_scanner.rules import (
    ISINSTANCE_ARG_COUNT,
    RULE_ABSOLUTE_PROJECT_PATH_LITERAL,
    RULE_ANY_PLACEHOLDER,
    RULE_DEFENSIVE_DICT_PROBING,
    RULE_EXCEPTION_HYGIENE,
    RULE_INLINE_PROMPT_PATH,
    RULE_INTERNAL_MONKEYPATCH,
    RULE_JSON_RAW_ALIAS,
    RULE_JSON_RECURSIVE_PAYLOAD,
    RULE_NAIVE_TIME,
    RULE_OS_PATH,
    RULE_PRINT_LOGGING,
    RULE_TEST_ENV_LEAKAGE,
)

from .support import append_rule_finding, line_evidence

RAW_JSON_TYPE_NAMES = frozenset({"JSONDict", "JSONValue", "PrimitiveValue"})
ANY_TYPE_NAMES = frozenset({"Any"})
JSON_ALIAS_MODULES = frozenset({"src.types", "src.utils.json"})
TYPING_MODULES = frozenset({"typing", "typing_extensions"})
JSON_CONTAINER_NAMES = frozenset(
    {
        "Awaitable",
        "Callable",
        "Coroutine",
        "Iterable",
        "Mapping",
        "MutableMapping",
        "Sequence",
        "dict",
        "list",
        "set",
        "tuple",
    }
)
PAYLOADISH_MARKERS = (
    "argument",
    "data",
    "json",
    "metadata",
    "payload",
    "raw",
    "response",
    "tool_input",
)
NAIVE_TIME_CALLS = {
    ("date", "today"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
}


def _parse_ast(content: str) -> ast.Module | None:
    try:
        return ast.parse(content)
    except SyntaxError:
        return None


def _collect_import_aliases(
    tree: ast.Module,
    canonical_names: frozenset[str],
    modules: frozenset[str],
) -> set[str]:
    names = set(canonical_names)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in modules:
            continue
        for alias in node.names:
            if alias.name in canonical_names:
                names.add(alias.asname or alias.name)
    return names


def _annotation_contains_name(annotation: ast.AST, names: set[str]) -> bool:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id in names:
            return True
        if isinstance(node, ast.Attribute) and node.attr in names:
            return True
    return False


def _container_base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _container_base_name(node.value)
    return None


def _annotation_has_recursive_json(
    annotation: ast.AST,
    raw_json_names: set[str],
) -> bool:
    for node in ast.walk(annotation):
        if not isinstance(node, ast.Subscript):
            continue
        base_name = _container_base_name(node.value)
        if base_name not in JSON_CONTAINER_NAMES:
            continue
        if _annotation_contains_name(node.slice, raw_json_names):
            return True
    return False


def _function_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = list(node.args.posonlyargs)
    args.extend(node.args.args)
    args.extend(node.args.kwonlyargs)
    if node.args.vararg is not None:
        args.append(node.args.vararg)
    if node.args.kwarg is not None:
        args.append(node.args.kwarg)
    return args


def _iter_annotation_contexts(tree: ast.Module) -> list[tuple[int, ast.AST]]:
    contexts: list[tuple[int, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            contexts.append((node.lineno, node.annotation))
        elif isinstance(node, ast.TypeAlias):
            contexts.append((node.lineno, node.value))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            contexts.extend(
                (arg.lineno, arg.annotation)
                for arg in _function_args(node)
                if arg.annotation is not None
            )
            if node.returns is not None:
                contexts.append((node.lineno, node.returns))
    return contexts


def _scan_annotation_rules(
    path: Path,
    lines: list[str],
    tree: ast.Module,
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    any_names = _collect_import_aliases(tree, ANY_TYPE_NAMES, TYPING_MODULES)
    raw_json_names = _collect_import_aliases(
        tree,
        RAW_JSON_TYPE_NAMES,
        JSON_ALIAS_MODULES,
    )
    for lineno, annotation in _iter_annotation_contexts(tree):
        evidence = line_evidence(lines, lineno)
        if _annotation_contains_name(annotation, any_names):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                lineno,
                RULE_ANY_PLACEHOLDER,
                evidence,
            )
        if _annotation_contains_name(annotation, raw_json_names):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                lineno,
                RULE_JSON_RAW_ALIAS,
                evidence,
            )
        if _annotation_has_recursive_json(annotation, raw_json_names):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                lineno,
                RULE_JSON_RECURSIVE_PAYLOAD,
                evidence,
            )
    return findings


def _expr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _expr_name(node.value)
    return None


def _is_payloadish_expr(node: ast.AST) -> bool:
    name = _expr_name(node)
    if name is None:
        return False
    normalized = name.lower()
    return any(marker in normalized for marker in PAYLOADISH_MARKERS)


def _is_dict_type_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "dict"
    if isinstance(node, ast.Attribute):
        return node.attr == "dict"
    if isinstance(node, ast.Tuple):
        return any(_is_dict_type_expr(elt) for elt in node.elts)
    return False


def _is_key_error_expr(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "KeyError"
    if isinstance(node, ast.Attribute):
        return node.attr == "KeyError"
    if isinstance(node, ast.Tuple):
        return any(_is_key_error_expr(elt) for elt in node.elts)
    return False


def _scan_defensive_dict_rules(
    path: Path,
    lines: list[str],
    tree: ast.Module,
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for node in ast.walk(tree):
        lineno = _defensive_dict_lineno(node)
        if lineno is not None:
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                lineno,
                RULE_DEFENSIVE_DICT_PROBING,
                line_evidence(lines, lineno),
            )
    return findings


def _defensive_dict_lineno(node: ast.AST) -> int | None:
    if isinstance(node, ast.Call) and _is_defensive_dict_call(node):
        return node.lineno
    if isinstance(node, ast.ExceptHandler) and _is_key_error_expr(node.type):
        return node.lineno
    return None


def _is_defensive_dict_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr in {
        "get",
        "setdefault",
    }:
        return _is_payloadish_expr(node.func.value)
    if not isinstance(node.func, ast.Name) or node.func.id != "isinstance":
        return False
    if len(node.args) < ISINSTANCE_ARG_COUNT:
        return False
    return _is_payloadish_expr(node.args[0]) and _is_dict_type_expr(node.args[1])


def _is_os_path_call(node: ast.Call) -> bool:
    """``os.path.<x>(...)`` and ``os.fspath(...)``, read off the receiver.

    **What this does not reach.** A member bound as a bare name --
    ``from os.path import join`` then ``join(a, b)`` -- has no ``os``
    receiver left in the call to read, so it is not reported here.
    Resolving the callee cannot recover it either: the ban is on the
    *module*, and the bare name says nothing about which module bound it, so
    the import statement is where that spelling has to be met.
    :func:`_is_os_path_import` meets it.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    if isinstance(node.func.value, ast.Name):
        return node.func.value.id == "os" and node.func.attr == "fspath"
    if not isinstance(node.func.value, ast.Attribute):
        return False
    value = node.func.value
    return (
        isinstance(value.value, ast.Name)
        and value.value.id == "os"
        and value.attr == "path"
    )


#: The one member of ``os`` that takes a path and is banned with ``os.path``.
_OS_PATH_MEMBERS = frozenset({"fspath"})


def _is_os_path_import(node: ast.AST) -> TypeGuard[ast.Import | ast.ImportFrom]:
    """An import binding ``os.path``, or a path member of ``os``, by any name.

    ``import os.path``, ``import os.path as p`` and ``from os.path import
    join`` all bind the banned module; ``from os import fspath`` binds the
    one banned member of ``os`` itself. Aliases need no separate case: the
    statement is judged on what it imports, never on the local name it binds.
    ``import os`` alone binds nothing banned -- the call-site rule reads
    ``os.path.<x>`` and ``os.fspath`` off that receiver.
    """
    if isinstance(node, ast.Import):
        return any(
            alias.name == "os.path" or alias.name.startswith("os.path.")
            for alias in node.names
        )
    if not isinstance(node, ast.ImportFrom) or node.level:
        return False
    module = node.module or ""
    if module == "os.path" or module.startswith("os.path."):
        return True
    return module == "os" and any(
        alias.name in _OS_PATH_MEMBERS for alias in node.names
    )


def _contains_path_file_call(node: ast.AST) -> bool:
    """``Path(__file__)`` in whichever spelling the module writes it.

    ``pathlib.Path(__file__)`` builds the identical path and is written in
    this repository today, so matching only the bare name reported a clean
    module for the one construction AGENTS.md section 6 bans by hand.
    """
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or callee_name(child) != "Path":
            continue
        if child.args and isinstance(child.args[0], ast.Name):
            return child.args[0].id == "__file__"
    return False


def _contains_prompt_literal(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value == "prompts":
            return True
    return False


def _is_inline_prompt_path(node: ast.AST) -> bool:
    return _contains_path_file_call(node) and _contains_prompt_literal(node)


def _call_base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


#: The receivers :data:`NAIVE_TIME_CALLS` names, for alias resolution.
NAIVE_TIME_RECEIVERS = frozenset(receiver for receiver, _ in NAIVE_TIME_CALLS)


def _is_naive_time_call(node: ast.Call, aliases: dict[str, str]) -> bool:
    """A naive clock read, through whatever local name imported its receiver.

    ``from datetime import datetime as dt`` binds a second spelling of one
    class, and ``dt.now()`` is the same naive read as ``datetime.now()``;
    *aliases* maps the local name back so the pair is looked up on what was
    imported rather than on what was typed.

    **What this does not reach.** ``now``, ``utcnow`` and ``today`` are
    classmethods, not members of the ``datetime`` module, so no import binds
    any of them as a bare name -- the attribute form measured here is the
    only spelling the language admits. A receiver held in a variable
    (``clock = datetime`` then ``clock.now()``) has no static name and is not
    reached, the same limit :mod:`src.utils.ast_callee` states for itself.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    base_name = _call_base_name(node.func.value)
    if base_name is None:
        return False
    return (aliases.get(base_name, base_name), node.func.attr) in NAIVE_TIME_CALLS


def _scan_repo_hygiene_rules(
    path: Path,
    lines: list[str],
    tree: ast.Module,
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    absolute_prefix = (project_root or Path.cwd()).resolve().as_posix()
    aliases = import_aliases(tree, NAIVE_TIME_RECEIVERS)
    for node in ast.walk(tree):
        if _is_os_path_import(node):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                node.lineno,
                RULE_OS_PATH,
                line_evidence(lines, node.lineno),
            )
        if isinstance(node, ast.Call):
            _scan_hygiene_call(path, lines, project_root, findings, seen, node, aliases)
        elif isinstance(node, ast.BinOp) and _is_inline_prompt_path(node):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                node.lineno,
                RULE_INLINE_PROMPT_PATH,
                line_evidence(lines, node.lineno),
            )
        elif isinstance(node, ast.Constant) and _is_absolute_project_path_literal(
            node,
            absolute_prefix,
        ):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                node.lineno,
                RULE_ABSOLUTE_PROJECT_PATH_LITERAL,
                line_evidence(lines, node.lineno),
            )
    return findings


def _scan_hygiene_call(
    path: Path,
    lines: list[str],
    project_root: Path | None,
    findings: list[RuleFinding],
    seen: set[tuple[str, int, str]],
    node: ast.Call,
    aliases: dict[str, str],
) -> None:
    if _is_os_path_call(node):
        definition = RULE_OS_PATH
    elif _is_naive_time_call(node, aliases):
        definition = RULE_NAIVE_TIME
    elif callee_name(node) == "print":
        definition = RULE_PRINT_LOGGING
    else:
        return
    append_rule_finding(
        findings,
        seen,
        path,
        project_root,
        node.lineno,
        definition,
        line_evidence(lines, node.lineno),
    )


def _is_absolute_project_path_literal(node: ast.AST, absolute_prefix: str) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    return node.value.startswith(absolute_prefix)


def _exception_type_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_broad_exception(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return _exception_type_name(node) in {"BaseException", "Exception"}


def _has_nested_safe_exception_tuple(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Tuple):
        return False
    for elt in node.elts:
        if isinstance(elt, ast.Starred):
            continue
        if isinstance(elt, ast.Name) and elt.id.startswith("SAFE_"):
            return True
    return False


def _is_empty_exception_body(node: ast.ExceptHandler) -> bool:
    return bool(node.body) and all(isinstance(child, ast.Pass) for child in node.body)


def _scan_exception_hygiene_rules(
    path: Path,
    lines: list[str],
    tree: ast.Module,
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if (
            node.type is None
            or _is_broad_exception(node.type)
            or _has_nested_safe_exception_tuple(node.type)
            or _is_empty_exception_body(node)
        ):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                node.lineno,
                RULE_EXCEPTION_HYGIENE,
                line_evidence(lines, node.lineno),
            )
    return findings


def _is_test_path(path: Path) -> bool:
    return "tests" in path.parts


def _is_os_environ_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_os_environ_target(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript):
        return _is_os_environ_expr(node.value)
    return _is_os_environ_expr(node)


def _is_os_environ_update(node: ast.Call) -> bool:
    """``os.environ.update(...)``, read off the receiver it mutates.

    **What this does not reach.** ``update`` is matched in attribute form
    only, which is the only form that keeps the receiver this rule is about:
    it is a mapping method, so no import binds it as a bare name, and a copy
    held in a variable (``write = os.environ.update``) has no static callee
    for :mod:`src.utils.ast_callee` to resolve either.
    """
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
        and _is_os_environ_expr(node.func.value)
    )


#: The two patch verbs. ``delattr`` removes an internal attribute exactly as
#: ``setattr`` replaces one, and both take the same dotted target.
_MONKEYPATCH_VERBS = frozenset({"setattr", "delattr"})


def _is_internal_monkeypatch(node: ast.Call) -> bool:
    """A patch of ``src.`` through any receiver, named or rebound.

    Keyed on the *target* rather than on a receiver spelled ``monkeypatch``:
    the fixture's own ``with monkeypatch.context() as patched:`` rebinds it,
    ``pytest.MonkeyPatch()`` never binds that name at all, and both spellings
    are written in this suite today -- a rule reading the literal name
    reported zero violations for every one of them. A dotted ``"src...."``
    first argument is what makes the call a patch of internal code, and it
    says so whatever the receiver is called.

    **What this does not reach.** The builtin ``setattr(module, "name", x)``,
    which patches internal code just as effectively but is written as a bare
    name; resolving the callee would report every ordinary ``setattr`` in the
    suite, so the receiver-form requirement stays and this spelling is met by
    ``scripts/check_no_internal_monkeypatch.py`` instead, which tracks
    receivers rather than guessing at them. A target passed as an object
    rather than a dotted string is likewise outside this rule and inside that
    gate's.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _MONKEYPATCH_VERBS:
        return False
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return False
    return isinstance(node.args[0].value, str) and node.args[0].value.startswith("src.")


def _scan_test_scope_rules(
    path: Path,
    lines: list[str],
    tree: ast.Module,
    project_root: Path | None,
) -> list[RuleFinding]:
    if not _is_test_path(path):
        return []

    findings: list[RuleFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for node in ast.walk(tree):
        env_lineno = _test_env_leakage_lineno(node)
        if env_lineno is not None:
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                env_lineno,
                RULE_TEST_ENV_LEAKAGE,
                line_evidence(lines, env_lineno),
            )
        if isinstance(node, ast.Call) and _is_internal_monkeypatch(node):
            append_rule_finding(
                findings,
                seen,
                path,
                project_root,
                node.lineno,
                RULE_INTERNAL_MONKEYPATCH,
                line_evidence(lines, node.lineno),
            )
    return findings


def _test_env_leakage_lineno(node: ast.AST) -> int | None:
    if isinstance(node, ast.Assign) and any(
        _is_os_environ_target(target) for target in node.targets
    ):
        return node.lineno
    if isinstance(node, ast.AnnAssign | ast.AugAssign) and _is_os_environ_target(
        node.target,
    ):
        return node.lineno
    if isinstance(node, ast.Call) and _is_os_environ_update(node):
        return node.lineno
    return None


def scan_ast_rules(
    path: Path,
    lines: list[str],
    content: str,
    project_root: Path | None,
) -> list[RuleFinding]:
    tree = _parse_ast(content)
    if tree is None:
        return []
    return (
        _scan_annotation_rules(path, lines, tree, project_root)
        + _scan_defensive_dict_rules(path, lines, tree, project_root)
        + _scan_repo_hygiene_rules(path, lines, tree, project_root)
        + _scan_exception_hygiene_rules(path, lines, tree, project_root)
        + _scan_test_scope_rules(path, lines, tree, project_root)
    )
