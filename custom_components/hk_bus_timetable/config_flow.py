"""Config flow for the HK Bus Time Table integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ApiError,
    HkBusEtaApiClient,
    RouteInfo,
    RouteNotFoundError,
    RouteStop,
    StopInfo,
    StopNotFoundError,
)
from .const import (
    CONF_COMPANY,
    CONF_DEST_EN,
    CONF_DEST_TC,
    CONF_DIRECTION,
    CONF_ORIG_EN,
    CONF_ORIG_TC,
    CONF_ROUTE,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME_EN,
    CONF_STOP_NAME_TC,
    CONF_TIME_FORMAT,
    DEFAULT_SCAN_INTERVAL,
    DIRECTION_INBOUND,
    DIRECTION_OUTBOUND,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    TIME_FORMAT_TIMESTAMP,
    TIME_FORMATS,
)

_LOGGER = logging.getLogger(__name__)


class HkBusEtaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HK Bus ETA."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: HkBusEtaApiClient | None = None
        self._company: str | None = None
        self._route: str | None = None
        self._route_infos: dict[str, RouteInfo] = {}
        self._direction: str | None = None
        self._stops_cache: list[tuple[RouteStop, StopInfo | None]] | None = None
        self._stop_id: str | None = None
        self._stop_name_en: str | None = None
        self._stop_name_tc: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: pick the bus company."""
        if user_input is not None:
            self._company = user_input[CONF_COMPANY]
            self._client = HkBusEtaApiClient(
                async_get_clientsession(self.hass), self._company
            )
            return await self.async_step_route()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COMPANY): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value="KMB", label="KMB / LWB (九巴 / 龍運)"
                                ),
                                selector.SelectOptionDict(
                                    value="CTB", label="Citybus / NWFB (城巴 / 新巴)"
                                ),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_route(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: enter the route number and validate it against the API."""
        assert self._client is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            route = user_input[CONF_ROUTE].strip().upper()
            infos: dict[str, RouteInfo] = {}
            for direction in (DIRECTION_OUTBOUND, DIRECTION_INBOUND):
                try:
                    route_info = await self._client.async_get_route_info(route, direction)
                    # Citybus returns the same route info for both directions,
                    # so confirm the direction really has stops.
                    await self._client.async_get_route_stops(route, direction)
                except RouteNotFoundError:
                    continue
                except ApiError:
                    errors["base"] = "cannot_connect"
                    break
                infos[direction] = route_info

            if not errors and not infos:
                errors[CONF_ROUTE] = "route_not_found"
            if not errors:
                self._route = route
                self._route_infos = infos
                return await self.async_step_direction()

        return self.async_show_form(
            step_id="route",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ROUTE): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: pick the direction of travel."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._direction = user_input[CONF_DIRECTION]
            return await self.async_step_stop()

        options = [
            selector.SelectOptionDict(
                value=direction,
                label=f"{info.orig_en} → {info.dest_en}",
            )
            for direction, info in self._route_infos.items()
        ]
        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DIRECTION): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _async_route_stops(self) -> list[tuple[RouteStop, StopInfo | None]]:
        """Fetch (and cache) the stops for the chosen route and direction."""
        assert self._client is not None
        assert self._route is not None
        assert self._direction is not None
        if self._stops_cache is None:
            self._stops_cache = await self._client.async_get_route_stops_with_names(
                self._route, self._direction
            )
        return self._stops_cache

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: pick a stop from the route's stop list, or type a stop ID."""
        assert self._client is not None
        errors: dict[str, str] = {}

        try:
            stops = await self._async_route_stops()
        except ApiError as err:
            _LOGGER.error("Failed to load route stops: %s", err)
            return self.async_abort(reason="cannot_connect")

        known: dict[str, StopInfo | None] = {
            route_stop.stop_id: stop_info for route_stop, stop_info in stops
        }

        if user_input is not None:
            stop_id = str(user_input[CONF_STOP_ID]).strip()
            match = next(
                (stop for stop in known if stop.upper() == stop_id.upper()), None
            )
            if match is not None:
                stop_info = known[match]
                self._stop_id = match
                self._stop_name_en = stop_info.name_en if stop_info else match
                self._stop_name_tc = stop_info.name_tc if stop_info else ""
            else:
                # The user typed a stop ID manually - validate it directly.
                try:
                    stop_info = await self._client.async_get_stop(stop_id)
                except StopNotFoundError:
                    errors[CONF_STOP_ID] = "stop_not_found"
                except ApiError:
                    errors["base"] = "cannot_connect"
                else:
                    self._stop_id = stop_info.stop_id
                    self._stop_name_en = stop_info.name_en
                    self._stop_name_tc = stop_info.name_tc

            if not errors:
                await self.async_set_unique_id(
                    f"{self._company}-{self._route}-{self._direction}-{self._stop_id}"
                )
                self._abort_if_unique_id_configured()
                return await self.async_step_time_format()

        options: list[selector.SelectOptionDict] = []
        for route_stop, stop_info in stops:
            if stop_info is not None:
                label = f"{route_stop.seq}. {stop_info.name_en}"
                if stop_info.name_tc and stop_info.name_tc != stop_info.name_en:
                    label += f" {stop_info.name_tc}"
            else:
                label = f"{route_stop.seq}. {route_stop.stop_id}"
            options.append(
                selector.SelectOptionDict(value=route_stop.stop_id, label=label)
            )

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                            sort=False,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_time_format(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 5: choose between clock time and minutes-until-arrival."""
        assert self._route_infos is not None and self._direction is not None

        if user_input is not None:
            info = self._route_infos[self._direction]
            orig_en, dest_en = info.orig_en, info.dest_en
            orig_tc, dest_tc = info.orig_tc, info.dest_tc
            if self._direction == DIRECTION_INBOUND:
                # Citybus route info is direction-agnostic; an inbound bus
                # heads back towards the route's origin.
                orig_en, dest_en = dest_en, orig_en
                orig_tc, dest_tc = dest_tc, orig_tc

            title = f"{self._company} {self._route} → {dest_en} @ {self._stop_name_en}"
            return self.async_create_entry(
                title=title,
                data={
                    CONF_COMPANY: self._company,
                    CONF_ROUTE: self._route,
                    CONF_DIRECTION: self._direction,
                    CONF_STOP_ID: self._stop_id,
                    CONF_STOP_NAME_EN: self._stop_name_en,
                    CONF_STOP_NAME_TC: self._stop_name_tc,
                    CONF_ORIG_EN: orig_en,
                    CONF_ORIG_TC: orig_tc,
                    CONF_DEST_EN: dest_en,
                    CONF_DEST_TC: dest_tc,
                },
                options={
                    CONF_TIME_FORMAT: user_input[CONF_TIME_FORMAT],
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                },
            )

        return self.async_show_form(
            step_id="time_format",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TIME_FORMAT): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(TIME_FORMATS),
                            translation_key=CONF_TIME_FORMAT,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HkBusEtaOptionsFlow:
        """Return the options flow handler."""
        return HkBusEtaOptionsFlow(config_entry)


class HkBusEtaOptionsFlow(OptionsFlow):
    """Options: display format and polling interval."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TIME_FORMAT,
                        default=current.get(CONF_TIME_FORMAT, TIME_FORMAT_TIMESTAMP),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(TIME_FORMATS),
                            translation_key=CONF_TIME_FORMAT,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
