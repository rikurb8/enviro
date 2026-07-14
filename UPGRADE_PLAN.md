# Upgrade plan: latest MicroPython + library refresh

_Drafted 2026-07-13._

## Context

This repo is a fork of Pimoroni's Enviro firmware (Pico W boards: Indoor, Grow, Weather, Urban) with local additions (desktop testbench, Flask/SQLite dashboard, provisioning call-home). It hasn't been updated in a while; this plan brings it to the latest MicroPython and refreshes other dependencies.

Current state (verified 2026-07-13):

- MicroPython is pinned to **pimoroni-pico v1.22.2** (MicroPython 1.22, ~early 2024) in `.github/workflows/release-zip.yml`.
- Latest upstream pimoroni-pico release with an Enviro build is **v1.27.0** (Feb 2026, MicroPython 1.27). Asset naming changed: it is now `enviro-v1.27.0-pimoroni-micropython.uf2` (was `pimoroni-enviro-v1.22.2-micropython.uf2`).
- Upstream `pimoroni/enviro` has been dormant since April 2024, and this fork already contains its last commits (CSV patch, v1.22.2 CI bump) — **no upstream merge needed**.
- `phew` submodule is pinned to `b33a44b`; upstream phew's latest commit is `751c404` (June 2024: fixes form-data read to content-length, stops defaulting to debug log level).
- CI workflow uses the removed `ubuntu-20.04` runner (GitHub retired it in 2025 — the workflow is broken today regardless), `dir2uf2 v0.0.1`, and `littlefs-python==0.4.0` (too old for the LittleFS format in MicroPython ≥1.23; dir2uf2 v0.1.0 pins `littlefs-python==0.12.0`).
- Desktop tooling (uv-managed: flask, sqlmodel, pytest) is recent; only a routine lock refresh is warranted.

Note: `origin` is a Forgejo instance, so the GitHub Actions workflow may never actually run there — but it is the only place the firmware version is pinned, and the docs/manual flashing flow derive from it, so it stays the source of truth.

## Changes

### 1. Bump MicroPython firmware pin → pimoroni-pico v1.27.0

File: `.github/workflows/release-zip.yml`

- `FIRMWARE_NAME: enviro-v1.27.0-pimoroni-micropython` (note the new naming scheme)
- `FIRMWARE_URL: https://github.com/pimoroni/pimoroni-pico/releases/download/v1.27.0`

### 2. Update phew submodule

- `git submodule update --init phew`, then check out upstream `pimoroni/phew` commit `751c404` inside the submodule and commit the new pointer.

### 3. Fix/modernize the CI workflow

File: `.github/workflows/release-zip.yml`

- Runner: `ubuntu-20.04` → `ubuntu-24.04`.
- `dir2uf2` checkout ref: `v0.0.1` → `v0.1.0`.
- `littlefs-python==0.4.0` → `littlefs-python==0.12.0` (matches dir2uf2 v0.1.0's `requirements-micropython-1.23.0.txt`; required for the LittleFS format used by MicroPython ≥1.23).
- `actions/upload-release-asset@v1` is archived/deprecated — optionally replace the three upload steps with `gh release upload` or `softprops/action-gh-release@v2` (only while we're touching the file anyway).

### 4. Docs

File: `documentation/upgrading-firmware.md` (line 40) — asset name reference `pimoroni-picow-enviro` → the new `enviro-vX.Y.Z-pimoroni-micropython` naming.

### 5. Compatibility check for MicroPython 1.22 → 1.27

The firmware code imports u-prefixed modules: `ujson` (`enviro/__init__.py:96`, `enviro/destinations/mqtt.py`), `urequests` (`enviro/destinations/http.py`, `influxdb.py`, `adafruit_io.py`, `enviro/provisioning.py:173`), and `usocket`/`ustruct`/`ubinascii`/`ussl` in the vendored `enviro/mqttsimple.py`.

- Built-in u-aliases (`ujson`, `ubinascii`, `ustruct`, `usocket`, `ussl`) still resolve in MicroPython 1.27, and `urequests` ships as a deprecated shim in Pimoroni builds — expected to work as-is.
- Verify on-device (see Verification); if any import fails on 1.27, switch to the un-prefixed names (`json`, `requests`, etc.) — a mechanical rename. Optionally do the rename proactively; the desktop testbench shims (`tests/sim/urequests.py`) would need matching aliases.

### 6. Desktop dependencies (minor)

- `uv lock --upgrade && uv sync` to refresh `uv.lock` within existing constraints (`flask>=3.0,<4`, `sqlmodel>=0.0.22,<1`, `pytest>=8`). Constraints themselves are current; no `pyproject.toml` changes needed.

### 7. Version bump

- `enviro/constants.py`: `ENVIRO_VERSION = "0.0.10"` → `"0.1.0"` (signals the firmware-base jump; version is reported in logs/uploads).

## Verification

1. Desktop testbench: `uv run pytest` — must pass after the lock refresh (and after any u-module renames, if made).
2. On-device (manual, needs the Pico W):
   - Download `enviro-v1.27.0-pimoroni-micropython.uf2` from the pimoroni-pico v1.27.0 release; flash via BOOTSEL/RPI-RP2.
   - Copy firmware files with the existing `install-on-device-fs` script (mpremote), including the updated `phew/`.
   - Smoke test: provisioning portal comes up, a reading cycle completes, and the configured destination upload (or the local dashboard call-home at `server/app.py`) receives data.
3. CI (if Forgejo/GitHub Actions is enabled): push a branch and confirm the Build Zip workflow downloads the v1.27.0 uf2 and dir2uf2 appends the filesystem without littlefs errors.

## Out of scope

- Merging from upstream `pimoroni/enviro` (already up to date; upstream dormant since April 2024).
- pimoroni-pico v1.29 preview builds — stick to stable v1.27.0.
