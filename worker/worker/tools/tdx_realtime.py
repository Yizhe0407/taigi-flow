"""TDX real-time bus arrival tool."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import aiohttp

from . import register
from .base import BaseTool

logger = logging.getLogger(__name__)

_TDX_TOKEN_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect"
    "/protocol/openid-connect/token"
)
_TDX_API_BASE = "https://tdx.transportdata.tw/api/basic/v2"
_REQUEST_TIMEOUT = 8.0

# Module-level token cache: (access_token, expire_epoch)
_token_cache: tuple[str, float] | None = None


async def _get_token() -> str:
    global _token_cache

    client_id = os.getenv("TDX_CLIENT_ID", "")
    client_secret = os.getenv("TDX_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise RuntimeError("TDX_CLIENT_ID / TDX_CLIENT_SECRET not set")

    # Refresh 5 min before expiry
    if _token_cache is not None:
        token, expire_at = _token_cache
        if time.time() < expire_at - 300:
            return token

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TDX_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
        )
        resp.raise_for_status()
        body = await resp.json()

    access_token: str = body["access_token"]
    expires_in: int = body.get("expires_in", 1800)
    _token_cache = (access_token, time.time() + expires_in)
    logger.info("TDX token refreshed, expires_in=%ds", expires_in)
    return access_token


class TdxBusArrivalTool(BaseTool):
    name = "tdx.bus_arrival"
    description = "查詢公車即時到站時間（TDX API）"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市代碼，例如 YunlinCounty（雲林縣）、"
                    "Taipei（台北市）",
            },
            "route": {
                "type": "string",
                "description": "路線名稱，例如 Y02",
            },
            "stop": {
                "type": "string",
                "description": "站名（可選，僅回傳該站）",
            },
        },
        "required": ["city", "route"],
    }

    async def execute(self, **kwargs: Any) -> str:
        city: str = kwargs["city"]
        route: str = kwargs["route"]
        stop: str | None = kwargs.get("stop")

        try:
            token = await _get_token()
        except Exception as exc:
            logger.warning("TDX token fetch failed: %s", exc)
            return "即時資料這馬提無著（無法取得授權）"

        url = f"{_TDX_API_BASE}/Bus/EstimatedTimeOfArrival/City/{city}/{route}"
        params = {"$format": "JSON", "$top": "100"}

        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
                )
                if resp.status in (403, 429):
                    logger.warning("TDX API status=%d", resp.status)
                    return "即時資料這馬提無著（API 限流）"
                resp.raise_for_status()
                data: list[dict[str, Any]] = await resp.json()
        except TimeoutError:
            return "即時資料這馬提無著（請求逾時）"
        except Exception as exc:
            logger.warning("TDX API error: %s", exc)
            return "即時資料這馬提無著（API 錯誤）"

        if not data:
            return f"路線 {route} 目前無即時資料"

        lines: list[str] = []
        for item in data:
            stop_name = item.get("StopName", {}).get("Zh_tw", "")
            if stop and stop not in stop_name:
                continue
            eta: int | None = item.get("EstimatedArrivalTime")
            if eta is None:
                status_txt = "末班車已過"
            elif eta == 0:
                status_txt = "進站中"
            elif eta < 60:
                status_txt = f"{eta} 秒後"
            else:
                status_txt = f"約 {eta // 60} 分鐘後"
            lines.append(f"{stop_name}：{status_txt}")
            if stop:
                break  # single stop mode

        if not lines:
            target = f"站點「{stop}」" if stop else "各站"
            return f"路線 {route} {target} 無即時資料"

        return f"{route} 即時到站：\n" + "\n".join(lines)


register(TdxBusArrivalTool())
