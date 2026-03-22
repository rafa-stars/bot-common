# bot-common

Bot プロジェクト共通基盤ライブラリ。

## モジュール

| モジュール | 用途 |
|-----------|------|
| `bot_common.json_parser` | LLM出力用5層フォールバックJSONパーサ |
| `bot_common.timezone` | JST/UTC安全なdatetime処理 |
| `bot_common.logging` | 統一ログ設定 |

外部依存: なし（Python標準ライブラリのみ）

## セットアップ

### 新規Botへの導入

```bash
# submodule追加
git submodule add https://github.com/rafa-stars/bot-common.git lib/bot-common

# editable install
pip install -e lib/bot-common
```

### 既存リポジトリのクローン

```bash
git clone --recurse-submodules <repo-url>
pip install -e lib/bot-common
```

`--recurse-submodules` を忘れた場合:

```bash
git submodule init && git submodule update
pip install -e lib/bot-common
```

### GitHub Actions

`actions/checkout` に `submodules: recursive` を追加:

```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
- run: pip install -e lib/bot-common
```

## 使い方

```python
from bot_common.timezone import JST, now_jst, today_jst, utcnow, ensure_aware
from bot_common.json_parser import extract_json_array, extract_json_object
from bot_common.logging import setup_logging

setup_logging(verbose=False, noisy_libs=["httpx", "urllib3"])
```

### kabu-bot (naive utcnow)

```python
from bot_common.timezone import utcnow as _utcnow_aware

def utcnow():
    """DB互換の naive UTC datetime。"""
    return _utcnow_aware().replace(tzinfo=None)
```

## 更新

### 手動（1Bot）

```bash
cd <bot-repo>
git submodule update --remote lib/bot-common
git add lib/bot-common
git commit -m "chore: update bot-common"
git push
```

### 一括（全Bot）

```bash
bash scripts/update-all.sh
```

## ロールバック

### 前のバージョンに戻す

```bash
cd <bot-repo>/lib/bot-common
git checkout <previous-commit-hash>
cd ../..
git add lib/bot-common
git commit -m "chore: rollback bot-common"
```

### submoduleを完全に外す

```bash
git submodule deinit lib/bot-common
git rm lib/bot-common
rm -rf .git/modules/lib/bot-common
# 旧コードをcore/等に復元
```

## テスト

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## バージョン戦略

- 全Bot同一commit を原則
- `scripts/update-all.sh` で一括更新＋バージョン乖離チェック
- 1Botのみ先行更新は許容（1週間以内に全Bot追随）
