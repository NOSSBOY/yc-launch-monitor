"""HTTP fetching for X/Twitter posts using the X API v2."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from yc_launch_monitor.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "YCLaunchMonitor/0.1 (+https://github.com/)"
X_API_SEARCH_RECENT_URL = "https://api.x.com/2/tweets/search/recent"


class XFetchError(RuntimeError):
    """Raised when X/Twitter data cannot be retrieved via the API."""


class XFetcher:
    """Fetch recent tweets matching founder/launch queries from X API v2."""

    def __init__(self, settings: Settings, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._settings = settings
        self._user_agent = user_agent

    def search_recent_posts(
        self,
        query: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query X API v2 for recent tweets matching the search criteria.

        Raises XFetchError if credentials are missing or if the API returns an error.
        """
        token = self._settings.x_bearer_token
        if not token:
            raise XFetchError(
                "X_BEARER_TOKEN is not configured. Supply a valid X API Bearer token in "
                "environment variables or .env to query live posts."
            )

        query_str = query or self._settings.x_search_query
        limit = max(10, min(max_results or self._settings.x_max_results, 100))

        params = {
            "query": query_str,
            "max_results": str(limit),
            "tweet.fields": "author_id,created_at,text,entities,conversation_id",
            "expansions": "author_id",
            "user.fields": "name,username,description,url",
        }
        url = f"{X_API_SEARCH_RECENT_URL}?{urllib.parse.urlencode(params)}"
        logger.info("Searching X posts via API: query=%r", query_str)

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                raise XFetchError("X API authentication failed: invalid or expired Bearer token") from exc
            if exc.code == 429:
                raise XFetchError("X API rate limit exceeded (HTTP 429)") from exc
            raise XFetchError(f"X API query failed with HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise XFetchError(f"Failed to connect to X API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise XFetchError("X API response was not valid JSON") from exc

        return self._stitch_tweets_with_users(payload)

    def _stitch_tweets_with_users(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Combine data tweets with user expansion metadata for convenient parsing."""
        data = payload.get("data", [])
        if not isinstance(data, list):
            return []

        includes = payload.get("includes", {})
        users = {u.get("id"): u for u in includes.get("users", []) if isinstance(u, dict)}

        stitched: list[dict[str, Any]] = []
        for tweet in data:
            if not isinstance(tweet, dict):
                continue
            author_id = tweet.get("author_id")
            user_obj = users.get(author_id, {})
            enriched_tweet = dict(tweet)
            enriched_tweet["author_name"] = user_obj.get("name")
            enriched_tweet["author_username"] = user_obj.get("username")
            enriched_tweet["author_url"] = user_obj.get("url")
            stitched.append(enriched_tweet)

        return stitched
