# Hargassner Cloud

A Home Assistant custom component that brings Hargassner wood-pellet and biomass
boilers into Home Assistant through the manufacturer's web portal at
`web.hargassner.at`.

Hargassner does not document or support this portal for outside use. The
component is built by observing what the portal itself requests and returns, and
it is maintained by the community. Treat it as a convenience rather than an
official interface: the portal can change shape at any time.

## Installing

The quickest route is HACS:

1. In Home Assistant, open **HACS** and switch to the **Integrations** section.
2. From the overflow menu, pick **Custom repositories** and add
   `https://github.com/mumat/hargassner-cloud-ha`, category **Integration**.
3. Search for **Hargassner Cloud**, install it, and restart Home Assistant.

To install without HACS, copy the `custom_components/hargassner_cloud` folder
from this repository into your Home Assistant `custom_components` directory and
restart.

## Adding your boiler

Go to **Settings → Devices & services → Add integration** and choose
**Hargassner Cloud**.

Sign in with the same email address and password you use on the Hargassner web
portal or mobile app. A portal host and an area are optional; the host defaults
to `web.hargassner.at` and the area is left empty.

If your account can reach more than one installation, you are asked which one to
add. Every installation you add becomes its own Home Assistant device, and the
component reports the boiler's firmware/software version when the portal exposes
it.

## What shows up in Home Assistant

Only the widgets and fields your installation actually reports are turned into
entities, so the exact set differs from boiler to boiler.

**Readings.** Boiler status and operating program, current and target boiler
temperature, flue-gas temperature, efficiency, pellet stock, current and average
outdoor temperature, buffer status/charge/temperature, per-boiler temperature and
charge, per-heating-circuit flow and room temperatures, and heat-source/request
temperatures on controller-style installations.

**Status flags.** Whether the cloud connection is up, whether the boiler is
running, the exhaust guard, buffer pump and force-charging state, and pump/active
flags for each numbered boiler and heating circuit.

**Setpoints.** Pellet stock, hot-water target, day and reduced room
temperatures, room-temperature correction, heating-curve steepness, and the
heating/reduced deactivation limits.

**Selections.** Heating-circuit operating mode, boiler program, solar mode, and
the bathroom/pool heating options where the installation offers them.

**Buttons.** Force an immediate hot-water charge, acknowledge pending events,
and start ignition.

**Thermostats.** One climate entity per heating circuit, wired to that circuit's
room setpoint and mode.

Numbered boilers and heating circuits are discovered from the data, so there is
no fixed limit on how many a system may have.

## Optional extras

Open **Settings → Devices & services → Hargassner Cloud → Configure** to reach
these. Saving reloads the component.

**Polling interval.** How often the portal is read, in seconds. Defaults to 300;
anything below 30 is refused.

**Area.** A suggested Home Assistant area for the device.

**Expose every writable parameter.** Off by default. Turning it on walks every
writable parameter the installation reports and adds a control for each one it
has not already covered — a select when the parameter lists choices, a switch
when its value is a boolean, or a number when it advertises a range. This is how
an unfamiliar boiler model can pick up controls without a code change; the
trade-off is a longer, less curated entity list.

**Measurement channels.** Off by default. Turning it on reads the portal's
separate measurement-history endpoint and adds diagnostic sensors for the extra
channels a system may expose, such as oxygen content, return temperatures,
system pressure, pellet inventory or humidity. These live outside the main
polling response, so they are treated as best-effort: a failure here is logged
quietly and never disturbs the regular updates.

**Field overrides.** A JSON object, normally left empty, for pointing an entity
at a different widget field when a model names things unusually. Each key is the
entity's key; `widget` and `field` are required and `number` is optional.

```json
{
  "heater_smoke_temp": {
    "widget": "HEATER",
    "field": "smoke_temperature"
  },
  "buffer_temp_top": {
    "widget": "BUFFER",
    "field": "buffer_temperature_top"
  },
  "hc1_flow_temp_target": {
    "widget": "HEATING_CIRCUIT_FLOOR",
    "field": "flow_temperature_target",
    "number": "1"
  }
}
```

Malformed JSON is rejected by the dialog.

## How signing in works

Alongside your email and password, the portal expects a `client_id` and
`client_secret` that belong to Hargassner's own web frontend. These are not
personal secrets. The component reads the current pair from the live frontend
and keeps a known-good pair as a fallback, so a change on Hargassner's side does
not permanently lock you out.

Rejections are handled differently depending on their cause:

- Your **password** being wrong opens Home Assistant's reauthentication dialog.
- The **frontend credentials** being rejected or unfindable raises a repair
  issue instead, because your password is not the problem.
- **Scheduled maintenance** is treated as a temporary outage: entities go
  unavailable and recover on their own, with no prompt and no repair issue.

## Privacy

The component only makes outbound HTTPS requests to the Hargassner host you
configure. Nothing is sent anywhere else.

Diagnostics are generated from a reduced view of the data: usernames, passwords,
tokens, installation IDs, names, serial numbers and location fields are
redacted, and the widget payload is collapsed to field names and value types
rather than live readings. As with any integration built on an undocumented API,
it is worth a glance before sharing a diagnostics file publicly.

## Working on it

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Then run the checks:

```bash
python -m compileall custom_components tests
pytest
ruff format --check custom_components tests
ruff check custom_components tests
mypy custom_components tests
```

The tests never touch the network. A live check against the real portal is opt-in
and skipped unless credentials are supplied:

```bash
export HARGASSNER_USERNAME=you@example.com
export HARGASSNER_PASSWORD=...
pytest -m live
```

## Licence

MIT. See [LICENSE](LICENSE). Hargassner is a trademark of its respective owner;
this project is unaffiliated with the company.
