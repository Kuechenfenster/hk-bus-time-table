"""Sensor platform for the HK Bus Time Table integration.

Each config entry exposes three sensors: the next, second and third upcoming
bus. Depending on the chosen display format the state is either a timestamp
(device class ``timestamp``) or the minutes until arrival (device class
``duration``, unit ``min``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMPANY,
    CONF_DEST_EN,
    CONF_DEST_TC,
    CONF_DIRECTION,
    CONF_ORIG_EN,
    CONF_ORIG_TC,
    CONF_ROUTE,
    CONF_STOP_ID,
    CONF_STOP_NAME_EN,
    CONF_STOP_NAME_TC,
    CONF_TIME_FORMAT,
    DOMAIN,
    TIME_FORMAT_MINUTES,
    TIME_FORMAT_TIMESTAMP,
)
from .coordinator import EtaPrediction, HkBusEtaCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="next_bus", translation_key="next_bus"),
    SensorEntityDescription(key="second_bus", translation_key="second_bus"),
    SensorEntityDescription(key="third_bus", translation_key="third_bus"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the three ETA sensors for a config entry."""
    coordinator: HkBusEtaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HkBusEtaSensor(coordinator, entry, description, index)
        for index, description in enumerate(SENSOR_DESCRIPTIONS)
    )


class HkBusEtaSensor(CoordinatorEntity[HkBusEtaCoordinator], SensorEntity):
    """One ETA prediction (next / second / third bus)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HkBusEtaCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        index: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._index = index
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="data.gov.hk",
            model=f"{entry.data[CONF_COMPANY]} {entry.data[CONF_ROUTE]}",
            entry_type=DeviceEntryType.SERVICE,
        )
        if self._time_format == TIME_FORMAT_MINUTES:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_suggested_display_precision = 0
        else:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def _time_format(self) -> str:
        return self._entry.options.get(CONF_TIME_FORMAT, TIME_FORMAT_TIMESTAMP)

    @property
    def _prediction(self) -> EtaPrediction | None:
        if not self.coordinator.data or self._index >= len(self.coordinator.data):
            return None
        return self.coordinator.data[self._index]

    @property
    def native_value(self) -> datetime | int | None:
        prediction = self._prediction
        if prediction is None or prediction.eta is None:
            return None
        if self._time_format == TIME_FORMAT_MINUTES:
            minutes = (prediction.eta - dt_util.utcnow()).total_seconds() / 60
            return max(0, int(round(minutes)))
        return prediction.eta

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._entry.data
        attributes: dict[str, Any] = {
            "company": data[CONF_COMPANY],
            "route": data[CONF_ROUTE],
            "direction": data[CONF_DIRECTION],
            "stop_id": data[CONF_STOP_ID],
            "stop_name_en": data.get(CONF_STOP_NAME_EN),
            "stop_name_tc": data.get(CONF_STOP_NAME_TC),
            "origin_en": data.get(CONF_ORIG_EN),
            "origin_tc": data.get(CONF_ORIG_TC),
            "destination_en": data.get(CONF_DEST_EN),
            "destination_tc": data.get(CONF_DEST_TC),
        }
        if (prediction := self._prediction) is not None:
            attributes["eta_sequence"] = prediction.eta_seq
            attributes["scheduled_eta"] = (
                prediction.eta.isoformat() if prediction.eta else None
            )
            attributes["remark_en"] = prediction.remark_en
            attributes["remark_tc"] = prediction.remark_tc
            if prediction.dest_en:
                attributes["destination_en"] = prediction.dest_en
            if prediction.dest_tc:
                attributes["destination_tc"] = prediction.dest_tc
            if prediction.data_timestamp:
                attributes["data_timestamp"] = prediction.data_timestamp.isoformat()
        return attributes
