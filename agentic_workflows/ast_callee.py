"""One way to recognise a call, whatever spelling it is written in (REQ-060).

Every check that sweeps source for call sites shares one hazard: a call is
written more than one way. ``record(...)``, ``ledger.record(...)`` and
``rec(...)`` after ``from ... import record as rec`` are the same call, and a
matcher that knows only the first reports *nothing* when a site is rewritten
into either of the others. That direction is silent -- the derived set stays
complete-looking with a member missing from it -- which is why every check on
the money and progress surfaces resolves callees here rather than each
spelling its own test.

**Why this sits in ``src/`` (REQ-062).** It held the same code under
``tests/unit/support/`` and the CI gates under ``scripts/`` could not read it:
a gate importing the test tree inverts the layering, so
``scripts/check_no_raw_llmrequest.py`` kept a bare-name-only matcher of its
own and stayed green while an attribute-form construction shipped in real
production source. Nothing here belongs to tests -- it is a pure ``ast``
reader with no fixture, no pytest import and no test data, exactly like the
source sweepers ``src/utils/`` already ships (``type_erasure_scan.py``,
``python_antipattern_scanner/``) -- so this is the one place both layers may
import from.

**What this does not reach.** A name rebound at run time (``Entry =
models.SpendEntry``), a callee held in a variable or a container
(``recorder = ledger.record`` then ``recorder(...)``), a dynamically imported
module, and a call whose function is itself an expression -- ``factory()(...)``
or ``handlers[k](...)`` -- have no static name here and answer ``None``,
from :func:`callee_name`, :func:`callee_root` and :func:`dotted_callee`
alike. The attribute spelling is matched on the attribute name alone, so an
unrelated method that happens to share a vocabulary name is reported; that
direction fails loudly at whichever check asked, and is the deliberate trade
against the silent one above. A check that cannot afford even that trade --
one comparing against a set that has to match exactly -- resolves the
callee's own dotted path through :func:`dotted_callee` instead, which needs
the module's import table and answers an identity rather than a word.
"""

from __future__ import annotations

import ast
from collections.abc import Collection, Iterator


def callee_name(call: ast.Call) -> str | None:
    """The name *call* invokes, in either spelling, or ``None`` for neither.

    ``record(...)`` and ``ledger.record(...)`` both answer ``"record"``: the
    local spelling as written, before any import alias is resolved.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def callee_root(call: ast.Call) -> str | None:
    """The local name *call* reaches through, or ``None`` for an expression.

    ``send(...)``, ``client.send(...)`` and ``sdk.client.send(...)`` answer
    ``"send"``, ``"client"`` and ``"sdk"`` to :func:`callee_name` -- and
    ``"send"``, ``"client"`` and ``"sdk"`` respectively here, because this
    answers a different question: *which binding does the call go through*.
    A sweep asking whether a module uses what it imported needs the root, not
    the invoked attribute, which the imported module never spells.
    """
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def import_symbols(tree: ast.AST) -> dict[str, str]:
    """Local name -> the dotted path it stands for, for every plain import.

    ``from re import compile`` binds ``compile`` to ``re.compile``; ``import
    a.b.c`` binds ``a`` to ``a``, which is what the statement really binds, and
    is enough for :func:`dotted_callee` to rebuild the rest from the written
    attributes. A relative import binds nothing, because the package it is
    relative to is not readable from the tree alone -- a caller that knows its
    own dotted path resolves those itself and passes its own table.
    """
    symbols: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            for alias in node.names:
                if alias.name != "*":
                    symbols[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                symbols[alias.asname or root] = alias.name if alias.asname else root
    return symbols


def dotted_callee(call: ast.Call, symbols: dict[str, str]) -> str | None:
    """The dotted path *call* invokes, resolved through *symbols*.

    ``compile(...)``, ``re.compile(...)`` and ``regex.compile(...)`` are one
    function written three ways, and which spelling a module uses is its own
    choice. :func:`callee_name` answers the same for the first two and the
    wrong thing for a same-named method of something else; this answers the
    function's own identity instead, for a caller that can supply the module's
    import table.

    Only the *root* is looked up: the attributes written after it are appended
    as they stand, so a table holding a module resolves every member of it
    without an entry apiece. An unbound root stands for itself -- which is what
    ``import a.b.c`` binds -- so a local name (``self``, a parameter, a
    variable) yields a path no module owns and matches nothing rather than
    matching the wrong thing.

    **What this does not reach.** A callee with no static root (``factory()
    (...)``, ``handlers[k](...)``) answers ``None``, like :func:`callee_name`
    and :func:`callee_root`. A name rebound at run time resolves to whatever
    the import table says, not to what the rebinding did.
    """
    attributes: list[str] = []
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        attributes.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([symbols.get(node.id, node.id), *reversed(attributes)])


def import_aliases(tree: ast.AST, vocabulary: Collection[str]) -> dict[str, str]:
    """Local name -> the *vocabulary* member it stands for, for every alias.

    ``from agentic_workflows.spend.ledger import record_provider_spend as rec`` binds a
    second bare-name spelling of one call. ``import a.b as m`` needs no entry:
    ``m.record(...)`` is an attribute call, matched on its attribute name.
    """
    wanted = frozenset(vocabulary)
    return {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in wanted
    }


def calls_to(
    tree: ast.AST,
    vocabulary: Collection[str],
    *,
    aliases: dict[str, str] | None = None,
) -> Iterator[tuple[ast.Call, str]]:
    """Every call under *tree* invoking a *vocabulary* member, with that member.

    Both spellings and every import alias. *aliases* is for a walk that starts
    below a module's import statements -- pass ``import_aliases(module, ...)``
    so a sweep over one function resolves what that module bound; omitted, the
    aliases are read off *tree* itself.
    """
    wanted = frozenset(vocabulary)
    resolved = import_aliases(tree, wanted) if aliases is None else aliases
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        written = callee_name(node)
        if written is None:
            continue
        canonical = resolved.get(written, written)
        if canonical in wanted:
            yield node, canonical
