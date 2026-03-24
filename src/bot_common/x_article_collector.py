"""X記事（Articles）の収集モジュール（SocialData API経由）。

全Botで共用。ジャンルフィルタリングは呼び出し側で行う。
optional dependency: pip install bot-common[socialdata]
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from bot_common.timezone import now_jst, utcnow

logger = logging.getLogger(__name__)

# --- 定数 ---

_SEARCH_URL = "https://api.socialdata.tools/twitter/search"
_ARTICLE_URL = "https://api.socialdata.tools/twitter/article"

_RETRY_MAX = 3
_RETRY_BACKOFF_BASE = 1  # 秒: 1, 2, 4

_CACHE_TTL_DAYS = 7
_CACHE_MAX_ENTRIES = 1000

# 日本語判定: ひらがな・カタカナ・漢字
_JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")


# --- dataclass ---


@dataclass
class XArticle:
    """収集したX記事。"""

    tweet_id: str
    author_username: str
    author_display_name: str
    author_followers: int
    title: str
    body_text: str
    preview_text: str
    tweet_url: str
    thumbnail_url: str
    likes: int
    retweets: int
    replies: int
    quotes: int
    bookmarks: int
    views: int
    published_at: str  # ISO format
    is_japanese: bool
    collected_at: datetime = field(default_factory=now_jst)


# --- 例外 ---


class SocialDataError(Exception):
    """SocialData API関連の基底例外。"""


class InsufficientBalanceError(SocialDataError):
    """HTTP 402: 残高不足。"""


class RateLimitError(SocialDataError):
    """HTTP 429: レート制限超過。"""


# --- コレクター ---


class XArticleCollector:
    """SocialData APIを使ったX記事コレクター。"""

    def __init__(self, api_key: str, cache_dir: Path | None = None) -> None:
        """コレクターを初期化する。

        Args:
            api_key: SocialData APIキー。
            cache_dir: キャッシュ保存先ディレクトリ。Noneならキャッシュ無効。
        """
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "httpx is required: pip install bot-common[socialdata]"
            ) from exc

        self._api_key = api_key
        self._cache_dir = cache_dir / "x_articles" if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    # --- public API ---

    def search_articles(
        self,
        min_faves: int = 500,
        since: str | None = None,
        until: str | None = None,
        max_results: int = 200,
    ) -> list[dict]:
        """X記事を検索する。

        Args:
            min_faves: 最小いいね数。
            since: 検索開始日 (YYYY-MM-DD)。
            until: 検索終了日 (YYYY-MM-DD)。
            max_results: 最大取得件数。

        Returns:
            ツイート辞書のリスト。
        """
        query_parts = [
            "url:x.com/i/article",
            f"min_faves:{min_faves}",
            "-filter:replies",
        ]
        if since:
            query_parts.append(f"since:{since}")
        if until:
            query_parts.append(f"until:{until}")
        query = " ".join(query_parts)

        logger.info("X記事を検索: query=%s, max_results=%d", query, max_results)

        tweets: list[dict] = []
        cursor: str | None = None

        while len(tweets) < max_results:
            params: dict[str, str] = {"query": query}
            if cursor:
                params["next_cursor"] = cursor

            data = self._get(_SEARCH_URL, params=params)
            batch = data.get("tweets", [])
            if not batch:
                break

            tweets.extend(batch)
            cursor = data.get("next_cursor", "")
            if not cursor:
                break

        tweets = tweets[:max_results]
        logger.info("検索完了: %d件取得", len(tweets))
        return tweets

    def get_article_detail(self, tweet_id: str) -> dict | None:
        """記事の詳細を取得する（キャッシュ対応）。

        Args:
            tweet_id: ツイートID。

        Returns:
            記事詳細辞書。取得失敗時はNone。
        """
        cached = self._load_cache(tweet_id)
        if cached is not None:
            logger.debug("キャッシュヒット: tweet_id=%s", tweet_id)
            return cached

        url = f"{_ARTICLE_URL}/{tweet_id}"
        try:
            data = self._get(url)
        except SocialDataError:
            logger.warning("記事詳細の取得に失敗: tweet_id=%s", tweet_id)
            return None

        self._save_cache(tweet_id, data)
        return data

    def collect_japanese_articles(
        self,
        min_faves: int = 500,
        since: str | None = None,
        until: str | None = None,
        max_results: int = 200,
    ) -> list[XArticle]:
        """日本語のX記事を収集する。

        検索 → 日本語フィルタ → 記事詳細取得 → XArticle変換。

        Args:
            min_faves: 最小いいね数。
            since: 検索開始日 (YYYY-MM-DD)。
            until: 検索終了日 (YYYY-MM-DD)。
            max_results: 最大取得件数。

        Returns:
            日本語X記事のリスト。
        """
        tweets = self.search_articles(
            min_faves=min_faves,
            since=since,
            until=until,
            max_results=max_results,
        )

        japanese_tweets = [t for t in tweets if self._is_japanese_author(t.get("user", {}))]
        logger.info(
            "日本語フィルタ: %d/%d件が日本語著者",
            len(japanese_tweets),
            len(tweets),
        )

        articles: list[XArticle] = []
        for tweet in japanese_tweets:
            tweet_id = str(tweet.get("id_str", tweet.get("id", "")))
            detail = self.get_article_detail(tweet_id)

            article_data = detail.get("article", {}) if detail else {}
            body_text = self._extract_body_text(article_data)
            user = tweet.get("user", {})

            article = XArticle(
                tweet_id=tweet_id,
                author_username=user.get("screen_name", ""),
                author_display_name=user.get("name", ""),
                author_followers=user.get("followers_count", 0),
                title=article_data.get("title", ""),
                body_text=body_text,
                preview_text=article_data.get("preview_text", ""),
                tweet_url=f"https://x.com/{user.get('screen_name', '')}/status/{tweet_id}",
                thumbnail_url=article_data.get("cover_url", ""),
                likes=tweet.get("favorite_count", 0),
                retweets=tweet.get("retweet_count", 0),
                replies=tweet.get("reply_count", 0),
                quotes=tweet.get("quote_count", 0),
                bookmarks=tweet.get("bookmark_count", 0),
                views=tweet.get("views_count", 0),
                published_at=tweet.get("created_at", ""),
                is_japanese=True,
            )
            articles.append(article)

        logger.info("日本語記事収集完了: %d件", len(articles))
        self._cleanup_cache()
        return articles

    # --- 内部メソッド ---

    def _is_japanese_author(self, user: dict) -> bool:
        """著者が日本語ユーザーかを判定する。

        user.name と user.description に日本語文字が含まれるかで判定。

        Args:
            user: ユーザー辞書。

        Returns:
            日本語ユーザーならTrue。
        """
        name = user.get("name", "")
        description = user.get("description", "")
        return bool(_JAPANESE_RE.search(name) or _JAPANESE_RE.search(description))

    def _extract_body_text(self, article_data: dict) -> str:
        """記事の全文テキストを抽出する。

        content_state.blocks の各blockの text を改行で結合。

        Args:
            article_data: 記事データ辞書。

        Returns:
            全文テキスト。
        """
        content_state = article_data.get("content_state", {})
        blocks = content_state.get("blocks", [])
        texts = [block.get("text", "") for block in blocks if block.get("text")]
        return "\n".join(texts)

    def _get(self, url: str, params: dict[str, str] | None = None) -> dict:
        """HTTP GETリクエスト（リトライ付き）。

        Args:
            url: リクエストURL。
            params: クエリパラメータ。

        Returns:
            レスポンスJSON辞書。

        Raises:
            InsufficientBalanceError: HTTP 402。
            RateLimitError: HTTP 429でリトライ上限超過。
            SocialDataError: その他のAPIエラー。
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(_RETRY_MAX):
            try:
                response = httpx.get(
                    url, params=params, headers=headers, timeout=30.0
                )

                if response.status_code == 402:
                    raise InsufficientBalanceError(
                        "SocialData API残高不足 (HTTP 402)。アカウントを確認してください。"
                    )

                if response.status_code == 429:
                    wait = _RETRY_BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "レート制限 (HTTP 429)。%d秒後にリトライ (%d/%d)",
                        wait,
                        attempt + 1,
                        _RETRY_MAX,
                    )
                    time.sleep(wait)
                    last_error = RateLimitError(f"HTTP 429 (attempt {attempt + 1})")
                    continue

                if response.status_code >= 500:
                    wait = _RETRY_BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "サーバーエラー (HTTP %d)。%d秒後にリトライ (%d/%d)",
                        response.status_code,
                        wait,
                        attempt + 1,
                        _RETRY_MAX,
                    )
                    time.sleep(wait)
                    last_error = SocialDataError(
                        f"HTTP {response.status_code} (attempt {attempt + 1})"
                    )
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                raise SocialDataError(f"HTTP error: {exc}") from exc
            except httpx.TimeoutException as exc:
                wait = _RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "タイムアウト。%d秒後にリトライ (%d/%d)",
                    wait,
                    attempt + 1,
                    _RETRY_MAX,
                )
                time.sleep(wait)
                last_error = exc
                continue
            except httpx.RequestError as exc:
                wait = _RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "ネットワークエラー: %s。%d秒後にリトライ (%d/%d)",
                    exc,
                    wait,
                    attempt + 1,
                    _RETRY_MAX,
                )
                time.sleep(wait)
                last_error = exc
                continue

        if isinstance(last_error, RateLimitError):
            raise last_error
        raise SocialDataError(
            f"リトライ上限超過 ({_RETRY_MAX}回): {last_error}"
        ) from last_error

    # --- キャッシュ ---

    def _load_cache(self, tweet_id: str) -> dict | None:
        """キャッシュからデータを読み込む。

        Args:
            tweet_id: ツイートID。

        Returns:
            キャッシュデータ。無ければNone。
        """
        if not self._cache_dir:
            return None

        cache_file = self._cache_dir / f"{tweet_id}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data.get("_cached_at", ""))
            if utcnow() - cached_at > timedelta(days=_CACHE_TTL_DAYS):
                cache_file.unlink(missing_ok=True)
                return None
            return data
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.debug("キャッシュ読み込みエラー: %s (%s)", cache_file, exc)
            return None

    def _save_cache(self, tweet_id: str, data: dict) -> None:
        """データをキャッシュに保存する。

        Args:
            tweet_id: ツイートID。
            data: 保存するデータ。
        """
        if not self._cache_dir:
            return

        cache_data = {**data, "_cached_at": utcnow().isoformat()}
        cache_file = self._cache_dir / f"{tweet_id}.json"
        try:
            cache_file.write_text(
                json.dumps(cache_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("キャッシュ書き込みエラー: %s (%s)", cache_file, exc)

    def _cleanup_cache(self) -> None:
        """TTL超過(7日)または上限(1000件)超過のキャッシュを削除する。"""
        if not self._cache_dir:
            return

        try:
            cache_files = sorted(
                self._cache_dir.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
            )
        except OSError as exc:
            logger.warning("キャッシュクリーンアップエラー: %s", exc)
            return

        now = utcnow()
        remaining: list[Path] = []

        for f in cache_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                cached_at = datetime.fromisoformat(data.get("_cached_at", ""))
                if now - cached_at > timedelta(days=_CACHE_TTL_DAYS):
                    f.unlink(missing_ok=True)
                    continue
            except (json.JSONDecodeError, ValueError, OSError):
                f.unlink(missing_ok=True)
                continue
            remaining.append(f)

        # 上限超過: 古い順に削除
        if len(remaining) > _CACHE_MAX_ENTRIES:
            to_remove = remaining[: len(remaining) - _CACHE_MAX_ENTRIES]
            for f in to_remove:
                f.unlink(missing_ok=True)
            logger.info(
                "キャッシュ上限超過: %d件削除 (残%d件)",
                len(to_remove),
                _CACHE_MAX_ENTRIES,
            )


def article_to_dict(article: XArticle) -> dict:
    """XArticleを辞書に変換する（JSON保存用）。

    Args:
        article: XArticleインスタンス。

    Returns:
        辞書。datetimeはISO形式文字列に変換。
    """
    d = asdict(article)
    if isinstance(d.get("collected_at"), datetime):
        d["collected_at"] = d["collected_at"].isoformat()
    return d
