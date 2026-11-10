# HK Bus Time Table — Home Assistant integration

[![Hassfest](https://github.com/Kuechenfenster/hk-bus-time-table/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/Kuechenfenster/hk-bus-time-table/actions/workflows/hassfest.yaml)
[![Marketplace validation](https://github.com/Kuechenfenster/hk-bus-time-table/actions/workflows/hacs.yaml/badge.svg)](https://github.com/Kuechenfenster/hk-bus-time-table/actions/workflows/hacs.yaml)

Real-time Hong Kong bus arrival times in Home Assistant, powered by the
official [data.gov.hk](https://data.gov.hk/en-datasets/category/transport)
real-time arrival APIs.

Each configured route/stop/direction creates three sensors: **next bus**,
**second bus** and **third bus**. Display them as clock times
(e.g. `17:03`) or as minutes until arrival (e.g. `6 min`) — your choice,
per entry.

## Supported operators

| Company | Covered routes | API |
|---|---|---|
| KMB / LWB (九巴 / 龍運) | e.g. 1A, 270, A31, N260 | `data.etabus.gov.hk` |
| Citybus / NWFB (城巴 / 新巴) | e.g. 5B, 788, A21 (CTB-operated) | `rt.data.gov.hk` |

Both are the official real-time arrival data feeds published on data.gov.hk.

## Requirements

- Home Assistant **2026.11 or newer** — the [Marketplace](https://www.home-assistant.io/integrations/marketplace/)
  is built in and lives under **Settings → Marketplace** (it replaces HACS).
- On Home Assistant 2026.10 or older, use the [manual installation](#manual-installation).

## Installation (Marketplace)

This integration is installed through the Marketplace as a custom repository.
Click the button, or follow the steps below:

[![Open your Home Assistant instance and open this repository inside the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Kuechenfenster&repository=hk-bus-time-table&category=integration)

1. Go to **Settings → Marketplace**.
2. Open the **⋮ menu** (or the custom repositories page) and choose
   **Add from link**.
3. Paste `https://github.com/Kuechenfenster/hk-bus-time-table`, select
   **Integration** and confirm. (Adding a repository that is not in the
   catalog needs a one-time GitHub device sign-in; installing from the
   catalog needs no GitHub account.)
4. Open **HK Bus Time Table** and click **Download**.
5. No restart is needed — this integration has a config flow, so setting it
   up starts right away:

[![Open your Home Assistant instance and start setting up HK Bus Time Table.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hk_bus_timetable)

### Migrating from HACS

If you installed this integration through HACS on 2026.10 or earlier, the
2026.11 update migrates everything automatically: installed projects, custom
repositories and update entities carry over, and HACS itself is removed. No
action needed.

### Manual installation

1. Copy the `custom_components/hk_bus_timetable` folder into your Home
   Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Everything is configured through the UI — no YAML required.

1. Go to **Settings → Devices & Services → Add Integration** and search for
   **HK Bus Time Table**.
2. **Bus company** — KMB/LWB or Citybus.
3. **Bus route** — enter the route number (e.g. `1A`). The route is validated
   live against the API.
4. **Direction** — pick origin → destination.
5. **Bus stop** — pick a stop from the route's stop list (searchable, English
   and Chinese names), **or type a stop ID directly** if you already know it.
6. **Display format** — clock times or minutes-until-arrival.

Repeat for every route/stop you want to track.

### Options

Via **Settings → Devices & Services → HK Bus Time Table → Configure**:

- **Update interval** — polling interval in seconds (default 30, min 15,
  max 600). Please don't hammer the public APIs.
- **Show arrivals as** — switch an existing entry between clock time and
  minutes-from-now.

## Entities

Each entry is one device with three sensors:

| Sensor | `timestamp` mode | `minutes` mode |
|---|---|---|
| Next bus | next arrival as date/time | minutes until arrival |
| Second bus | 2nd arrival | minutes until 2nd arrival |
| Third bus | 3rd arrival | minutes until 3rd arrival |

Attributes on every sensor: `company`, `route`, `direction`, `stop_id`,
`stop_name_en`, `stop_name_tc`, `origin_*`, `destination_*`, `eta_sequence`,
`scheduled_eta`, `remark_en`, `remark_tc` (e.g. "Scheduled Bus",
"原定班次", "Final stop") and `data_timestamp`.

If no prediction exists (route not running, terminus quiet), the sensor shows
`unknown` but stays available; if the API itself fails, sensors show
`unavailable` and recover automatically.

## Examples

Lovelace card:

```yaml
type: entities
title: "Bus 1A to Star Ferry"
entities:
  - sensor.kmb_1a_next_bus
  - sensor.kmb_1a_second_bus
  - sensor.kmb_1a_third_bus
```

Automation when using **minutes** mode (leave-home alert):

```yaml
alias: Bus almost at the stop
triggers:
  - trigger: numeric_state
    entity_id: sensor.kmb_1a_next_bus
    below: 6
actions:
  - action: notify.notify
    data:
      title: "🚌 Time to go"
      message: "Next 1A arrives in {{ states('sensor.kmb_1a_next_bus') }} minutes."
mode: single
```

## Notes & limitations

- KMB special departures (service type 2+, rare variant trips) are not
  selectable; mainline service type 1 is always used.
- A handful of stops appear on a route but have no live prediction while the
  bus is away — the sensors then read `unknown`, which is expected.
- On one-way/circular routes the API sometimes reports the "wrong" bound flag;
  the integration falls back to the unfiltered predictions in that case.
- Citybus route data was merged into CTB after the NWFB merger (2023) — NWFB
  routes work via the Citybus option.

## Development

- Validation runs in CI with [hassfest](.github/workflows/hassfest.yaml) and
  the [HACS action](.github/workflows/hacs.yaml) — since 2026.11 the HACS
  action validates against the Marketplace catalog requirements (the
  Marketplace reads `hacs.json`).
- **Releases:** the Marketplace shows and installs versions from GitHub
  releases, and the release **tag must match `version` in
  [`manifest.json`](custom_components/hk_bus_timetable/manifest.json)**.
  To cut a release: push the version bump, then
  `gh release create 1.0.0 --title 1.0.0 --notes "Release notes here"`.
- Brand icons in `custom_components/hk_bus_timetable/brand/` are generated
  with `python3 scripts/make_icons.py` (macOS, needs Pillow).
- `scripts/demo_api.py` smoke-tests the API layer against the live endpoints
  without Home Assistant: `python3 scripts/demo_api.py`
- The default catalog lives in the
  [`hacs/default`](https://github.com/hacs/default) repository — submit a PR
  there to list this integration in the Marketplace without the GitHub
  sign-in step.

## Credits

Bus real-time arrival data © Transport Department / data.gov.hk via the KMB
and Citybus ETA APIs. This project is not affiliated with the bus operators.
The bus icon is the Material Design Icons `bus` glyph (Apache-2.0).
