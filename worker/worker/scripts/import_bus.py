"""Import TDX bus JSON data into the database.

Usage:
    uv run python -m worker.scripts.import_bus --dir <path> [--clean]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import ijson  # type: ignore[import-untyped]
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.models import BusOperator, BusRoute, BusSchedule, BusStop, RouteStop
from ..db.session import async_session_factory

logger = logging.getLogger(__name__)

_BATCH = 500  # rows per INSERT


# TDX ServiceDay keys in bitmask order (Sun=bit0=1, Mon=bit1=2, ..., Sat=bit6=64)
_SERVICE_DAY_KEYS = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]


def _service_day_bitmask(service_day: dict[str, int]) -> int:
    return sum(service_day.get(d, 0) << i for i, d in enumerate(_SERVICE_DAY_KEYS))


def _or_none(v: str) -> str | None:
    return v if v else None


async def _truncate_bus_tables(db: Any) -> None:
    """Delete all bus data in FK-safe order."""
    await db.execute(delete(BusSchedule))
    await db.execute(delete(RouteStop))
    await db.execute(delete(BusRoute))
    await db.execute(delete(BusStop))
    await db.execute(delete(BusOperator))
    await db.commit()
    logger.info("Truncated all bus tables")


async def _import_routes(data_dir: Path, db: Any) -> None:
    routes_raw: list[dict[str, Any]] = json.loads(
        (data_dir / "route.json").read_text(encoding="utf-8")
    )
    op_rows: list[dict[str, Any]] = []
    route_rows: list[dict[str, Any]] = []

    seen_ops: set[str] = set()

    for entry in routes_raw:
        operators: list[dict[str, Any]] = entry.get("Operators", [])
        # Take the first operator as the primary one
        primary_op = operators[0] if operators else None

        resolved_op_id: str = ""
        if primary_op:
            resolved_op_id = str(primary_op["OperatorID"])
            if resolved_op_id not in seen_ops:
                seen_ops.add(resolved_op_id)
                op_name: dict[str, str] = primary_op.get("OperatorName", {})
                op_rows.append(
                    {
                        "id": resolved_op_id,
                        "code": primary_op.get("OperatorCode", ""),
                        "nameZh": op_name.get("Zh_tw", ""),
                        "nameEn": op_name.get("En", ""),
                    }
                )

        for sub in entry.get("SubRoutes", []):
            sub_name: dict[str, str] = sub.get("SubRouteName", {})
            headsign = _or_none(sub.get("Headsign", ""))
            route_rows.append(
                {
                    "uid": sub["SubRouteUID"],
                    "routeId": sub["SubRouteID"],
                    "nameZh": sub_name.get("Zh_tw", ""),
                    "nameEn": sub_name.get("En", ""),
                    "headsign": headsign,
                    "direction": sub.get("Direction", 0),
                    "city": entry.get("City", ""),
                    "operatorId": resolved_op_id,
                }
            )

    if op_rows:
        stmt = pg_insert(BusOperator).values(op_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "code": stmt.excluded.code,
                "nameZh": stmt.excluded.nameZh,
                "nameEn": stmt.excluded.nameEn,
            },
        )
        await db.execute(stmt)

    if route_rows:
        stmt2 = pg_insert(BusRoute).values(route_rows)
        stmt2 = stmt2.on_conflict_do_update(
            index_elements=["uid"],
            set_={
                "routeId": stmt2.excluded.routeId,
                "nameZh": stmt2.excluded.nameZh,
                "nameEn": stmt2.excluded.nameEn,
                "headsign": stmt2.excluded.headsign,
                "direction": stmt2.excluded.direction,
                "city": stmt2.excluded.city,
                "operatorId": stmt2.excluded.operatorId,
            },
        )
        await db.execute(stmt2)

    await db.commit()
    logger.info("Imported %d operators, %d routes", len(op_rows), len(route_rows))


async def _upsert_stops_batch(rows: list[dict[str, Any]], db: Any) -> None:
    stmt = pg_insert(BusStop).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["uid"],
        set_={
            "stopId": stmt.excluded.stopId,
            "nameZh": stmt.excluded.nameZh,
            "nameEn": stmt.excluded.nameEn,
            "lat": stmt.excluded.lat,
            "lng": stmt.excluded.lng,
            "address": stmt.excluded.address,
            "city": stmt.excluded.city,
        },
    )
    await db.execute(stmt)


async def _import_stops(data_dir: Path, db: Any) -> None:
    stops_raw: list[dict[str, Any]] = json.loads(
        (data_dir / "stop.json").read_text(encoding="utf-8")
    )
    batch: list[dict[str, Any]] = []
    total = 0
    for s in stops_raw:
        pos = s.get("StopPosition", {})
        name: dict[str, str] = s.get("StopName", {})
        batch.append(
            {
                "uid": s["StopUID"],
                "stopId": s["StopID"],
                "nameZh": name.get("Zh_tw", ""),
                "nameEn": name.get("En", ""),
                "lat": pos.get("PositionLat", 0.0),
                "lng": pos.get("PositionLon", 0.0),
                "address": _or_none(s.get("StopAddress", "")),
                "city": s.get("City", ""),
            }
        )
        if len(batch) >= _BATCH:
            await _upsert_stops_batch(batch, db)
            total += len(batch)
            batch = []

    if batch:
        await _upsert_stops_batch(batch, db)
        total += len(batch)

    await db.commit()
    logger.info("Imported %d stops", total)


async def _import_stop_of_route(data_dir: Path, db: Any) -> None:
    data: list[dict[str, Any]] = json.loads(
        (data_dir / "stop_of_route.json").read_text(encoding="utf-8")
    )

    # Delete existing RouteStops in bulk batches (avoid N individual DELETEs)
    route_uids = list({entry["SubRouteUID"] for entry in data})
    for i in range(0, len(route_uids), _BATCH):
        chunk = route_uids[i : i + _BATCH]
        await db.execute(delete(RouteStop).where(RouteStop.routeUid.in_(chunk)))

    batch: list[dict[str, Any]] = []
    total = 0
    for entry in data:
        route_uid = entry["SubRouteUID"]
        for stop in entry.get("Stops", []):
            boarding_val = stop.get("StopBoarding", 1)
            batch.append(
                {
                    "routeUid": route_uid,
                    "stopUid": stop["StopUID"],
                    "sequence": stop["StopSequence"],
                    "boarding": boarding_val >= 0,
                }
            )
            if len(batch) >= _BATCH:
                stmt = pg_insert(RouteStop).values(batch)
                await db.execute(stmt.on_conflict_do_nothing())
                total += len(batch)
                batch = []

    if batch:
        stmt = pg_insert(RouteStop).values(batch)
        await db.execute(stmt.on_conflict_do_nothing())
        total += len(batch)

    await db.commit()
    logger.info("Imported %d route-stop associations", total)


async def _import_schedules(data_dir: Path, db: Any) -> None:
    # Delete and re-insert in a single transaction so a mid-run failure never
    # leaves the table empty. Intermediate commits are skipped intentionally.
    await db.execute(delete(BusSchedule))

    schedule_path = data_dir / "schedule.json"
    batch: list[dict[str, Any]] = []
    total = 0

    with open(schedule_path, "rb") as f:
        for entry in ijson.items(f, "item"):
            route_uid: str = entry.get("SubRouteUID", "")
            for tt in entry.get("Timetables", []):
                service_day: dict[str, int] = tt.get("ServiceDay", {})
                stop_times = [
                    {
                        "stopUid": st["StopUID"],
                        "sequence": st["StopSequence"],
                        "arrivalTime": st.get("ArrivalTime", ""),
                    }
                    for st in tt.get("StopTimes", [])
                ]
                batch.append(
                    {
                        "id": str(uuid.uuid4()),
                        "routeUid": route_uid,
                        "tripId": str(tt.get("TripID", "")),
                        "serviceDays": _service_day_bitmask(service_day),
                        "isLowFloor": bool(tt.get("IsLowFloor", False)),
                        "stopTimes": stop_times,
                    }
                )
                if len(batch) >= _BATCH:
                    await db.execute(pg_insert(BusSchedule).values(batch))
                    total += len(batch)
                    logger.info("  schedules buffered: %d", total)
                    batch = []

    if batch:
        await db.execute(pg_insert(BusSchedule).values(batch))
        total += len(batch)

    await db.commit()
    logger.info("Imported %d schedule timetables", total)


async def run(data_dir: Path, clean: bool) -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Importing bus data from %s (clean=%s)", data_dir, clean)

    async with async_session_factory() as db:
        if clean:
            await _truncate_bus_tables(db)

        await _import_routes(data_dir, db)
        await _import_stops(data_dir, db)
        await _import_stop_of_route(data_dir, db)
        await _import_schedules(data_dir, db)

    logger.info("Import complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import TDX bus data into DB")
    parser.add_argument(
        "--dir", required=True, help="Directory containing TDX JSON files"
    )
    parser.add_argument(
        "--clean", action="store_true", help="Truncate tables before import"
    )
    args = parser.parse_args()
    asyncio.run(run(Path(args.dir), args.clean))


if __name__ == "__main__":
    main()
