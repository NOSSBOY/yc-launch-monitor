"""HTTP fetching for YC Speedrun companies."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from yc_launch_monitor.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 YCLaunchMonitor/0.1"
)
OFFICIAL_SPEEDRUN_API_URL = (
    "https://speedrun-api.a16z.com/api/companies/companies/?limit=100&ordering=name"
)


class YCSpeedrunFetchError(RuntimeError):
    """Raised when YC Speedrun data cannot be retrieved."""


class YCSpeedrunFetcher:
    """Fetch raw company data backing YC Speedrun."""

    def __init__(self, settings: Settings, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._settings = settings
        self._user_agent = user_agent

    def fetch_text(self, url: str | None = None) -> str:
        """Retrieve raw text / HTML / JSON from the Speedrun URL."""
        target_url = url or self._settings.yc_speedrun_url
        logger.info("Fetching Speedrun data from %s", target_url)

        request = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise YCSpeedrunFetchError(
                f"Failed to fetch {target_url} with HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise YCSpeedrunFetchError(f"Failed to fetch {target_url}: {exc}") from exc

    def fetch_companies(self, url: str | None = None) -> list[dict[str, Any]]:
        """
        Fetch Speedrun page / API and extract raw company dictionaries.

        Supports the official REST API endpoint (with pagination), direct JSON endpoints,
        embedded __NEXT_DATA__ JSON script blocks, and embedded company lists.
        """
        target_url = url or self._settings.yc_speedrun_url

        # Fast path: If querying the standard speedrun.a16z.com web page, try the direct API endpoint
        if target_url in (
            "https://speedrun.a16z.com/companies/",
            "https://speedrun.a16z.com/companies",
            "https://speedrun.a16z.com/",
            "https://speedrun.a16z.com",
            OFFICIAL_SPEEDRUN_API_URL,
        ):
            try:
                all_items: list[dict[str, Any]] = []
                next_url: str | None = OFFICIAL_SPEEDRUN_API_URL
                while next_url:
                    content = self.fetch_text(next_url)
                    data = json.loads(content)
                    items = self._extract_items_from_dict(data)
                    if not items:
                        break
                    all_items.extend(items)
                    next_url = data.get("next") if isinstance(data, dict) else None
                    if len(all_items) >= 2000:
                        break

                if all_items:
                    logger.info("Retrieved %s companies from Speedrun REST API", len(all_items))
                    return all_items
            except Exception as exc:
                logger.warning(
                    "Direct Speedrun API query failed (%s); falling back to page fetch %s",
                    exc,
                    target_url,
                )

        content = self.fetch_text(target_url)
        content_stripped = content.strip()

        # Case 1: Direct JSON response
        if content_stripped.startswith("{") or content_stripped.startswith("["):
            try:
                data = json.loads(content_stripped)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
                if isinstance(data, dict):
                    return self._extract_items_from_dict(data)
            except json.JSONDecodeError:
                pass

        # Case 2: Embedded Next.js __NEXT_DATA__ JSON in HTML
        next_data_match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if next_data_match:
            try:
                next_json = json.loads(next_data_match.group(1))
                items = self._extract_items_from_dict(next_json)
                if items:
                    logger.info("Extracted %s companies from __NEXT_DATA__", len(items))
                    return items
            except json.JSONDecodeError as exc:
                logger.warning("Found __NEXT_DATA__ script but failed to parse JSON: %s", exc)

        # Case 3: Embedded generic JSON scripts with company data
        script_matches = re.findall(
            r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for script_content in script_matches:
            try:
                script_json = json.loads(script_content.strip())
                if isinstance(script_json, dict):
                    items = self._extract_items_from_dict(script_json)
                    if items:
                        return items
                elif isinstance(script_json, list):
                    items = [item for item in script_json if isinstance(item, dict)]
                    if items:
                        return items
            except json.JSONDecodeError:
                continue

        logger.warning("No structured company items could be extracted from Speedrun response")
        return []

    def _extract_items_from_dict(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Recursively inspect dictionary keys to find company item lists."""
        for key in ("companies", "hits", "items", "results", "data", "speedrun_companies"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for subkey in ("results", "items", "companies", "data"):
                    subval = value.get(subkey)
                    if isinstance(subval, list):
                        return [item for item in subval if isinstance(item, dict)]

        # Check pageProps / nested structures
        props = payload.get("props", {})
        if isinstance(props, dict):
            page_props = props.get("pageProps", {})
            if isinstance(page_props, dict):
                for key in ("companies", "hits", "items", "results", "data"):
                    value = page_props.get(key)
                    if isinstance(value, list):
                        return [item for item in value if isinstance(item, dict)]
                    if isinstance(value, dict):
                        for subkey in ("results", "items", "companies", "data"):
                            subval = value.get(subkey)
                            if isinstance(subval, list):
                                return [item for item in subval if isinstance(item, dict)]

        return []
