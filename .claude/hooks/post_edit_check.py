"""PostToolUse hook: 編集した .py に構文エラーがあれば exit 2 で Claude に差し戻す。"""
import json
import py_compile
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = data.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        return 0
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"[post_edit] 構文エラー: {e.msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
