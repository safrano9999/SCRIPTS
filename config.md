# config.sh reference

This document describes the current SOT behavior of
`SCRIPTS/safrano9999/config.sh` and the example-file directives used by the
safrano9999 repositories and container image repositories.

`config.sh` is intentionally root-local: it reads example files in the current
project directory and writes generated config files into that same directory.
Container image `setup.sh` scripts may move or patch those generated files into
`CONTAINER/<container-name>/`, but that is setup-layer logic, not `config.sh`
logic.

## Entry Points

`config.sh` decides its working directory as follows:

- If `env.example`, `config.conf_example`, or `container.example` exists next to
  the script itself, that script directory is used.
- Otherwise the current working directory is used.

It supports:

- `--no-container`: do not configure `container.conf` and do not generate
  compose/quadlet files.
- `--show`: accepted by argument parsing, currently only stored in
  `CONFIG_SHOW`; no active output mode is implemented by `config.sh` itself.

## Generated Files

Default output files:

- `.env`
- `config.conf`
- `container.conf`
- `build.conf`

When any example file contains a `#CONTAINER-NAME` marker followed by
`CONTAINER_NAME=...`, container-name mode is enabled. Then files become:

- `<container>.env`
- `<container>_config.conf`
- `<container>_container.conf`
- `<container>_build.conf`
- `<container>-compose.yml`
- `<container>.container`

`CONFIG_CONTAINER_NAME` can force the container name non-interactively. Without
that variable, an interactive terminal is prompted with the example default.

## Example File Classes

`config.sh` processes example files in this order:

1. `*build.conf_example` -> `build.conf` or `<container>_build.conf`
2. `env*example` -> `.env` or `<container>.env`
3. `config*example` -> `config.conf` or `<container>_config.conf`
4. `container*example` and `config*.container` -> `container.conf` or
   `<container>_container.conf`

The matching is shell glob based. This means files such as
`env.cloudflare.example`, `config.cloudflare.conf_example`,
`container.fedora44-ai.example`, and `fedora.build.conf_example` are picked up
when they match the relevant glob in the project root.

## Value Lookup Priority

`config_value KEY` resolves values in this order:

1. `container.conf` or `<container>_container.conf` unless `--no-container`
2. `config.conf` or `<container>_config.conf`
3. `.env` or `<container>.env`
4. `container.example` unless `--no-container`
5. `config.conf_example`
6. `env.example`

This priority matters for generated ports, volumes, mounts, persistence, and
conditional directives.

## Basic Key Handling

Only lines shaped like `KEY=value` are configurable. Keys must match:

```text
^[A-Za-z_][A-Za-z0-9_]*$
```

Blank lines reset pending one-shot directives such as `#required`, `#secret`,
`#choices`, `#when`, `#when-not`, and `#default-if`.

Existing values are preserved. Required keys are only prompted again if the key
is absent or present with an empty value.

If a non-empty key already exists in another runtime configuration file, it is
left there and reported as `exists in <file>`. `config.sh` does not copy or move
the value into the current target. Runtime files are loaded together, so a key
must have only one owner among `.env`, `config.conf`, and `container.conf`.

After configuration, the target file is rewritten against its example file so
comments and ordering from the example are preserved. Unknown local keys are
appended under `# Additional local values`.

## Supported Directives

### `#required: TEXT`

Applies to the next `KEY=value`. The key must receive a non-empty value unless
an existing non-empty value already exists.

The text after `#required:` is informational for humans; the script only uses
the directive as a boolean flag.

### `#secret`

Applies to the next `KEY=value`. In an interactive terminal the value is read
with hidden input. The value is still written to the generated target file.

This directive is also meaningful for external tooling such as welcome/reference
generation, where secret variables can be redacted.

### `#default-preset: VALUE`

This is not parsed as a separate directive by `config.sh`. It is preserved as a
comment and acts as documentation for the default value written on the next
`KEY=value` line.

The actual default used by `config.sh` is the value after `=` in the example
line. For a real preset, the example line itself must contain the desired
default:

```text
#default-preset: 443
OPENAI_V1_PORT=443
```

### `#choices: A B C`

Applies to the next key. The prompt shows `[A/B/C]`.

Accepted input:

- Literal value matching one of the listed choices.
- Numeric index, where `1` selects the first choice.

Invalid values are rejected and the user is prompted again.

Current examples include:

- `NOTE_DB_BACKEND`: `file sqlite mariadb postgres`
- `NOTE_TRIGGER_TYPE`: `none webhook cli`

### `#when: KEY=value`

Applies to the next key. If the condition is not true, the target key is written
as:

```text
TARGET=blank
```

The condition value is normalized for booleans:

- `0 false no off` -> `false`
- `1 true yes on` -> `true`

Current example: `NOTE_PATH` only matters when `NOTE_DB_BACKEND=file`.

### `#when-not: KEY=value`

Opposite of `#when`. If the condition is true, the target key is written as
`blank`.

Current example: `NOTE_TRIGGER` is blanked when `NOTE_TRIGGER_TYPE=none`.

### `#default-if: KEY=value DEFAULT`

Applies to the next key. If `KEY` currently resolves to `value`, the next key's
default is replaced by `DEFAULT`.

Boolean values use the same normalization as `#when`.

### `#blank-if: KEY=value TARGET_A TARGET_B ...`

Registers a rule. When `KEY` is configured or found with `value`, every target
listed is auto-written as:

```text
TARGET=blank
```

This is heavily used for database backends. Example:

```text
#blank-if: KACHELMANN_DB_BACKEND=sqlite KACHELMANN_DB_URL KACHELMANN_DB_PORT KACHELMANN_DB_NAME KACHELMANN_DB_USER KACHELMANN_DB_PW KACHELMANN_DB_PREFIX
KACHELMANN_DB_BACKEND=sqlite
```

When the backend is `sqlite`, network database fields become `blank`.

### `#repeat-group: GROUP STYLE FIELD...`

Defines a repeatable set of keys. A group can be configured once, skipped, or
extended with the next free index.

Styles:

- `suffix`: index 1 uses `FIELD`; index 2 uses `FIELD_2`.
- `suffix02`: index 1 uses `FIELD`; index 2 uses `FIELD_02`.
- `infix`: index 1 uses `FIELD`; index 2 uses `GROUP_2_<field-tail>`.

Completion detection:

- The script scans indexes 1 through 50.
- A slot is complete when all required fields in the group have non-empty
  values, except fields marked by `#repeat-optional-complete`.
- If at least one complete slot exists, the user is prompted with `skip/new`.
- `skip` skips the whole group for this run.
- `new` writes the next free indexed group.

Current important groups:

- `OPENAI_V1 suffix OPENAI_V1_PROVIDER OPENAI_V1_URL OPENAI_V1_PORT OPENAI_V1_KEY OPENAI_V1_API_KEY_ALIAS`
- `ZEROINBOX suffix ZEROINBOX_PROVIDER ZEROINBOX_EMAIL ZEROINBOX_APP_PASSWORD`
- `ZEROINBOX suffix ZEROINBOX_ONLY_UNSEEN`
- `NEXTCLOUD suffix02 NEXTCLOUD_URL NEXTCLOUD_USER NEXTCLOUD_PW NEXTCLOUD_SYNC_FOLDERS NEXTCLOUD_TIMER NEXTCLOUD_CALENDAR`
- `CALENDAR infix CALENDAR_URL CALENDAR_USER CALENDAR_PASSWORD`

### `#repeat-optional-complete: FIELD...`

Marks repeat-group fields that do not have to be non-empty for the slot to count
as complete.

Current example:

```text
#repeat-optional-complete: NEXTCLOUD_SYNC_FOLDERS
```

This lets a Nextcloud account count as complete even if file sync is blank.

### `#repeat-freeform: FIELD...`

Keeps the first repeat entry's preset and choices, but clears both for later
indexed entries. The group still uses the normal `skip/new` prompt. This lets
the first `ADDITIONAL_LINE` offer known network modes while
`ADDITIONAL_LINE_02`, `_03`, and later entries accept arbitrary Quadlet lines.

### `${REPEAT_SUFFIX}`

Within defaults in a repeat group, `${REPEAT_SUFFIX}` is replaced as:

- empty string for index 1
- `_02`, `_03`, ... for later indexes

Current example:

```text
NEXTCLOUD_SYNC_FOLDERS=/named_volumes/NEXTCLOUD${REPEAT_SUFFIX}|/
```

Index 2 becomes:

```text
NEXTCLOUD_SYNC_FOLDERS_02=/named_volumes/NEXTCLOUD_02|/
```

### `${CONTAINER_NAME}`

Within defaults, `${CONTAINER_NAME}` is replaced with the active container name.
It is also expanded inside `*_VOLUMES` values when generating compose/quadlet.

### `#valuedupe: TARGET`

Applies to the next key. After that source key gets a value, the user is asked
whether the same value should be reused for `TARGET`, but only if `TARGET` is
not already set.

This is intended for cases where two variables often intentionally share a
secret or token.

### `#reverse-varname: SOURCE`

Applies to the next key, which is treated as an alias-variable-name field.

When the alias field receives a valid shell variable name, `config.sh` writes a
new variable with that alias name and copies the current value from `SOURCE`.

Current OpenAI-v1 example:

```text
OPENAI_V1_KEY=...
#reverse-varname: OPENAI_V1_KEY
OPENAI_V1_API_KEY_ALIAS=GEMINI_API_KEY
```

Result:

```text
OPENAI_V1_KEY=secret
OPENAI_V1_API_KEY_ALIAS=GEMINI_API_KEY
GEMINI_API_KEY=secret
```

Inside repeat groups the source key is indexed consistently. For
`OPENAI_V1_KEY_2`, the alias receives the value from `OPENAI_V1_KEY_2`.

### Provider selectors

Any key matching `(^|_)PROVIDER(_[0-9]+)?$` is treated as a provider selector.

If a provider file exists, the prompt shows numbered provider options.
Provider files are resolved in this order:

1. `provider.conf` next to the example file.
2. `provider.conf` in the project root.
3. For keys containing `_PROVIDER`, `safrano9999/<prefix>-provider.conf`.
4. First `safrano9999/*-provider.conf` found.

Provider sections are read from:

```text
[provider.name]
```

Numeric provider input is normalized to the provider name. Non-numeric input is
lowercased.

### OpenSSL generator defaults

If a required key has a default shaped like:

```text
example: openssl rand -hex N
example: openssl rand -base64 N
```

then an interactive user can choose between manual input and generation. In
non-interactive mode the value is generated automatically.

## Database Backend Logic

Any key matching:

```text
*_DB_BACKEND
*_DB_HOST
*_DB_URL
*_DB_PORT
*_DB_NAME
*_DB_USER
*_DB_PW
*_DB_PASSWORD
*_DB_PREFIX
```

is recognized as database config.

Backends are normalized:

- `postgresql`, `pgsql`, `psql` -> `postgres`
- `mysql` -> `mysql`
- `mariadb` -> `mariadb`
- `sqlite3` -> `sqlite`

If an env target contains more than one `*_DB_BACKEND` group and none of the DB
keys already exists, `config.sh` offers bulk setup:

1. Use selected backend for all.
2. Configure individually.

For `sqlite`, all non-backend DB fields are written as `blank`.

For server databases, the script asks for common host, port, name, user, and
password, then writes all detected DB key groups. Default port:

- `postgres`: `5432`
- `mysql` / `mariadb`: `3306`

## GUI Environment Special Case

If the key is `DISPLAY`, `config.sh` uses special GUI/XDG handling.

Interactive choices:

1. Autodetect GUI environment.
2. Enter manual values.

It writes:

- `DISPLAY`
- `NO_AT_BRIDGE`
- `XDG_RUNTIME_DIR`

`NO_AT_BRIDGE` and `XDG_RUNTIME_DIR` are then skipped when encountered later in
the same example.

## Container Generation

Unless `--no-container` is used, `config.sh` creates or updates:

- `docker-compose.yml` or `<container>-compose.yml`
- `<container>.container`

Generation only happens when a port is discoverable or `webui.py` exists.

Image selection:

1. `<PROJECT_NAME>_IMAGE` where project name is uppercased and `-` becomes `_`.
2. `IMAGE`.
3. Existing generated quadlet/compose image.
4. `localhost/<container>:latest`.

If `Containerfile` or `Dockerfile` exists, compose includes a local build block.

If `webui.py` exists, compose/quadlet uses:

```text
uvicorn webui:app --host 0.0.0.0 --port <first-port>
```

## Port Rules

`*_PUBLISH_PORT` generates published port mappings.

Container image setup scripts use the shared `container_instance.py` helper to
persist `CONTAINER_NR` in `<container>_container.conf`:

- `TUN` is the default for new instances.
- Blank means manual publish-port configuration.
- `2` through `5` select the blocks `20000-29999` through `50000-59999`.
- `TUN` disables all host port publishing while retaining normal container
  networking for an in-container Tailscale or Cloudflare tunnel.

With a numeric block, publish-port presets must be below `20000`. The last four
digits are retained, so block `3` projects `11002` to `31002`, `8077` to
`38077`, and `13333-13340` to `33333-33340`. Internal `*_PORT` values do not
change. If more than one publish port is missing, `config.sh` asks once whether
all projected defaults should be accepted. That answer is runtime-only; only
the resulting ports and `CONTAINER_NR` are persisted.

The shared Python helper owns instance discovery, range labels, explicit range
selection, and migration into `CONTAINER/<name>/`. `config.sh` only applies the
selected mode while processing `container*example` files. It does not infer or
reserve ranges across separate image repositories.

For a key:

```text
FOO_PUBLISH_PORT=11000
```

the internal port is resolved from:

```text
FOO_PORT
```

If `FOO_PORT` is not set, the publish port is also used as the internal port.

The publish host is resolved from:

1. `FOO_PUBLISH_HOST`
2. Global publish host directive via `#publish-host: KEY`
3. `127.0.0.1`

Final mapping:

```text
<publish-host>:<publish-port>:<internal-port>
```

Plain `PORT` or non-publish `*_PORT` only establishes the first internal port
for commands and fallback identity mapping.

### `#publish-host: KEY`

Declares which key should provide the default publish host for generated port
mappings.

## Volume And Device Rules

### `*_VOLUMES`

CSV list of volume specs. Relative sources are normalized to absolute paths
under the project root.

If the source is a simple name without `/`, `.`, `~`, or `$`, it is also added
as a named volume in compose.

`${CONTAINER_NAME}` is expanded before volume generation.

### `*_CAPABILITIES`

CSV list. Generates compose `cap_add` and quadlet `AddCapability=`.

### `*_DEVICES`

CSV list. Generates compose `devices` and quadlet `AddDevice=`.

### `ADDITIONAL_LINE` and `ADDITIONAL_LINE_02`

Any key matching `ADDITIONAL_LINE(_[0-9]+)?` is copied literally into the
quadlet if the value is not blank/null. This is used for custom lines such as
network options:

```text
ADDITIONAL_LINE=Network=slirp4netns:mtu=1500
```

## Bind Mount Directives

### `#mount-bind: KEY...`

For each listed key, the configured value is treated as a relative path and
mounted into:

```text
/opt/safrano9999/<PROJECT>/<relative-path>
```

Absolute and parent-relative values are ignored for safety.

### `#mount-if: KEY=value PATH...`

If the condition matches, every listed relative path is mounted into:

```text
/opt/safrano9999/<PROJECT>/<relative-path>
```

Boolean values are normalized.

### `_SOT.md` files in `.gitignore`

If `.gitignore` contains entries ending in `_SOT.md`, `config.sh` creates/touches
those files and bind-mounts them into the matching project path inside
`/opt/safrano9999/<PROJECT>/`.

## SQLite Persistence

After container config, `config.sh` calls `sqlite_persistence.sh`.

Initialization:

- If `safrano9999/<repo>/env.example` exists, every staged repo with a
  configured `*_DB_BACKEND=sqlite` gets a `sqlite/` directory.
- Otherwise the current repo is checked.

Mount generation:

- For source repos: target defaults to `/opt/safrano9999/<repo>/sqlite`.
- For plugin zip roots: target defaults to `/root/.openclaw/extensions/<plugin-id>/sqlite`.

Named volume format:

```text
<container>-<db-prefix>-sqlite:<target>/sqlite:Z
```

Only `sqlite` / `sqlite3` backends generate these sqlite volumes.

## Optional Persistence

`optional_persistence.sh` contributes additional mounts and environment values.

### `*_PERSISTENT_PATH`

Any configured key ending in `_PERSISTENT_PATH` creates:

```text
<container>-<prefix>-persistent:<path>:Z
```

It also emits an environment entry:

```text
KEY=<path>
```

Blank/null values disable the mount.

### `#named-volume: MOUNT SOURCE TARGET KIND`

This directive applies to the next `KEY=value`. If that key resolves to a true
value (`1`, `true`, `yes`, `on`), a named volume mount is generated.

Fields:

- `MOUNT`: path where the named volume is mounted in the container.
- `SOURCE`: path inside that mount.
- `TARGET`: final path to link or populate.
- `KIND`: optional, one of `file`, `dir`, `link`; empty is accepted.

Enabled named volumes generate:

```text
<container>-<basename-of-mount>:<mount>:Z
```

They also emit:

```text
NAMED_VOLUME_LINKS=<mount>|<source>|<target>|<kind>;...
```

This environment value is consumed by the runtime named-volume link helper.

Current examples include ZEROINBOX `REPORTS`, `logs`, and `maildir` volumes.

### `*_SYNC_FOLDERS`

Any configured key matching:

```text
*_SYNC_FOLDERS
*_SYNC_FOLDERS_02
```

is parsed as CSV of:

```text
LOCAL_PATH|REMOTE_PATH
```

If `LOCAL_PATH` starts with `/named_volumes/`, a named volume is generated:

```text
<container>-<basename-of-local-path>:<local-path>:Z
```

This is used by NEXTCLOUD.

## Cloudflare Examples

Cloudflare service examples are just normal env/config examples:

- `env.cloudflare.example`
- `config.cloudflare.conf_example`
- `config.cloudflare.container`

They are picked up by the generic globs when copied or linked into a project
root.

Secrets such as tunnel tokens are marked with `#secret`. Start switches such as
`CLOUDFLARED_START=1` are normal config keys.

## Known Current Pattern Families

### OpenAI-v1 provider group

Used by multiple repos:

```text
#repeat-group: OPENAI_V1 suffix OPENAI_V1_PROVIDER OPENAI_V1_URL OPENAI_V1_PORT OPENAI_V1_KEY OPENAI_V1_API_KEY_ALIAS
```

Behavior:

- Can add more providers via `skip/new`.
- Indexed variables use `_2`, `_3`, ... because style is `suffix`.
- `OPENAI_V1_PORT` defaults to the example value, currently usually `443`.
- `OPENAI_V1_KEY` is secret.
- `OPENAI_V1_API_KEY_ALIAS` can create reverse alias env vars such as
  `GEMINI_API_KEY`, `XAI_API_KEY`, or `SAKANA_API_KEY`.

### ZEROINBOX account group

```text
#repeat-group: ZEROINBOX suffix ZEROINBOX_PROVIDER ZEROINBOX_EMAIL ZEROINBOX_APP_PASSWORD
```

Behavior:

- Index 1: `ZEROINBOX_PROVIDER`, `ZEROINBOX_EMAIL`, `ZEROINBOX_APP_PASSWORD`.
- Index 2: `ZEROINBOX_PROVIDER_2`, `ZEROINBOX_EMAIL_2`, ...
- Password is secret.

`ZEROINBOX_ONLY_UNSEEN` has its own repeat group so per-account config can
follow the same suffix.

### NEXTCLOUD account group

```text
#repeat-group: NEXTCLOUD suffix02 NEXTCLOUD_URL NEXTCLOUD_USER NEXTCLOUD_PW NEXTCLOUD_SYNC_FOLDERS NEXTCLOUD_TIMER NEXTCLOUD_CALENDAR
```

Behavior:

- Index 1 has no suffix.
- Index 2 uses `_02`.
- `NEXTCLOUD_SYNC_FOLDERS` is optional for slot completeness.
- Default sync folder can include `${REPEAT_SUFFIX}`.
- `/named_volumes/...` local sync paths generate named volumes.

### CALENDAR account group

```text
#repeat-group: CALENDAR infix CALENDAR_URL CALENDAR_USER CALENDAR_PASSWORD
```

Behavior:

- Index 1: `CALENDAR_URL`, `CALENDAR_USER`, `CALENDAR_PASSWORD`.
- Index 2: `CALENDAR_2_URL`, `CALENDAR_2_USER`, `CALENDAR_2_PASSWORD`.

### NOTE backend

NOTE is the current special case where `file` is a valid DB backend choice.
That is allowed because `NOTE/env.example` explicitly declares:

```text
#choices: file sqlite mariadb postgres
NOTE_DB_BACKEND=file
```

Other repos do not automatically get `file` as a backend choice.

## Non-Goals And Boundaries

- `config.sh` does not own container-instance folder layout.
- `config.sh` does not patch final absolute paths into `CONTAINER/<name>/`.
  That is `setup.sh` responsibility in image repos.
- `config.sh` does not build images.
- `config.sh` does not install plugins.
- `#default-preset` is documentation unless the following `KEY=value` line also
  contains that value.
