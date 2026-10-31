# Telegram C2 Bot

Remote control of a host and its Docker containers through configured Actions, invoked from Telegram or HTTP.

## Language

### Invoking work

**Action**:
A named, configured unit of work with allowed Roles, tags, and staged Handlers. The same Action is reachable as a Command and as an Endpoint.
_Avoid_: Telegram command (when meaning the unit of work), job, task

**Command**:
The Telegram way of invoking an Action (`/status`), or one of the built-in meta commands (`/help`, `/action_info`, `/actions_by_tag`, `/reload_actions`).
_Avoid_: Action (when meaning the Telegram message)

**Endpoint**:
The HTTP way of invoking an Action (`POST /actions/status`).
_Avoid_: Route (outside implementation talk), API command

**Alias**:
An alternative Command name for an Action. Aliases have no Endpoint of their own.

**Handler**:
One step of an Action, either local code or a Host Operation, run in a numbered stage.

**Host Operation**:
A whitelisted program on the host machine, run by the host runner on behalf of a Handler.
_Avoid_: host action, script

### Access

**User**:
A Telegram user ID with one or more Roles.

**Role**:
A named permission. An Action runs only if the User holds at least one of its allowed Roles; `admin` is additionally required for `/reload_actions`.

**API Key**:
A secret that lets an HTTP caller act as a specific User, with that User's Roles.
_Avoid_: token (reserved for the Telegram bot token)
