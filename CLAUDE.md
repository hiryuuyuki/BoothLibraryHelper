# BoothLibraryHelper — AI作業規約

## 技術構成（事実のみ）
- Python / PySide6 + qasync / Playwright + BeautifulSoup4 / requests / PyInstaller
- エントリポイント: app/main.py, app/__main__.py
- 依存関係は app/requirements.txt（本体）と requirements-dev.txt（開発用）に書かれたものだけ。
  ここに無いパッケージを import しない・提案なしに追加しない。

## 絶対の禁止事項
- git commit / push / merge / rebase / reset --hard / worktree remove を実行しない（人が行う）
- pip install、requirements の変更をしない（必要なら「提案」として報告する）
- .env、認証情報、Cookie、トークンを読まない・表示しない・ログに出さない
- 自分の worktree 以外のファイルを編集しない
- テストを skip・削除・弱めて通さない

## 編集ルール
- 必要最小限の差分にとどめる。無関係な整形やリファクタリングをしない
- 既存のスタイルに合わせる（ファイル先頭のヘッダーコメント、logger.py の使い方）
- バグ修正は「失敗するテスト → 修正 → テストが通る」の順で行う

## 検証コマンド
- python -m compileall -q app
- python -m pytest -q
- python -m ruff check app tests

## コミットメッセージの規約（人がコミットするときの参考）
- `fix(storage): ...` / `test(db): ...` / `feat(ui): ...`（Conventional Commits）

## テストの方針
- GUI（ui_main.py, *_dialog.py）は最初はテスト対象にしない。
  ロジック層（models, db, storage, version, utils, settings）から始める
- ネットワークに接続するテストは禁止。BOOTH の HTML は tests/fixtures から読む

## チーム運用
- 課題は `/team <内容>` で統括に渡す。手順は .claude/commands/team.md
- 引き継ぎ票は .claude/work/<id>.md（git管理外）
