# 联网搜索
import json
from typing import Any

import httpx

from app.common.config.plugins_config import SearXNG_API_URL, url_meta_search, api_key


async def meta_search_async(query: str) -> Any:
    """使用 Meta Search 进行联网搜索（异步）。

    该函数常被 Agent 作为工具函数注册；如果不提供 description，LangChain 会使用此 docstring 作为工具描述。

    Args:
        query (str): 搜索关键词。

    Returns:
        Any: Meta Search 的 JSON 响应。
    """
    url = url_meta_search
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "scope": "webpage",
        "includeSummary": False,
        "size": 10,
        "includeRawContent": False,
        "conciseSnippet": False,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


async def searxng_search_async(query: str) -> Any:
    """使用 SearXNG 进行联网搜索（异步）。

    Args:
        query (str): 搜索关键词。

    Returns:
        Any: SearXNG 的 JSON 响应。
    """
    params = {
        "q": query,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(SearXNG_API_URL, params=params)
        response.raise_for_status()
        return response.json()
