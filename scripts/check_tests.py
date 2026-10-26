"""Fail on tests that can't catch a bug.

Coverage counts a test with no real assertion as covering code, and ruff doesn't look at intent,
so this is the only gate for it.
"""

import ast
import copy
import sys
from collections import defaultdict
from pathlib import Path
from typing import TypeAlias

MOCK_ASSERTS = frozenset(
    {
        "assert_any_await",
        "assert_any_call",
        "assert_awaited",
        "assert_awaited_once",
        "assert_awaited_once_with",
        "assert_awaited_with",
        "assert_called",
        "assert_called_once",
        "assert_called_once_with",
        "assert_called_with",
        "assert_has_awaits",
        "assert_has_calls",
        "assert_not_awaited",
        "assert_not_called",
    }
)
MOCK_ATTRS = frozenset({"await_count", "call_args", "call_args_list", "call_count", "called"})
WEAK_CALLS = frozenset({"callable", "hasattr", "isinstance", "len"})
RAISES = frozenset({"raises", "warns"})
PATCHERS = frozenset({"delattr", "object", "patch", "setattr", "setitem"})
OWN_PACKAGE = "tfdiff."
MAX_CLONES = 2

TestFn: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef


def call_name(func: ast.expr) -> str:
    match func:
        case ast.Name(id=name) | ast.Attribute(attr=name):
            return name
    return ""


def is_weak(test: ast.expr) -> bool:
    match test:
        # `assert found` or `assert len(found)`: passes for any non-empty value, right or wrong
        case ast.Constant() | ast.Name():
            return True
        case ast.Compare(ops=[ast.IsNot()], comparators=[ast.Constant(value=None)]):
            return True
        case ast.Attribute(attr=attr) | ast.Compare(left=ast.Attribute(attr=attr)):
            return attr in MOCK_ATTRS
        case ast.Call(func=func):
            return call_name(func) in WEAK_CALLS
    return False


def is_check(node: ast.AST) -> bool:
    match node:
        case ast.Assert(test=test):
            return not is_weak(test)
        case ast.withitem(context_expr=ast.Call(func=func)):
            return call_name(func) in RAISES
        case ast.Call(func=func):
            name = call_name(func)
            return name.startswith("assert_") and name not in MOCK_ASSERTS
    return False


def own_names(tree: ast.Module) -> frozenset[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        match node:
            case ast.ImportFrom(module=str(module), names=names) if module.startswith("tfdiff"):
                found.update(alias.asname or alias.name for alias in names)
            case ast.Import(names=names):
                found.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in names
                    if alias.name.startswith("tfdiff")
                )
    return frozenset(found)


def patches_own_code(call: ast.Call, own: frozenset[str]) -> bool:
    if call_name(call.func) not in PATCHERS:
        return False
    match call.args:
        case [ast.Constant(value=str(target)), *_]:
            return target.startswith(OWN_PACKAGE)
        # a module or object imported from tfdiff, as setattr(cli, ...) or patch.object(engine, ...)
        case [ast.Name(id=name) | ast.Attribute(value=ast.Name(id=name)), *_]:
            return name in own
    return False


def skeleton(fn: TestFn) -> str:
    body = copy.deepcopy(fn.body)
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant):
                node.value = None
    return "".join(ast.dump(stmt) for stmt in body)


def check_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[str] = []
    own = own_names(tree)
    clones: defaultdict[str, list[int]] = defaultdict(list)
    tests = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]
    for fn in tests:
        nodes = list(ast.walk(fn))
        if not any(is_check(node) for node in nodes):
            errors.append(f"{path}:{fn.lineno}: {fn.name}: no assertion that can fail on a bug")
        errors.extend(
            f"{path}:{node.lineno}: {fn.name}: patches our own code, use real objects"
            for node in nodes
            if isinstance(node, ast.Call) and patches_own_code(node, own)
        )
        clones[skeleton(fn)].append(fn.lineno)
    errors.extend(
        f"{path}:{lines[0]}: {len(lines)} tests differ only in literals, use parametrize"
        for lines in clones.values()
        if len(lines) > MAX_CLONES
    )
    return errors


def main(root: Path) -> int:
    errors = [error for path in sorted(root.rglob("test_*.py")) for error in check_file(path)]
    sys.stderr.writelines(f"{error}\n" for error in errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "tests")))
