"""Data update coordinator for the HK Bus Time Table integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, EtaEntry, HkBusEtaApiClient
from .const import CONF_DIRECTION, CONF_ROUTE, CONF_STOP_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EtaPrediction:
    """One parsed ETA prediction."""

    eta_seq: int
    eta: datetime | None
    remark_en: str
    remark_tc: str
    dest_en: str
    dest_tc: str
    data_timestamp: datetime | None


class HkBusEtaCoordinator(DataUpdateCoordinator[list[EtaPrediction]]):
    """Poll the bus ETA API for one route/stop/direction combination."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: HkBusEtaApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {config_entry.data[CONF_ROUTE]}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> list[EtaPrediction]:
        entry = self.config_entry
        try:
            entries = await self.client.async_get_eta(
                stop_id=entry.data[CONF_STOP_ID],
                route=entry.data[CONF_ROUTE],
                direction=entry.data[CONF_DIRECTION],
            )
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with the bus ETA API: {err}") from err
        return [self._to_prediction(item) for item in entries]

    @staticmethod
    def _to_prediction(item: EtaEntry) -> EtaPrediction:
        eta = dt_util.parse_datetime(item.eta) if item.eta else None
        timestamp = dt_util.parse_datetime(item.data_timestamp) if item.data_timestamp else None
        return EtaPrediction(
            eta_seq=item.eta_seq,
            eta=eta,
            remark_en=item.rmk_en,
            remark_tc=item.rmk_tc,
            dest_en=item.dest_en,
            dest_tc=item.dest_tc,
            data_timestamp=timestamp,
        )
