---
description: 自律開発チームで課題を処理する（提案のみモード）
argument-hint: <課題の説明 または Issue番号>
---
あなたは統括役です。課題: $ARGUMENTS

1. 課題を分析し、.claude/work/<id>.md に引き継ぎ票（課題、受け入れ条件、対象ファイル、リスク、worktreeのパス）を書く。
   ここで一度止め、ユーザーの確認を得る。
2. main時点のベースライン（compileall/pytest/ruffの結果）を取得し、引き継ぎ票に記録する。
3. `git worktree add ../blh-wt/<id> -b ai/<id>-<slug>` を実行する（クラウドでは省略可）。
4. implementer → reviewer → verifier の順に呼ぶ。毎回、引き継ぎ票のパスを渡す。
5. REQUEST_CHANGES か FAIL の場合は、指摘を引き継ぎ票に追記してimplementerに差し戻す。差し戻しは最大2回。
   3回目は止めて、経緯をまとめてユーザーに報告する。
6. 全員がOKなら、ユーザーに次を報告して終わる：
   変更の要約 / git -C <wt> diff --stat / テスト数値 / レビューの指摘と対応 / GUIの実機確認が必要か /
   ユーザーが実行するcommitコマンド案
絶対にcommit・push・merge・worktreeの削除をしない。
