# Changelog

Notable, user-visible changes are recorded here.

## 0.1.1 — 2026-11-08

- Fixed writes (numbers, selects, switches, buttons): widget `resource` paths
  are now resolved under the portal's `/api` root instead of the host root.
- Send the client `Branding` header on every request, matching the official
  web client.
- Failed writes now record their phase/status in diagnostics and log the
  response body at debug level.

## 0.1.0 — 2026-11-04

First public version.

**Setup and sign-in**

- Guided setup that signs in with the account email and password, discovers the
  installations on the account, and asks which one to add.
- Automatic retrieval of the frontend's public client credentials, with a
  built-in fallback and a repair issue if they are rejected or cannot be found.
- Reauthentication when the account password itself stops being accepted.

**Home Assistant entities**

- Readings and status flags for the boiler, buffer, numbered boilers, heating
  circuits, heating controller and outdoor temperature.
- Writable setpoints, enumerated selections, boolean switches, action buttons and
  a thermostat for each heating circuit.
- A coordinator-driven poll with a configurable interval.

**Optional extras**

- A mode that exposes every remaining writable parameter as a control.
- Sensors for the portal's separate measurement-history channels.
- Field overrides for pointing an entity at a different widget field.
- Redacted diagnostics and a system-health entry.
- English and German translations.
