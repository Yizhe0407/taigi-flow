"""Static bus query tools backed by the local TDX-imported database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, select, text

from ..db.models import BusRoute, BusSchedule, BusStop, RouteStop
from ..db.session import async_session_factory
from . import register
from .base import BaseTool

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SearchStopsTool(BaseTool):
    name = "bus.search_stops"
    description = "模糊搜尋公車站名，回傳站點清單"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "站名關鍵字"},
            "city": {
                "type": "string",
                "description": "城市（可選），例如 YunlinCounty",
            },
            "limit": {"type": "integer", "description": "最多回傳幾站", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> str:
        query: str = kwargs["query"]
        city: str | None = kwargs.get("city")
        limit: int = int(kwargs.get("limit", 5))

        async with async_session_factory() as db:
            rows = await _search_stops(db, query, city, limit)

        if not rows:
            return f"找不到「{query}」相關站點"
        lines = [f"{r['nameZh']}（{r['city']}，{r['uid']}）" for r in rows]
        return "找到站點：\n" + "\n".join(lines)


class FindRoutesTool(BaseTool):
    name = "bus.find_routes"
    description = "查詢兩站之間的直達公車路線"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_stop": {"type": "string", "description": "出發站名或 UID"},
            "to_stop": {"type": "string", "description": "目的站名或 UID"},
        },
        "required": ["from_stop", "to_stop"],
    }

    async def execute(self, **kwargs: Any) -> str:
        from_stop: str = kwargs["from_stop"]
        to_stop: str = kwargs["to_stop"]

        async with async_session_factory() as db:
            result = await _find_routes(db, from_stop, to_stop)

        return result


class ListStopsTool(BaseTool):
    name = "bus.list_stops"
    description = "列出公車路線完整停靠站序列"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "route": {"type": "string", "description": "路線名稱，例如 Y02"},
            "direction": {
                "type": "integer",
                "description": "方向：0 去程、1 返程",
                "default": 0,
            },
        },
        "required": ["route"],
    }

    async def execute(self, **kwargs: Any) -> str:
        route: str = kwargs["route"]
        direction: int = int(kwargs.get("direction", 0))

        async with async_session_factory() as db:
            result = await _list_stops(db, route, direction)

        return result


class NextDeparturesTool(BaseTool):
    name = "bus.next_departures"
    description = "查詢今天從某站出發的接下來班次"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "stop": {"type": "string", "description": "站名"},
            "route": {"type": "string", "description": "路線名稱（可選）"},
            "weekday": {
                "type": "integer",
                "description": "星期幾（0=Mon, 6=Sun，預設今天）",
            },
            "limit": {"type": "integer", "description": "回傳幾班", "default": 3},
        },
        "required": ["stop"],
    }

    async def execute(self, **kwargs: Any) -> str:
        stop: str = kwargs["stop"]
        route: str | None = kwargs.get("route")
        weekday: int | None = kwargs.get("weekday")
        limit: int = int(kwargs.get("limit", 3))

        if weekday is None:
            weekday = datetime.now(UTC).weekday()
        bit = 1 << ((weekday + 1) % 7)

        async with async_session_factory() as db:
            result = await _next_departures(db, stop, route, bit, limit)

        return result


# ── DB query helpers ──────────────────────────────────────────────────────────


async def _search_stops(
    db: AsyncSession,
    query: str,
    city: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    stmt = select(BusStop).where(BusStop.nameZh.ilike(f"%{query}%"))
    if city:
        stmt = stmt.where(BusStop.city == city)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    stops = result.scalars().all()
    if not stops:
        # Fallback: trigram similarity (requires pg_trgm extension)
        try:
            raw = await db.execute(
                text(
                    "SELECT uid, \"nameZh\", city FROM \"BusStop\" "
                    "WHERE similarity(\"nameZh\", :q) > 0.2 "
                    + ("AND city = :city " if city else "")
                    + "ORDER BY similarity(\"nameZh\", :q) DESC LIMIT :lim"
                ),
                {"q": query, "lim": limit, **({"city": city} if city else {})},
            )
            return [{"uid": r[0], "nameZh": r[1], "city": r[2]} for r in raw]
        except Exception:
            return []
    return [{"uid": s.uid, "nameZh": s.nameZh, "city": s.city} for s in stops]


async def _find_routes(db: AsyncSession, from_q: str, to_q: str) -> str:
    from_stops = await _search_stops(db, from_q, None, 3)
    to_stops = await _search_stops(db, to_q, None, 3)

    if not from_stops:
        return f"找不到出發站「{from_q}」"
    if not to_stops:
        return f"找不到目的站「{to_q}」"

    from_uids = [s["uid"] for s in from_stops]
    to_uids = [s["uid"] for s in to_stops]

    # Find routes that serve both stops, with from before to
    stmt = (
        select(
            RouteStop.routeUid,
            RouteStop.stopUid,
            RouteStop.sequence,
        )
        .where(RouteStop.stopUid.in_(from_uids + to_uids))
        .order_by(RouteStop.routeUid, RouteStop.sequence)
    )
    rows = (await db.execute(stmt)).all()

    # Group by route
    route_stops: dict[str, dict[str, int]] = {}
    for row in rows:
        route_uid, stop_uid, seq = row
        route_stops.setdefault(route_uid, {})[stop_uid] = seq

    direct_routes: list[tuple[str, int, int]] = []
    for route_uid, stop_seqs in route_stops.items():
        from_seq = next(
            (stop_seqs[u] for u in from_uids if u in stop_seqs), None
        )
        to_seq = next(
            (stop_seqs[u] for u in to_uids if u in stop_seqs), None
        )
        if from_seq is not None and to_seq is not None and from_seq < to_seq:
            direct_routes.append((route_uid, from_seq, to_seq))

    if not direct_routes:
        return f"找不到從「{from_q}」到「{to_q}」的直達路線"

    # Load route names
    route_uids = [r[0] for r in direct_routes]
    routes = (
        await db.execute(select(BusRoute).where(BusRoute.uid.in_(route_uids)))
    ).scalars().all()
    uid_to_name = {r.uid: r.nameZh for r in routes}

    lines: list[str] = []
    for route_uid, from_seq, to_seq in direct_routes:
        name = uid_to_name.get(route_uid, route_uid)
        lines.append(f"{name}（第 {from_seq} 站 → 第 {to_seq} 站）")
    return f"從「{from_q}」到「{to_q}」直達路線：\n" + "\n".join(lines)


async def _list_stops(db: AsyncSession, route_query: str, direction: int) -> str:
    # Find route by name
    stmt = select(BusRoute).where(
        and_(BusRoute.nameZh.ilike(f"%{route_query}%"), BusRoute.direction == direction)
    )
    routes = (await db.execute(stmt)).scalars().all()
    if not routes:
        return f"找不到路線「{route_query}」（方向 {direction}）"

    route = routes[0]

    # Load stops in sequence order
    stmt2 = (
        select(RouteStop, BusStop)
        .join(BusStop, RouteStop.stopUid == BusStop.uid)
        .where(RouteStop.routeUid == route.uid)
        .order_by(RouteStop.sequence)
    )
    rows = (await db.execute(stmt2)).all()

    if not rows:
        return f"路線 {route.nameZh} 沒有站點資料"

    stop_names: list[str] = []
    for i, row in enumerate(rows):
        stop_obj = cast("BusStop", row[1])
        stop_names.append(f"{i+1}. {stop_obj.nameZh}")
    dir_label = "去程" if direction == 0 else "返程"
    header = f"{route.nameZh}（{dir_label}）共 {len(stop_names)} 站："
    return header + "\n" + "\n".join(stop_names)


async def _next_departures(
    db: AsyncSession,
    stop_query: str,
    route_query: str | None,
    service_day_bit: int,
    limit: int,
) -> str:
    from zoneinfo import ZoneInfo

    taipei_now = datetime.now(ZoneInfo("Asia/Taipei"))
    current_time = taipei_now.strftime("%H:%M")

    # Find matching stops
    stops = await _search_stops(db, stop_query, None, 3)
    if not stops:
        return f"找不到站點「{stop_query}」"
    stop_uids = [s["uid"] for s in stops]

    # Find routes serving these stops
    rs_stmt = select(RouteStop).where(RouteStop.stopUid.in_(stop_uids))
    if route_query:
        # Filter by route name
        route_stmt = select(BusRoute.uid).where(
            BusRoute.nameZh.ilike(f"%{route_query}%")
        )
        route_uids = [r[0] for r in (await db.execute(route_stmt)).all()]
        rs_stmt = rs_stmt.where(RouteStop.routeUid.in_(route_uids))

    route_stops_rows = (await db.execute(rs_stmt)).scalars().all()
    if not route_stops_rows:
        return f"找不到「{stop_query}」的路線資料"

    # For each route-stop, find today's schedules that haven't passed yet
    results: list[tuple[str, str, str]] = []  # (route_name, departure_time, trip_id)

    for rs in route_stops_rows:
        sched_stmt = select(BusSchedule, BusRoute).join(
            BusRoute, BusSchedule.routeUid == BusRoute.uid
        ).where(
            and_(
                BusSchedule.routeUid == rs.routeUid,
                (BusSchedule.serviceDays.op("&")(service_day_bit)) > 0,
            )
        )
        schedules = (await db.execute(sched_stmt)).all()

        for sched, bus_route in schedules:
            stop_times: list[dict[str, Any]] = sched.stopTimes  # type: ignore[assignment]
            for st in stop_times:
                if st.get("sequence") == rs.sequence:
                    arrival = st.get("arrivalTime", "")
                    if arrival and arrival > current_time:
                        results.append((bus_route.nameZh, arrival, sched.tripId))
                    break

    if not results:
        return f"「{stop_query}」今日接下來沒有班次"

    results.sort(key=lambda x: x[1])
    results = results[:limit]
    stop_name = stops[0]["nameZh"]
    lines = [f"{name} {t}" for name, t, _ in results]
    return f"{stop_name} 接下來 {len(lines)} 班：\n" + "\n".join(lines)


# Register all tools
register(SearchStopsTool())
register(FindRoutesTool())
register(ListStopsTool())
register(NextDeparturesTool())
