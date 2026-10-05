"""Constants for the HK Bus Time Table integration."""

from typing import Final

DOMAIN: Final = "hk_bus_timetable"

CONF_COMPANY: Final = "company"
CONF_ROUTE: Final = "route"
CONF_DIRECTION: Final = "direction"
CONF_STOP_ID: Final = "stop_id"
CONF_STOP_NAME_EN: Final = "stop_name_en"
CONF_STOP_NAME_TC: Final = "stop_name_tc"
CONF_ORIG_EN: Final = "orig_en"
CONF_ORIG_TC: Final = "orig_tc"
CONF_DEST_EN: Final = "dest_en"
CONF_DEST_TC: Final = "dest_tc"
CONF_TIME_FORMAT: Final = "time_format"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DIRECTION_OUTBOUND: Final = "outbound"
DIRECTION_INBOUND: Final = "inbound"

TIME_FORMAT_TIMESTAMP: Final = "timestamp"
TIME_FORMAT_MINUTES: Final = "minutes"
TIME_FORMATS: Final = [TIME_FORMAT_TIMESTAMP, TIME_FORMAT_MINUTES]

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 600
