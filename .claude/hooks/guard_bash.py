"""PreToolUse hook: 危険なBashコマンドをブロックする。

exit 0 = 許可 / exit 2 = ブロック（stderr の理由が Claude に返る）
permissions.deny は書き方次第ですり抜けられるため、ここで二重に守る。
"""
import json
import re
import sys

# git のグローバルオプション（-C <path>、-c k=v、--git-dir=...、--no-pager など）をサブコマンドの前に許容する。
# これが無いと `git -C <worktree> commit` のような形で判定をすり抜けてしまう。
_GIT_ARG = r"""(?:"[^"]*"|'[^']*'|\S+)"""
_GIT = r"\bgit(?:\s+(?:-[Cc]\s+" + _GIT_ARG + r"|--[\w-]+(?:=" + _GIT_ARG + r")?|-[A-Za-z]))*\s+"

BLOCK = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r", "rm -rf は禁止です"),
    (r"\bRemove-Item\b.*-Recurse", "再帰的な削除は禁止です"),
    (_GIT + r"(commit|push|merge|rebase|cherry-pick)\b", "git の履歴操作は人が行います"),
    (_GIT + r"reset\s+--hard\b|" + _GIT + r"clean\s+-[a-z]*f", "変更を捨てる操作は禁止です"),
    (r"--force\b|\s-f\s+origin", "force 系の操作は禁止です"),
    (r"\bpip3?\s+(install|uninstall)\b|\buv\s+(add|pip)\b", "依存関係の変更は提案だけにしてください"),
    (r"\b(printenv|env)\s*($|\|)|\bset\s*$|Get-ChildItem\s+env:", "環境変数を表示しないでください"),
    (r"(^|[\s/\\])\.env\b|cookies?\.(json|txt|db)", "秘密情報のファイルには触れないでください"),
    (r"\b(DROP|TRUNCATE)\s+TABLE\b|\bDELETE\s+FROM\b", "破壊的なSQLは禁止です"),
    (r"\bcurl\b.*\s-X\s*(POST|PUT|DELETE)", "外部への書き込みリクエストは禁止です"),
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[guard] BLOCKED: 入力を解析できないため安全側でブロックしました", file=sys.stderr)
        return 2
    cmd = data.get("tool_input", {}).get("command", "")
    for pattern, reason in BLOCK:
        if re.search(pattern, cmd, re.IGNORECASE):
            print(f"[guard] BLOCKED: {reason}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
