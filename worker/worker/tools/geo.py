"""Geo tools: geocode, route (OSRM), POI nearby (Overpass)."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from ..session.data_channel import get_client_location, publish_map_event
from . import register
from .base import BaseTool

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=8.0)
_USER_AGENT = "taigi-flow/0.1 (學術研究 - liaoyizhe75@gmail.com)"

_NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_OSRM_BASE = "https://router.project-osrm.org/route/v1"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Simple in-memory geocode cache (query → result)
_geocode_cache: dict[str, dict[str, Any]] = {}


async def _geocode(query: str) -> dict[str, Any] | None:
    if query in _geocode_cache:
        return _geocode_cache[query]

    params = {
        "q": query,
        "format": "json",
        "limit": "1",
        "accept-language": "zh-TW,zh,en",
    }
    async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}) as session:
        resp = await session.get(
            f"{_NOMINATIM_BASE}/search", params=params, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        results: list[dict[str, Any]] = await resp.json()

    if not results:
        return None

    result = {
        "lat": float(results[0]["lat"]),
        "lng": float(results[0]["lon"]),
        "display_name": results[0].get("display_name", query),
    }
    _geocode_cache[query] = result
    return result


class GetLocationTool(BaseTool):
    name = "geo.get_location"
    description = "取得使用者目前的 GPS 位置（由瀏覽器提供）並反查地名"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        loc = get_client_location()
        if not loc:
            return "目前無法取得你的位置（瀏覽器未提供 GPS）"

        lat, lng = loc["lat"], loc["lng"]
        try:
            headers = {"User-Agent": _USER_AGENT}
            async with aiohttp.ClientSession(headers=headers) as session:
                resp = await session.get(
                    f"{_NOMINATIM_BASE}/reverse",
                    params={
                        "lat": lat, "lon": lng,
                        "format": "json", "accept-language": "zh-TW,zh",
                    },
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
            address = data.get("display_name", f"{lat:.5f}, {lng:.5f}")
        except Exception:
            address = f"{lat:.5f}, {lng:.5f}"

        await publish_map_event(
            {"type": "map.focus", "lat": lat, "lng": lng, "zoom": 15}
        )
        return f"你目前在：{address}"


class GeocodeTool(BaseTool):
    name = "geo.geocode"
    description = "查詢地址或地名的經緯度座標"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "地址或地名，例如「斗六火車站」、「雲林科技大學」",
            }
        },
        "required": ["address"],
    }

    async def execute(self, **kwargs: Any) -> str:
        address: str = kwargs["address"]
        try:
            result = await _geocode(address)
        except Exception as exc:
            logger.warning("geocode error: %s", exc)
            return "地圖資料這馬提無著（地址查詢失敗）"

        if not result:
            return f"找無「{address}」的座標"

        return (
            f"{address} 座標：{result['lat']:.5f}, {result['lng']:.5f}\n"
            f"完整地址：{result['display_name']}"
        )


class RouteTool(BaseTool):
    name = "geo.route"
    description = "查詢兩地之間的駕車 / 步行 / 騎車路線距離與時間"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_place": {
                "type": "string",
                "description": "出發地名或地址",
            },
            "to_place": {
                "type": "string",
                "description": "目的地名或地址",
            },
            "mode": {
                "type": "string",
                "enum": ["driving", "walking", "cycling"],
                "description": "交通方式，預設 driving（駕車）",
            },
        },
        "required": ["from_place", "to_place"],
    }

    async def execute(self, **kwargs: Any) -> str:
        from_place: str = kwargs["from_place"]
        to_place: str = kwargs["to_place"]
        mode: str = kwargs.get("mode", "driving")

        try:
            src = await _geocode(from_place)
            dst = await _geocode(to_place)
        except Exception as exc:
            logger.warning("route geocode error: %s", exc)
            return "地圖資料這馬提無著（地址查詢失敗）"

        if not src:
            return f"找無出發地「{from_place}」"
        if not dst:
            return f"找無目的地「{to_place}」"

        url = (
            f"{_OSRM_BASE}/{mode}/"
            f"{src['lng']},{src['lat']};{dst['lng']},{dst['lat']}"
        )
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": _USER_AGENT}
            ) as session:
                resp = await session.get(
                    url,
                    params={
                        "overview": "simplified",
                        "geometries": "geojson",
                        "steps": "false",
                    },
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
        except Exception as exc:
            logger.warning("OSRM error: %s", exc)
            return "地圖資料這馬提無著（路線查詢失敗）"

        if data.get("code") != "Ok" or not data.get("routes"):
            return f"「{from_place}」到「{to_place}」查無路線"

        route = data["routes"][0]
        distance_km = route["distance"] / 1000
        duration_min = route["duration"] / 60
        mode_label = {"driving": "駕車", "walking": "步行", "cycling": "騎車"}.get(
            mode, mode
        )

        coords: list[list[float]] = (
            route.get("geometry", {}).get("coordinates", []) or []
        )
        if coords:
            await publish_map_event(
                {
                    "type": "map.route",
                    "from": {"lat": src["lat"], "lng": src["lng"]},
                    "to": {"lat": dst["lat"], "lng": dst["lng"]},
                    "coords": coords,
                    "distance_m": route["distance"],
                    "duration_s": route["duration"],
                }
            )

        return (
            f"從{from_place}到{to_place}（{mode_label}）：\n"
            f"距離約 {distance_km:.1f} 公里，時間約 {duration_min:.0f} 分鐘"
        )


class PoiNearbyTool(BaseTool):
    name = "geo.poi_nearby"
    description = "查詢附近的地點（餐廳、小吃、便利商店等 POI）"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜尋關鍵字，例如「小吃」、「便利商店」、「加油站」",
            },
            "location": {
                "type": "string",
                "description": "搜尋中心地名（可選，預設用 Session 目前位置）",
            },
            "radius_m": {
                "type": "integer",
                "description": "搜尋半徑（公尺），預設 1000",
            },
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> str:
        query: str = kwargs["query"]
        location_str: str | None = kwargs.get("location")
        radius_m: int = max(1, min(int(kwargs.get("radius_m", 1000)), 5000))

        center: dict[str, Any] | None = None
        if location_str:
            try:
                center = await _geocode(location_str)
            except Exception as exc:
                logger.warning("poi geocode error: %s", exc)

        if not center:
            stored = get_client_location()
            if stored:
                center = {
                    "lat": stored["lat"], "lng": stored["lng"],
                    "display_name": "目前位置",
                }
            else:
                return f"需要提供位置才能查詢附近的{query}"

        lat, lng = center["lat"], center["lng"]

        # Escape chars that could break the Overpass QL regex literal
        safe_query = re.sub(r'["\\]', lambda m: "\\" + m.group(), query)
        overpass_query = (
            f"[out:json][timeout:5];"
            f"("
            f'node[~"name|amenity|shop"~"{safe_query}",i]'
            f"(around:{radius_m},{lat},{lng});"
            f'way[~"name|amenity|shop"~"{safe_query}",i]'
            f"(around:{radius_m},{lat},{lng});"
            f");"
            f"out center 10;"
        )

        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": _USER_AGENT}
            ) as session:
                resp = await session.post(
                    _OVERPASS_URL,
                    data={"data": overpass_query},
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data: dict[str, Any] = await resp.json()
        except Exception as exc:
            logger.warning("Overpass error: %s", exc)
            return "地圖資料這馬提無著（POI 查詢失敗）"

        elements: list[dict[str, Any]] = data.get("elements", [])
        if not elements:
            return f"附近 {radius_m} 公尺內找無「{query}」"

        items: list[str] = []
        poi_list: list[dict[str, Any]] = []
        for el in elements[:5]:
            name = el.get("tags", {}).get("name", "（無名稱）")
            el_lat = el.get("lat") or el.get("center", {}).get("lat", lat)
            el_lng = el.get("lon") or el.get("center", {}).get("lon", lng)
            dist_m = _approx_dist_m(lat, lng, el_lat, el_lng)
            items.append(f"- {name}（約 {dist_m:.0f} 公尺）")
            poi_list.append({"name": name, "lat": el_lat, "lng": el_lng})

        if poi_list:
            await publish_map_event(
                {
                    "type": "map.poi",
                    "center": {"lat": lat, "lng": lng},
                    "items": poi_list,
                }
            )

        header = f"附近的{query}（{radius_m}m 內，共 {len(elements)} 筆，顯示前 5）："
        return header + "\n" + "\n".join(items)


def _approx_dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Rough equirectangular distance in metres."""
    import math

    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat**2 + dlng**2) * 6_371_000


register(GetLocationTool())
register(GeocodeTool())
register(RouteTool())
register(PoiNearbyTool())
