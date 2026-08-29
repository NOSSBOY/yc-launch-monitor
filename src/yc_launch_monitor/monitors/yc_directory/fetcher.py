"""HTTP fetching for the YC Directory (Algolia-backed)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from yc_launch_monitor.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 YCLaunchMonitor/0.1"
)


class YCDirectoryFetchError(RuntimeError):
    """Raised when YC Directory data cannot be retrieved."""


@dataclass(frozen=True, slots=True)
class AlgoliaConfig:
    """Algolia connection details used by the YC companies page."""

    app_id: str
    api_key: str
    index_name: str


class YCDirectoryFetcher:
    """Fetch raw company records backing https://www.ycombinator.com/companies."""

    def __init__(self, settings: Settings, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._settings = settings
        self._user_agent = user_agent

    def fetch_company_pages(self) -> list[dict[str, Any]]:
        """Retrieve all Algolia pages and return raw hit dictionaries."""
        config = self._resolve_algolia_config()
        first_page = self._query_algolia(config, page=0)
        hits = list(first_page.get("hits", []))
        total_pages = int(first_page.get("nbPages", 1))

        logger.info(
            "Fetched YC Directory page 1/%s (%s companies on page)",
            total_pages,
            len(first_page.get("hits", [])),
        )

        for page in range(1, total_pages):
            page_payload = self._query_algolia(config, page=page)
            page_hits = page_payload.get("hits", [])
            hits.extend(page_hits)
            logger.info(
                "Fetched YC Directory page %s/%s (%s companies on page)",
                page + 1,
                total_pages,
                len(page_hits),
            )

        logger.info("Retrieved %s raw YC Directory companies", len(hits))
        return hits

    def _resolve_algolia_config(self) -> AlgoliaConfig:
        if self._settings.yc_algolia_app_id and self._settings.yc_algolia_api_key:
            logger.debug("Using Algolia credentials from environment variables")
            return AlgoliaConfig(
                app_id=self._settings.yc_algolia_app_id,
                api_key=self._settings.yc_algolia_api_key,
                index_name=self._settings.yc_algolia_index,
            )

        logger.info(
            "Algolia credentials not configured; extracting public search key from %s",
            self._settings.yc_companies_url,
        )
        html = self._fetch_text(self._settings.yc_companies_url)
        return self._extract_algolia_config(html)

    def _query_algolia(self, config: AlgoliaConfig, page: int) -> dict[str, Any]:
        host = f"https://{config.app_id.lower()}-dsn.algolia.net"
        url = f"{host}/1/indexes/{config.index_name}/query"
        body = json.dumps(
            {
                "query": "",
                "page": page,
                "hitsPerPage": self._settings.yc_algolia_hits_per_page,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
                "X-Algolia-Application-Id": config.app_id,
                "X-Algolia-API-Key": config.api_key,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise YCDirectoryFetchError(
                f"Algolia query failed with HTTP {exc.code}: {details}"
            ) from exc
        except urllib.error.URLError as exc:
            raise YCDirectoryFetchError(f"Algolia query failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise YCDirectoryFetchError("Algolia response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise YCDirectoryFetchError("Algolia response must be a JSON object")

        return payload

    def _fetch_text(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self._user_agent},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise YCDirectoryFetchError(
                f"Failed to fetch {url} with HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise YCDirectoryFetchError(f"Failed to fetch {url}: {exc}") from exc

    def _extract_algolia_config(self, html: str) -> AlgoliaConfig:
        opts_match = re.search(r'window\.AlgoliaOpts\s*=\s*(\{.*?\});', html, re.DOTALL)
        if opts_match:
            try:
                opts = json.loads(opts_match.group(1))
                app_id = opts.get("app")
                api_key = opts.get("key")
                if app_id and api_key:
                    index_name = self._settings.yc_algolia_index
                    return AlgoliaConfig(app_id=str(app_id), api_key=str(api_key), index_name=index_name)
            except Exception:
                pass

        app_id = self._find_first(
            html,
            patterns=[
                r'AlgoliaOpts\s*=\s*\{[^}]*"(?:app|applicationId)"\s*:\s*"([A-Z0-9]{8,16})"',
                r'"(?:app|applicationId)"\s*:\s*"([A-Z0-9]{8,16})"',
                r'"X-Algolia-Application-Id"\s*:\s*"([A-Z0-9]{8,16})"',
                r'(?:app|applicationId)["\']\s*:\s*["\']([A-Z0-9]{8,16})["\']',
            ],
            label="Algolia application id",
        )
        api_key = self._find_first(
            html,
            patterns=[
                r'AlgoliaOpts\s*=\s*\{[^}]*"(?:key|apiKey|searchApiKey)"\s*:\s*"([A-Za-z0-9+/=_%-]{20,})"',
                r'"(?:key|apiKey|searchApiKey)"\s*:\s*"([A-Za-z0-9+/=_%-]{20,})"',
                r'"searchApiKey"\s*:\s*"([A-Za-z0-9+/=_%-]{20,})"',
                r'(?:key|apiKey|searchApiKey)["\']\s*:\s*["\']([A-Za-z0-9+/=_%-]{20,})["\']',
            ],
            label="Algolia search api key",
        )

        index_name = self._settings.yc_algolia_index
        index_match = re.search(
            r'indexes\s*:\s*\[\s*["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        if index_match:
            index_name = index_match.group(1)

        return AlgoliaConfig(app_id=app_id, api_key=api_key, index_name=index_name)

    @staticmethod
    def _find_first(html: str, patterns: list[str], label: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        raise YCDirectoryFetchError(f"Could not extract {label} from YC companies page")

