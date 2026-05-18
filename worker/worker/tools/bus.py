"""Static bus query tools backed by the local TDX-imported database."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, select, text

from ..db.models import BusRoute, BusSchedule, BusStop, RouteStop
from ..db.session import async_session_factory
from ..session.data_channel import publish_map_event
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
    description = "查詢兩站之間的直達或一次轉乘公車路線"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "from_stop": {"type": "string", "description": "出發站名"},
            "to_stop": {"type": "string", "description": "目的站名"},
            "max_transfers": {
                "type": "integer",
                "description": "最多轉乘次數：0 只找直達，1 允許一次轉乘（預設 1）",
                "default": 1,
            },
        },
        "required": ["from_stop", "to_stop"],
    }

    async def execute(self, **kwargs: Any) -> str:
        from_stop: str = kwargs["from_stop"]
        to_stop: str = kwargs["to_stop"]
        max_transfers: int = int(kwargs.get("max_transfers", 1))

        async with async_session_factory() as db:
            result = await _find_routes(db, from_stop, to_stop, max_transfers)

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
            text_result, stops_data = await _list_stops(db, route, direction)

        if stops_data:
            await publish_map_event(
                {"type": "bus.route_stops", "route": route, "stops": stops_data}
            )
        return text_result


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


async def _find_routes(
    db: AsyncSession, from_q: str, to_q: str, max_transfers: int = 1
) -> str:
    from_stops = await _search_stops(db, from_q, None, 3)
    to_stops = await _search_stops(db, to_q, None, 3)

    if not from_stops:
        return f"找不到出發站「{from_q}」"
    if not to_stops:
        return f"找不到目的站「{to_q}」"

    from_uids = [s["uid"] for s in from_stops]
    to_uids = [s["uid"] for s in to_stops]
    from_name = from_stops[0]["nameZh"]
    to_name = to_stops[0]["nameZh"]

    # ── 直達查詢 ──────────────────────────────────────────────────────────────
    stmt = (
        select(RouteStop.routeUid, RouteStop.stopUid, RouteStop.sequence)
        .where(RouteStop.stopUid.in_(from_uids + to_uids))
        .order_by(RouteStop.routeUid, RouteStop.sequence)
    )
    rows = (await db.execute(stmt)).all()

    route_stops: dict[str, dict[str, int]] = {}
    for route_uid, stop_uid, seq in rows:
        route_stops.setdefault(route_uid, {})[stop_uid] = seq

    direct: list[tuple[str, int, int]] = []
    for route_uid, stop_seqs in route_stops.items():
        from_seq = next((stop_seqs[u] for u in from_uids if u in stop_seqs), None)
        to_seq = next((stop_seqs[u] for u in to_uids if u in stop_seqs), None)
        if from_seq is not None and to_seq is not None and from_seq < to_seq:
            direct.append((route_uid, from_seq, to_seq))

    sections: list[str] = []

    if direct:
        all_uids = [r[0] for r in direct]
        uid_to_name = {
            r.uid: r.nameZh
            for r in (
                await db.execute(select(BusRoute).where(BusRoute.uid.in_(all_uids)))
            ).scalars().all()
        }
        direct_lines: list[str] = []
        for route_uid, from_seq, to_seq in direct[:5]:
            name = uid_to_name.get(route_uid, route_uid)
            direct_lines.append(
                f"  • {name}（第 {from_seq} 站上車，第 {to_seq} 站下車）"
            )
        sections.append("【直達】\n" + "\n".join(direct_lines))

    # ── 轉乘查詢 ─────────────────────────────────────────────────────────────
    if max_transfers >= 1:
        transfers = await _find_transfer_routes(db, from_uids, to_uids, limit=3)
        if transfers:
            # Load all route & stop names needed
            all_route_uids = list(
                {t["leg1_route"] for t in transfers}
                | {t["leg2_route"] for t in transfers}
            )
            all_stop_uids = list({t["transfer_uid"] for t in transfers})
            uid_to_name2 = {
                r.uid: r.nameZh
                for r in (
                    await db.execute(
                        select(BusRoute).where(BusRoute.uid.in_(all_route_uids))
                    )
                ).scalars().all()
            }
            uid_to_stop_name = {
                s.uid: s.nameZh
                for s in (
                    await db.execute(
                        select(BusStop).where(BusStop.uid.in_(all_stop_uids))
                    )
                ).scalars().all()
            }
            transfer_lines: list[str] = []
            for t in transfers:
                r1 = uid_to_name2.get(t["leg1_route"], t["leg1_route"])
                r2 = uid_to_name2.get(t["leg2_route"], t["leg2_route"])
                xfer = uid_to_stop_name.get(t["transfer_uid"], t["transfer_uid"])
                transfer_lines.append(f"  • 搭 {r1} 至「{xfer}」，轉 {r2}")
            sections.append("【轉乘（一次）】\n" + "\n".join(transfer_lines))

    if not sections:
        suffix = "（含一次轉乘）" if max_transfers >= 1 else "（僅直達）"
        return f"找不到從「{from_name}」到「{to_name}」的路線{suffix}"

    header = f"從「{from_name}」到「{to_name}」："
    return header + "\n\n" + "\n\n".join(sections)


async def _find_transfer_routes(
    db: AsyncSession,
    from_uids: list[str],
    to_uids: list[str],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Find routes requiring exactly one transfer via two SQL self-joins."""
    if not from_uids or not to_uids:
        return []

    # Step 1: stops reachable downstream from from_uids (via any route)
    reachable_rows = (await db.execute(
        text("""
            SELECT DISTINCT
                rs1."routeUid"  AS leg1_route,
                rs2."stopUid"   AS transfer_uid,
                rs1.sequence    AS from_seq,
                rs2.sequence    AS transfer_seq
            FROM "RouteStop" rs1
            JOIN "RouteStop" rs2
                ON rs1."routeUid" = rs2."routeUid"
               AND rs2.sequence   > rs1.sequence
            WHERE rs1."stopUid" = ANY(:from_uids)
            LIMIT 400
        """),
        {"from_uids": from_uids},
    )).all()

    if not reachable_rows:
        return []

    transfer_uids = list({r[1] for r in reachable_rows})
    leg1_routes = list({r[0] for r in reachable_rows})

    # Step 2: from transfer stops, find routes that reach to_stop
    #         (must be a different route than leg1)
    to_reach_rows = (await db.execute(
        text("""
            SELECT DISTINCT
                rs3."stopUid"   AS transfer_uid,
                rs3."routeUid"  AS leg2_route,
                rs3.sequence    AS board_seq
            FROM "RouteStop" rs3
            JOIN "RouteStop" rs4
                ON rs3."routeUid" = rs4."routeUid"
               AND rs4.sequence   > rs3.sequence
               AND rs4."stopUid"  = ANY(:to_uids)
            WHERE rs3."stopUid"  = ANY(:transfer_uids)
              AND rs3."routeUid" != ALL(:leg1_routes)
            LIMIT 200
        """),
        {
            "to_uids": to_uids,
            "transfer_uids": transfer_uids,
            "leg1_routes": leg1_routes,
        },
    )).all()

    if not to_reach_rows:
        return []

    # Index step-1 by transfer_uid
    reachable_by_transfer: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for leg1_route, transfer_uid, from_seq, transfer_seq in reachable_rows:
        reachable_by_transfer[transfer_uid].append((leg1_route, from_seq, transfer_seq))

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for transfer_uid, leg2_route, board_seq in to_reach_rows:
        for leg1_route, from_seq, transfer_seq in reachable_by_transfer.get(
            transfer_uid, []
        ):
            if leg1_route == leg2_route:
                continue
            key = (leg1_route, transfer_uid, leg2_route)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "leg1_route": leg1_route,
                "leg2_route": leg2_route,
                "transfer_uid": transfer_uid,
                "from_seq": from_seq,
                "transfer_seq": transfer_seq,
                "board_seq": board_seq,
            })
            if len(results) >= limit:
                return results

    return results


async def _list_stops(
    db: AsyncSession, route_query: str, direction: int
) -> tuple[str, list[dict[str, Any]]]:
    # Find route by name
    stmt = select(BusRoute).where(
        and_(BusRoute.nameZh.ilike(f"%{route_query}%"), BusRoute.direction == direction)
    )
    routes = (await db.execute(stmt)).scalars().all()
    if not routes:
        return f"找不到路線「{route_query}」（方向 {direction}）", []

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
        return f"路線 {route.nameZh} 沒有站點資料", []

    stop_names: list[str] = []
    stops_data: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        stop_obj = cast("BusStop", row[1])
        rs = cast("RouteStop", row[0])
        stop_names.append(f"{i+1}. {stop_obj.nameZh}")
        stops_data.append(
            {
                "name": stop_obj.nameZh,
                "lat": stop_obj.lat,
                "lng": stop_obj.lng,
                "sequence": rs.sequence,
            }
        )
    dir_label = "去程" if direction == 0 else "返程"
    header = f"{route.nameZh}（{dir_label}）共 {len(stop_names)} 站："
    return header + "\n" + "\n".join(stop_names), stops_data


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
