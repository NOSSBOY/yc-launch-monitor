"""HTTP fetching and API provider abstraction for LinkedIn posts."""

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
DEFAULT_LINKEDIN_POSTS_API_URL = "https://api.linkedin.com/v2/posts"


class LinkedInFetchError(RuntimeError):
    """Raised when LinkedIn post data cannot be retrieved via API or provider."""


class LinkedInFetcher:
    """
    Fetch posts matching founder and launch announcements from an approved LinkedIn provider/API.

    Adheres strictly to platform policies and requires approved API credentials
    (e.g., LINKEDIN_ACCESS_TOKEN) for live network operations.
    """

    def __init__(
        self,
        settings: Settings,
        user_agent: str = DEFAULT_USER_AGENT,
        api_base_url: str = DEFAULT_LINKEDIN_POSTS_API_URL,
    ) -> None:
        self._settings = settings
        self._user_agent = user_agent
        self._api_base_url = api_base_url

    def fetch_recent_posts(
        self,
        query: str | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query the LinkedIn API / approved provider for recent posts.

        Raises LinkedInFetchError if API access token is missing or if the API returns an error.
        """
        token = self._settings.linkedin_access_token
        if not token:
            raise LinkedInFetchError(
                "LINKEDIN_ACCESS_TOKEN is not configured. Live LinkedIn monitoring requires "
                "an approved LinkedIn Developer OAuth 2.0 access token in environment variables or .env. "
                "Use offline fixtures for local and automated testing."
            )

        query_str = query or getattr(self._settings, "linkedin_search_query", "YC OR Speedrun")
        limit = max_results or 50

        params = {
            "q": "search",
            "keywords": query_str,
            "count": str(limit),
        }
        url = f"{self._api_base_url}?{urllib.parse.urlencode(params)}"
        logger.info("Searching LinkedIn posts via API: query=%r", query_str)

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
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
                raise LinkedInFetchError(
                    "LinkedIn API authentication failed: invalid or expired access token"
                ) from exc
            if exc.code == 429:
                raise LinkedInFetchError("LinkedIn API rate limit exceeded (HTTP 429)") from exc
            raise LinkedInFetchError(
                f"LinkedIn API query failed with HTTP {exc.code}: {details}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LinkedInFetchError(f"Failed to connect to LinkedIn API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LinkedInFetchError("LinkedIn API response was not valid JSON") from exc

        return self._extract_posts_list(payload)

    def _extract_posts_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract elements or posts array from LinkedIn REST payload."""
        elements = payload.get("elements") or payload.get("posts") or payload.get("data")
        if isinstance(elements, list):
            return [e for e in elements if isinstance(e, dict)]
        return []
