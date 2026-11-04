# Design notes

These notes describe how the `hargassner_cloud` integration is put together and
why. They are aimed at anyone extending or debugging it, not at end users; the
README covers installation and everyday use.

The integration is a thin, defensive wrapper around a portal that Hargassner
does not document for outside consumption. The guiding idea is that the portal's
responses — not our code — decide what exists. We describe only the fields we
understand, and let everything else flow through generic mechanisms.

## The portal, as seen from outside

Everything talks to a single configured host, `https://web.hargassner.at` by
default. Requests carry an `Accept` header, a fixed `Branding` value that the
portal expects, and a bearer token once we are signed in.

Session handling:

- `POST /api/auth/login` takes the account email and password together with the
  frontend's public client credentials, and returns a token (optionally wrapped
  in a `data` envelope), usually with a refresh token and lifetime.
- `POST /api/auth/refresh` exchanges a refresh token for a new access token.
- `POST /api/auth/logout` ends the session. The pre-2026 `/oauth/token` password
  grant is kept only as a last-resort fallback and currently answers 404.

Reads:

- `GET /api/installations` lists the installations on the account; the older
  `GET /api/user/installations` path is tried if the first returns 404.
- `GET /api/installations/{id}` with a `with=...` relations query returns device
  metadata such as the software version code.
- `GET /api/installations/{id}/widgets` returns the current state and the set of
  writable parameters and actions. The older `GET /api/widgets?installationId=`
  form is the fallback.

A widget is the unit of everything:

```jsonc
{
  "widget": "HEATING_CIRCUIT_RADIATOR",
  "number": "1",
  "values":     { "flow_temperature_current": 31.5, "state": "STATE_HEATING" },
  "parameters": { "mode": { "value": "MODE_AUTOMATIC",
                            "resource": "/installations/1/widgets/...",
                            "options": ["MODE_OFF", "MODE_AUTOMATIC"] } },
  "actions":    { "force_charging": { "resource": "...", "disabled": false } }
}
```

Writes never invent URLs: a parameter or action carries its own `resource`, and
we `PATCH {resource}` a new value or `POST {resource}` to fire an action.

A second, separate endpoint family carries history that the widget response does
not: `GET /api/devices/{id}/metric-fields` lists channels (with a label and unit)
and `GET /api/devices/{id}/measurements?channels=...&from=...&to=...` returns
samples. This is optional and treated as best-effort.

## Sign-in

Signing in has two layers that fail for different reasons, so they are handled
separately.

The account layer is the user's email and password. A rejected password is the
user's to fix, so it raises the Home Assistant reauthentication flow.

The application layer is the `client_id`/`client_secret` that belong to
Hargassner's own web frontend. They are not personal secrets, and the frontend is
rebuilt regularly, so the client reads the current pair from the live assets
(Vite manifest, then the login page bundle, then a legacy bundle) and keeps a
built-in pair as a fallback. If a login is rejected while using a fallback pair,
the client re-reads the live pair once and retries. If that still fails, the
problem is upstream and becomes a repair issue rather than a password prompt.

Tokens are cached and refreshed before they expire, behind a lock so that many
entities waking at once cannot stampede the login endpoint. A 401 on a data call
clears the token, renews it, and retries the same request once.

Scheduled maintenance is detected from the portal's own maintenance page and
surfaces as a temporary update failure, not as a credential problem.

## Modules

- `const.py` holds the domain, config and option keys, defaults and widget type
  names.
- `auth.py` owns the client-credential lookup and nothing else, so the brittle
  part is easy to test and swap.
- `api.py` is the HTTP client: tokens, requests, retries, parsing and a small,
  redacted diagnostics record.
- `models.py` turns the raw widget response into `InstallationState`,
  `CloudWidget`, `CloudParameter`, `CloudAction` and `Measurement` objects.
- `adapters.py` coerces loosely-typed portal values; `helpers.py` looks widgets
  up and classifies writable parameters.
- `coordinator.py` polls and maps failures onto Home Assistant's update model;
  `runtime.py` holds the typed runtime data.
- `entity.py` is the shared base (device registry info, field-override reads).
- The platform modules build entities: `sensor`, `binary_sensor`, `number`,
  `select`, `switch`, `button`, `climate`.
- `config_flow.py` and `options_flow.py` handle setup, reauth and options;
  `diagnostics.py` and `system_health.py` expose redacted operational detail.

## Which entities exist

Entities are generated from the returned widgets, so a given installation only
gets what it can support.

For the well-known fields we use explicit descriptions with translation keys,
device classes and units. Numbered boilers and heating circuits are discovered by
walking the widgets, so there is no fixed count.

For anything else, an optional toggle exposes every remaining writable parameter:
a select when it lists options, a switch when its value is boolean, or a number
when it advertises a range. This is the safety net that keeps unfamiliar models
usable without editing code.

A JSON field-override option lets a user repoint an entity at a different field
if a model names things unusually.

## Options

The options flow exposes the poll interval (minimum 30 seconds), an optional
area, the expose-everything toggle, the measurement toggle, and the field
overrides. Changing options reloads the entry.

## Failure handling

- A rejected account password raises `ConfigEntryAuthFailed`.
- Rejected or unfindable frontend credentials raise a repair issue and a normal
  update failure.
- Maintenance, connection and unexpected-status errors are update failures: the
  entities go unavailable and recover on the next successful poll.
- The optional measurement fetch catches its own errors and never disturbs the
  main poll.
- No stale data is served on failure; silence is shown as unavailable.

## Testing

Tests never touch the network. They cover value coercion, widget lookup, model
parsing, the auth paths (success, refresh, credential rotation, bad password,
maintenance, same-endpoint retry), the config and options flows with stubbed
clients, diagnostics redaction, translation-key parity, and the entity
builders. A `live`-marked check against the real portal is opt-in and skipped
without credentials.

## Known gaps and next steps

- More languages would be welcome; English and German ship today.
- A manual client-credential override could help if the frontend lookup breaks.
- A `quality_scale.yaml` would formalise the integration-quality metadata.
- The measurement channels are read as a snapshot; historical graphs are not
  exposed.
