#!/usr/bin/env bash
# bot-common 一括更新スクリプト
#
# 全Botリポジトリの lib/bot-common submodule を最新に更新し、
# テスト実行後にコミット＆プッシュする。
#
# Usage: bash scripts/update-all.sh

set -euo pipefail

BOT_DIRS=(
    "$HOME/dev/parenting-bot"
    "$HOME/dev/ai-news-bot"
    "$HOME/dev/kabu-bot"
    "$HOME/dev/threads-career-bot"
    "$HOME/dev/bookmark-processor"
    "$HOME/dev/note-generator"
)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

failed_bots=()
success_bots=()

echo "=== bot-common 一括更新 ==="
echo ""

for dir in "${BOT_DIRS[@]}"; do
    bot_name=$(basename "$dir")

    if [ ! -d "$dir" ]; then
        echo -e "${YELLOW}[SKIP]${NC} $bot_name: ディレクトリが見つかりません"
        continue
    fi

    if [ ! -d "$dir/lib/bot-common" ]; then
        echo -e "${YELLOW}[SKIP]${NC} $bot_name: submodule未導入"
        continue
    fi

    echo -e "--- ${bot_name} ---"

    cd "$dir"

    # submodule更新
    git submodule update --remote lib/bot-common

    # 変更があるか確認
    if git diff --quiet lib/bot-common; then
        echo -e "${GREEN}[OK]${NC} $bot_name: 既に最新"
        success_bots+=("$bot_name")
        continue
    fi

    # pip install -e
    pip install -e lib/bot-common --quiet 2>/dev/null || true

    # テスト実行（テストがあれば）
    test_passed=true
    if [ -d "tests" ] && [ -n "$(find tests -name 'test_*.py' 2>/dev/null)" ]; then
        if ! python -m pytest tests/ -x -q 2>&1; then
            echo -e "${RED}[FAIL]${NC} $bot_name: テスト失敗"
            failed_bots+=("$bot_name")
            test_passed=false
            # 失敗したBotのsubmodule更新を元に戻す
            git checkout lib/bot-common
            continue
        fi
    else
        # スモークテスト: importが成功するか
        if ! python -c "from bot_common import JST, now_jst; print('import OK')" 2>&1; then
            echo -e "${RED}[FAIL]${NC} $bot_name: import失敗"
            failed_bots+=("$bot_name")
            git checkout lib/bot-common
            continue
        fi
    fi

    # コミット＆プッシュ
    git add lib/bot-common
    git commit -m "chore: update bot-common submodule"
    git push

    echo -e "${GREEN}[OK]${NC} $bot_name: 更新完了"
    success_bots+=("$bot_name")
done

echo ""
echo "=== 結果 ==="
echo -e "${GREEN}成功:${NC} ${success_bots[*]:-なし}"
if [ ${#failed_bots[@]} -gt 0 ]; then
    echo -e "${RED}失敗:${NC} ${failed_bots[*]}"
    echo ""
    echo "失敗したBotを手動で確認してください。"
    exit 1
fi

# バージョン乖離チェック
echo ""
echo "=== submodule commit 一覧 ==="
for dir in "${BOT_DIRS[@]}"; do
    if [ -d "$dir/lib/bot-common" ]; then
        bot_name=$(basename "$dir")
        commit=$(cd "$dir/lib/bot-common" && git rev-parse --short HEAD 2>/dev/null || echo "N/A")
        echo "  $bot_name: $commit"
    fi
done
