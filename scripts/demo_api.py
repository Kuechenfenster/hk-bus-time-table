#!/usr/bin/env python3
"""Standalone smoke test for the HK Bus Time Table API layer.

Loads custom_components/hk_bus_timetable/api.py directly (no Home Assistant needed)
and exercises the exact call sequence the config flow and coordinator run:

    route info -> route stops -> stop names -> ETA

Usage:
    python3 scripts/demo_api.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
API_PATH = REPO_ROOT / "custom_components" / "hk_bus_timetable" / "api.py"

spec = importlib.util.spec_from_file_location("hk_bus_timetable_api", API_PATH)
assert spec and spec.loader
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)

import aiohttp  # noqa: E402

CASES = [
    # company, route, direction, stop index on the route
    ("KMB", "1A", "outbound", 5),
    ("CTB", "788", "outbound", 0),
]


async def run_case(session: aiohttp.ClientSession, company: str, route: str, direction: str, stop_index: int) -> None:
    client = api.HkBusEtaApiClient(session, company)
    print(f"\n=== {company} route {route} ({direction}) ===")

    info = await client.async_get_route_info(route, direction)
    print(f"route: {info.orig_en} -> {info.dest_en}")

    stops = await client.async_get_route_stops_with_names(route, direction)
    print(f"stops: {len(stops)}")
    for route_stop, stop_info in stops[:3]:
        name = stop_info.name_en if stop_info else "(name lookup failed)"
        print(f"  {route_stop.seq}. {name} [{route_stop.stop_id}]")

    route_stop, stop_info = stops[min(stop_index, len(stops) - 1)]
    stop_name = stop_info.name_en if stop_info else "unknown"
    print(f"ETAs at stop {route_stop.seq}. {stop_name} ({route_stop.stop_id}):")

    etas = await client.async_get_eta(route_stop.stop_id, route, direction)
    now = datetime.now(timezone.utc)
    for entry in etas[:3]:
        if entry.eta:
            eta = datetime.fromisoformat(entry.eta)
            minutes = (eta - now).total_seconds() / 60
            remark = f" ({entry.rmk_en})" if entry.rmk_en else ""
            print(f"  seq {entry.eta_seq}: {eta.strftime('%H:%M')} [{max(0, minutes):.0f} min]{remark}")
        else:
            print(f"  seq {entry.eta_seq}: no prediction{(' - ' + entry.rmk_en) if entry.rmk_en else ''}")


async def main() -> None:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for company, route, direction, stop_index in CASES:
            try:
                await run_case(session, company, route, direction, stop_index)
            except api.ApiError as err:
                print(f"FAILED: {err}")


if __name__ == "__main__":
    asyncio.run(main())
