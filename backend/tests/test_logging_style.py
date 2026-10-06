"""
Library code logs through `logging`, and a log message does not start with a bracketed tag that only restates the logger's own name.

The log format already prints the logger name (`INFO [nuclides.isotope_database] ...`), so "[Isotope Database] Loaded ..." said it twice: 112
messages did. A tag that adds a sub-context the logger name lacks (`[CSV Upload]` in the analysis router, `[Watchdog]`, `[WebSocket]` in main)
stays. Scripts in tools/ and the tests print on purpose; they are not checked.
"""
import ast
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SKIP_PARTS = {"tests", "tools", "__pycache__", "TO_BE_DELETED", "legacy", "data"}
LEVELS = {"debug", "info", "warning", "error", "exception", "critical"}


def library_files():
    for path in sorted(BACKEND.rglob("*.py")):
        if not SKIP_PARTS & set(path.relative_to(BACKEND).parts):
            yield path


def first_literal(call):
    """The leading literal text of a logging call's message (a plain string or the start of an f-string), or None."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr) and arg.values and isinstance(arg.values[0], ast.Constant):
        return arg.values[0].value
    return None


def restates_module(tag, module_stem):
    norm, mod = re.sub(r"[^a-z0-9]+", "", tag.lower()), re.sub(r"[^a-z0-9]+", "", module_stem.lower())
    return bool(norm) and (norm == mod or norm in mod or mod in norm)


def test_library_code_does_not_print():
    offenders = []
    for path in library_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert not offenders, "print() in library code (use the module's logger): " + ", ".join(offenders)


def test_no_log_message_starts_with_a_tag_that_restates_the_module():
    offenders = []
    for path in library_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LEVELS
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in {"logger", "log", "logging"}):
                text = first_literal(node)
                match = re.match(r"\[([^\]]+)\]", text or "")
                if match and restates_module(match.group(1), path.stem):
                    offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno} {text[:50]!r}")
    assert not offenders, "the logger name is already in the log line: " + "; ".join(offenders)


def test_the_check_would_catch_the_old_style():
    """The rule itself: the old tag restated the module, a sub-context tag does not."""
    assert restates_module("Isotope Database", "isotope_database") and restates_module("AcquisitionManager", "acquisition_manager")
    assert restates_module("ML", "ml_analysis")
    assert not restates_module("CSV Upload", "analysis") and not restates_module("Watchdog", "main")
