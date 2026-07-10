# enviro testbench

Runs the **real firmware code** on desktop Python (no device needed) by
shadowing every MicroPython/hardware module with a fake from `tests/sim/`.

```bash
uv run pytest tests/ -v
```

[uv](https://docs.astral.sh/uv/) fetches Python and the locked pytest
version automatically (see `pyproject.toml` / `uv.lock` at the repo root),
so a fresh clone needs nothing but uv itself. Without uv, any Python 3.9+
with pytest installed works too: `python3 -m pytest tests/ -v`.

## How it works

- `tests/sim/` contains fake versions of `machine`, `pimoroni_i2c`,
  `breakout_bme280`, `breakout_ltr559`, `pcf85063a`, `phew`, `network`,
  `urequests`, `wakeup`, `ujson`, ... `conftest.py` puts this directory
  first on `sys.path`, so when `enviro` imports them it gets the fakes.
- **Time is virtual** (`tests/sim/simtime.py`): `time.sleep()` returns
  instantly and just advances a virtual clock, `time.ticks_ms()` advances
  it by 1ms per call. Pump-run sleeps are recorded in `sim.clock.sleeps`,
  and the moisture-sensor tick-counting loop runs instantly.
- The `sim` fixture boots a fresh simulated **grow** board per test
  (i2c scan returns an ltr559 and pin 12 low, so board detection picks
  "grow"), with a fresh `config` built from `enviro/config_template.py`
  and cwd pointed at an empty temp dir (the firmware writes
  `readings/`, `uploads/`, `last_time.txt` etc. relative to cwd).

**Rule:** never import `enviro` at a test module's top level — importing
the package boots the firmware. Always go through the `sim` fixture
(`sim.enviro`, `sim.board`).

## What you can poke and assert

| Handle | What it does |
| --- | --- |
| `sim.config.<setting>` | change any config value (e.g. `auto_water`, `moisture_target_a`, `destination`) |
| `sim.bme280.sim_reading` | `(temperature_c, pressure_pa, humidity_pct)` |
| `sim.ltr559.sim_lux` | light level |
| `sim.machine.Pin.sim_set_tick_period(pin, ms)` | simulate a moisture sensor (20ms = dry ... 80ms = soaked; pins 15/14/13 = channels a/b/c) |
| `sim.machine.Pin.sim_writes(pin)` | every value written to a pin (pumps are pins 12/11/10 = a/b/c) |
| `sim.clock.sleeps` | recorded `time.sleep()` durations (pump run times) |
| `sim.urequests.sim_queue_response(status_code=, json=)` | queue the next HTTP response |
| `sim.urequests.sim_requests` | every HTTP request the firmware made (method, url, json payload) |
| `sim.logging.sim_entries` | everything the firmware logged |

## Testing a call-home that controls watering

The fake `urequests` is the hook. Your custom destination/call-home module
will `import urequests`, and in tests it gets the fake, so:

```python
def test_server_can_raise_moisture_targets(sim):
  sim.config.destination = "my_callhome"
  sim.urequests.sim_queue_response(json={"moisture_target_a": 80})
  # ... run the flow, then assert the pump behaviour:
  assert sim.machine.Pin.sim_writes(12) == [1, 0]
```

If you add new MicroPython-only imports to the firmware, add a matching
fake module to `tests/sim/`.

## Limits

- The fakes implement only what the firmware currently uses; extend them
  as needed (they're all tiny).
- `enviro.sleep()` ends with `machine.reset()`, which in the simulator
  raises `machine.SimulatedReset` — catch that if you drive a full
  `main.py`-style cycle.
- Provisioning mode isn't simulated (the fake config is always
  provisioned), and CPython won't catch MicroPython-specific issues
  (memory limits, missing stdlib corners) — still smoke-test on the
  device before a release.
