# 基本設計書 - bot-common

## 1. システム概要

全Botプロジェクト共通の Python 基盤ライブラリ。Python 標準ライブラリのみに依存する軽量設計で、git submodule として各Botに組み込まれる。

- **目的**: Bot間で重複する共通処理を一元管理し、保守コストを削減する
- **対象**: parenting-bot, ai-news-bot, kabu-bot, threads-career-bot, bookmark-processor, note-generator（全6Bot）
- **配布形式**: git submodule + editable install (`pip install -e lib/bot-common`)
- **リポジトリ**: https://github.com/rafa-stars/bot-common.git

## 2. バッチ一覧

本ライブラリ単体でのバッチ処理はなし。各Botのバッチ処理から呼び出される。

### 保守スクリプト

| スクリプト | 実行タイミング | 処理概要 |
|---|---|---|
| `scripts/update-all.sh` | 手動（bot-common 更新時） | 全6Botの submodule 最新化 → pip install → テスト → commit & push |

## 3. 画面一覧（CLI）

なし（ライブラリのため画面・CLIを持たない）

## 4. 帳票・レポート一覧

なし

## 5. 外部送信一覧

| 送信先 | 受信元 | プロトコル | 認証 | 内容 |
|---|---|---|---|---|
| SocialData API | x_article_collector | HTTPS | API Key (`SOCIALDATA_API_KEY`) | X記事（Articles）検索・詳細取得 |

※ x_article_collector は optional 依存（`pip install bot-common[socialdata]`）

## 6. 機能概要

### 6.1 json_parser（196行）

LLM出力用の5層フォールバック JSONパーサ。

- **背景**: Claude/ChatGPT の出力に不正JSON（改行埋め込み、末尾カンマ等）が頻発
- **API**: `extract_json_array(text)` → List[dict], `extract_json_object(text)` → dict
- **フォールバック順序**: 直接パース → 改行修正 → 末尾カンマ削除 → strict=False → オブジェクト単体抽出
- **付加機能**: Markdown コードブロック自動削除

### 6.2 timezone（60行）

JST/UTC 安全な datetime 処理。

- **背景**: GitHub Actions（UTC）とBot（JST基準）のタイムゾーン不整合を防止
- **API**: `now_jst()`, `today_jst()`, `utcnow()`, `ensure_aware(dt, tz=JST)`
- **定数**: `JST = ZoneInfo("Asia/Tokyo")`
- **互換性**: kabu-bot の naive UTC datetime に対応

### 6.3 logging（36行）

統一ログ設定。

- **API**: `setup_logging(verbose=False, noisy_libs=["httpx", "urllib3"])`
- **機能**: 外部ライブラリ（httpx等）のログを CRITICAL に抑制、日時フォーマット統一

### 6.4 x_article_collector（481行）

SocialData API 経由の X記事（Articles）収集モジュール。

- **背景**: ai-news-bot のプライベートAPI廃止対応として追加
- **主要クラス**: `XArticleCollector`
- **API**: `search_articles()`, `get_article_detail()`, `collect_japanese_articles()`
- **リトライ**: HTTP 429/5xx → exponential backoff(1,2,4秒)、HTTP 402 → 即停止
- **キャッシュ**: TTL=7日、上限1000件（FIFO削除）
- **日本語判定**: ひらがな・カタカナ・漢字で判定
- **optional 依存**: httpx >= 0.27

## 7. 非機能要件

### 可用性
- 外部依存なし（標準ライブラリのみ）で環境構築の失敗リスクを最小化
- x_article_collector は optional 依存として分離

### セキュリティ
- API Key は環境変数から取得（ハードコードなし）

### パフォーマンス
- キャッシュ（TTL=7日、上限1000件）で API 呼び出し回数を削減

### データ整合性
- タイムゾーン処理の統一により、全BotでJST/UTCの不整合を防止

## 8. 考慮事項一覧

| # | 項目 | 内容 |
|---|---|---|
| 1 | バージョン戦略 | 全Bot同一commit を目指す。1Bot先行更新は許容（1週間以内に全Bot追随） |
| 2 | ロールバック | `git checkout <previous-commit-hash>` で個別Bot単位でロールバック可能 |
| 3 | テスト | 各モジュール単体テスト + 消費者テスト（実際のLLM出力サンプル、DBラウンドトリップ） |
| 4 | 拡張方針 | 2Bot以上で共通化できる処理のみ追加。単一Bot固有の処理は追加しない |

## 9. 技術スタック

| 項目 | 技術 |
|---|---|
| 言語 | Python 3.12+ |
| 基本依存 | なし（標準ライブラリのみ） |
| Optional 依存 | httpx >= 0.27（x_article_collector用） |
| テスト | pytest >= 8.0（30テスト） |
| ビルド | setuptools >= 68.0 |
| 配布 | git submodule + editable install |

## 10. 導入手順

### 新規Bot への導入

```bash
git submodule add https://github.com/rafa-stars/bot-common.git lib/bot-common
pip install -e lib/bot-common
```

### GitHub Actions 設定

```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
- run: pip install -e lib/bot-common
```

### 全Bot一括更新

```bash
cd bot-common
bash scripts/update-all.sh
```
