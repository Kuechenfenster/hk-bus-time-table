"""Async client for the Hong Kong bus ETA APIs published via data.gov.hk.

Supported operators:
- KMB / LWB  via https://data.etabus.gov.hk  ("KMB")
- Citybus    via https://rt.data.gov.hk      ("CTB", includes former NWFB routes)

Reference: https://data.gov.hk/en-datasets/category/transport

This module is intentionally free of Home Assistant imports so it can be
smoke-tested standalone (see scripts/demo_api.py).
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Any

import aiohttp

KMB_BASE_URL = "https://data.etabus.gov.hk/v1/transport/kmb"
CTB_BASE_URL = "https://rt.data.gov.hk/v2/transport/citybus"

COMPANY_KMB = "KMB"
COMPANY_CTB = "CTB"

SUPPORTED_COMPANIES: dict[str, str] = {
    COMPANY_KMB: KMB_BASE_URL,
    COMPANY_CTB: CTB_BASE_URL,
}

DIRECTION_OUTBOUND = "outbound"
DIRECTION_INBOUND = "inbound"
DIRECTION_TO_BOUND = {DIRECTION_OUTBOUND: "O", DIRECTION_INBOUND: "I"}

KMB_SERVICE_TYPE = "1"  # the KMB API requires a service type; special departures (2+) are not handled
DEFAULT_TIMEOUT = 10


class ApiError(Exception):
    """Network or protocol error talking to the ETA service."""


class DataNotFoundError(ApiError):
    """The API answered 422 - the requested object does not exist."""


class RouteNotFoundError(ApiError):
    """The requested route / direction combination does not exist."""


class StopNotFoundError(ApiError):
    """The requested stop does not exist."""


@dataclass(frozen=True)
class RouteInfo:
    """Origin/destination of a route direction."""

    orig_en: str
    orig_tc: str
    dest_en: str
    dest_tc: str


@dataclass(frozen=True)
class RouteStop:
    """One stop on a route direction."""

    seq: int
    stop_id: str


@dataclass(frozen=True)
class StopInfo:
    """A physical bus stop."""

    stop_id: str
    name_en: str
    name_tc: str


@dataclass(frozen=True)
class EtaEntry:
    """One ETA prediction row as returned by the API."""

    eta_seq: int
    eta: str | None
    rmk_en: str
    rmk_tc: str
    dest_en: str
    dest_tc: str
    data_timestamp: str | None


class HkBusEtaApiClient:
    """Thin async wrapper around the KMB/LWB and Citybus ETA endpoints."""

    def __init__(self, session: aiohttp.ClientSession, company: str) -> None:
        try:
            self._base_url = SUPPORTED_COMPANIES[company]
        except KeyError as err:
            raise ValueError(f"Unsupported bus company: {company}") from err
        self.company = company
        self._session = session

    async def _get_data(self, path: str) -> Any:
        """GET a path and return the `data` component of the API envelope."""
        url = f"{self._base_url}/{path}"
        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.get(url) as response:
                    body = await response.json(content_type=None)
                    status = response.status
        except (aiohttp.ClientError, asyncio.TimeoutError, socket.gaierror, ValueError) as err:
            # ValueError also covers malformed JSON payloads (JSONDecodeError)
            raise ApiError(f"Request to {url} failed: {err}") from err
        if status == 422 or (isinstance(body, dict) and str(body.get("code")) == "422"):
            raise DataNotFoundError(f"{url} returned 422 (not found)")
        if status != 200 or not isinstance(body, dict) or "data" not in body:
            raise ApiError(f"{url}: unexpected response (HTTP {status})")
        return body["data"]

    async def async_get_route_info(self, route: str, direction: str) -> RouteInfo:
        """Fetch origin/destination labels for a route direction."""
        if self.company == COMPANY_CTB:
            # Citybus has one endpoint for the whole route; direction is
            # validated separately via async_get_route_stops().
            path = f"route/{self.company}/{route}"
        else:
            path = f"route/{route}/{direction}/{KMB_SERVICE_TYPE}"
        try:
            data = await self._get_data(path)
        except DataNotFoundError as err:
            raise RouteNotFoundError(
                f"Route {route} ({direction}) not found for {self.company}"
            ) from err
        if not isinstance(data, dict) or not data.get("orig_en"):
            raise RouteNotFoundError(
                f"Route {route} ({direction}) not found for {self.company}"
            )
        return RouteInfo(
            orig_en=data["orig_en"],
            orig_tc=data.get("orig_tc", ""),
            dest_en=data["dest_en"],
            dest_tc=data.get("dest_tc", ""),
        )

    async def async_get_route_stops(self, route: str, direction: str) -> list[RouteStop]:
        """Fetch the ordered list of stops for a route direction."""
        if self.company == COMPANY_CTB:
            path = f"route-stop/{self.company}/{route}/{direction}"
        else:
            path = f"route-stop/{route}/{direction}/{KMB_SERVICE_TYPE}"
        try:
            data = await self._get_data(path)
        except DataNotFoundError as err:
            raise RouteNotFoundError(
                f"Route {route} ({direction}) not found for {self.company}"
            ) from err
        if not isinstance(data, list) or not data:
            raise RouteNotFoundError(
                f"Route {route} ({direction}) has no stops for {self.company}"
            )
        stops = [
            RouteStop(seq=int(item["seq"]), stop_id=str(item["stop"]))
            for item in data
            if item.get("stop") is not None and item.get("seq") is not None
        ]
        if not stops:
            raise RouteNotFoundError(
                f"Route {route} ({direction}) has no stops for {self.company}"
            )
        stops.sort(key=lambda stop: stop.seq)
        return stops

    async def async_get_stop(self, stop_id: str) -> StopInfo:
        """Fetch the name of one stop."""
        try:
            data = await self._get_data(f"stop/{stop_id}")
        except DataNotFoundError as err:
            raise StopNotFoundError(f"Stop {stop_id} not found for {self.company}") from err
        if not isinstance(data, dict) or not data.get("name_en"):
            raise StopNotFoundError(f"Stop {stop_id} not found for {self.company}")
        return StopInfo(
            stop_id=str(data.get("stop", stop_id)),
            name_en=data["name_en"],
            name_tc=data.get("name_tc", ""),
        )

    async def async_get_route_stops_with_names(
        self, route: str, direction: str, max_concurrency: int = 5
    ) -> list[tuple[RouteStop, StopInfo | None]]:
        """Fetch the route's stops and resolve each stop's name.

        Stops whose name lookup fails are returned with ``StopInfo`` = None so
        one bad stop cannot break the whole route.
        """
        route_stops = await self.async_get_route_stops(route, direction)
        semaphore = asyncio.Semaphore(max_concurrency)

        async def resolve(route_stop: RouteStop) -> tuple[RouteStop, StopInfo | None]:
            async with semaphore:
                try:
                    return route_stop, await self.async_get_stop(route_stop.stop_id)
                except ApiError:
                    return route_stop, None

        return list(await asyncio.gather(*(resolve(rs) for rs in route_stops)))

    async def async_get_eta(self, stop_id: str, route: str, direction: str) -> list[EtaEntry]:
        """Fetch upcoming ETAs for one route at one stop, ordered by eta_seq.

        Both APIs return predictions for every direction serving the stop, so
        results are filtered to the configured direction. If the filter would
        remove everything (seen on some one-way/circular routes), the
        unfiltered list is returned instead.
        """
        if self.company == COMPANY_CTB:
            path = f"eta/{self.company}/{stop_id}/{route}"
        else:
            path = f"eta/{stop_id}/{route}/{KMB_SERVICE_TYPE}"
        data = await self._get_data(path)
        if not isinstance(data, list):
            raise ApiError(f"Unexpected ETA payload for stop {stop_id}")

        bound = DIRECTION_TO_BOUND[direction]
        filtered = [item for item in data if str(item.get("dir", "")).upper() == bound]
        relevant = filtered if filtered else data

        entries: list[EtaEntry] = []
        for position, item in enumerate(relevant):
            try:
                seq = int(item.get("eta_seq", position + 1))
            except (TypeError, ValueError):
                seq = position + 1
            entries.append(
                EtaEntry(
                    eta_seq=seq,
                    eta=item.get("eta") or None,
                    rmk_en=item.get("rmk_en") or "",
                    rmk_tc=item.get("rmk_tc") or "",
                    dest_en=item.get("dest_en") or "",
                    dest_tc=item.get("dest_tc") or "",
                    data_timestamp=item.get("data_timestamp") or None,
                )
            )
        entries.sort(key=lambda entry: entry.eta_seq)
        return entries
