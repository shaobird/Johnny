"""
Custom tool definitions and implementations.
Add new tools here — define the schema in CUSTOM_TOOL_SCHEMAS and
add the handler in execute_tool().
"""

import ast
import operator
from datetime import datetime

NOTES_FILE = "notes.txt"

# ── Tool schemas (sent to the Claude API) ─────────────────────────────────────

CUSTOM_TOOL_SCHEMAS = [
    {
        "name": "get_datetime",
        "description": "Get the current date and time.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Safely evaluate a mathematical expression. "
            "Supports +, -, *, /, **, %, // and parentheses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression, e.g. '(2 + 3) * 4' or '2 ** 10'",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "save_note",
        "description": "Save a note or piece of information to a local file for later reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title for the note"},
                "content": {"type": "string", "description": "Content of the note"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "read_notes",
        "description": "Read all previously saved notes.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── Dispatcher ─────────────────────────────────────────────────────────────────

def execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a custom tool call to its implementation."""
    handlers = {
        "get_datetime": _get_datetime,
        "calculate": _calculate,
        "save_note": _save_note,
        "read_notes": _read_notes,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Error: unknown tool '{name}'"
    try:
        return handler(inputs)
    except Exception as exc:
        return f"Error running {name}: {exc}"


# ── Implementations ────────────────────────────────────────────────────────────

def _get_datetime(_inputs: dict) -> str:
    return datetime.now().strftime("%A, %B %d, %Y at %H:%M:%S")


def _calculate(inputs: dict) -> str:
    expression = inputs.get("expression", "").strip()
    try:
        result = _safe_eval(expression)
        return f"{expression} = {result}"
    except (ValueError, ZeroDivisionError) as exc:
        return f"Calculation error: {exc}"


def _safe_eval(expression: str) -> float:
    """
    Evaluate a math expression via AST — no exec/eval of arbitrary code.
    Raises ValueError for unsupported constructs.
    """
    _ops: dict = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant: {node.value!r}")
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ops:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            return _ops[op_type](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ops:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            return _ops[op_type](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    tree = ast.parse(expression, mode="eval")
    return _eval(tree.body)


def _save_note(inputs: dict) -> str:
    title = inputs.get("title", "Untitled")
    content = inputs.get("content", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 40}\n")
        f.write(f"[{timestamp}] {title}\n")
        f.write(f"{'=' * 40}\n")
        f.write(content.rstrip())
        f.write("\n")
    return f"Note '{title}' saved."


def _read_notes(_inputs: dict) -> str:
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content or "No notes saved yet."
    except FileNotFoundError:
        return "No notes saved yet."
