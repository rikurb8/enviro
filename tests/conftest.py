# pytest testbench for the enviro firmware
#
# runs the real firmware code under desktop cpython by shadowing all the
# micropython/hardware modules (machine, pimoroni_i2c, phew, urequests, ...)
# with the fakes in tests/sim. time is virtual: sleeps and ticks_ms are
# instant and deterministic. see tests/README.md.

import os
import sys
import time
import types
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
SIM = TESTS / "sim"

# sim modules must shadow micropython-only imports and the real phew
# submodule, so they go first on the path
for entry in (str(ROOT), str(SIM)):
  while entry in sys.path:
    sys.path.remove(entry)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

import simtime

# --- micropython api shims grafted onto cpython stdlib modules ------------
time.ticks_ms = simtime.clock.ticks_ms
time.ticks_us = lambda: simtime.clock.ticks_ms() * 1000
time.ticks_diff = lambda a, b: a - b
time.sleep = simtime.clock.sleep
time.sleep_ms = simtime.clock.sleep_ms

_real_mktime = time.mktime
def _mktime(t):
  t = tuple(t)
  if len(t) == 8:  # micropython 8-tuple -> cpython 9-tuple (isdst unknown)
    t = t + (-1,)
  return _real_mktime(t)
time.mktime = _mktime

# micropython flavoured os.ilistdir
os.ilistdir = lambda path=".": [(name, 0, 0) for name in sorted(os.listdir(path))]

# micropython flavoured sys.print_exception
import traceback
sys.print_exception = lambda exc, file=None: traceback.print_exception(
  type(exc), exc, exc.__traceback__, file=file or sys.stdout)


def _build_config():
  # a device config as provisioning would have written it, built from the
  # real template so new settings are picked up automatically
  cfg = types.ModuleType("config")
  exec((ROOT / "enviro" / "config_template.py").read_text(), cfg.__dict__)
  cfg.provisioned = True
  cfg.nickname = "simulator"
  cfg.wifi_ssid = "sim-network"
  cfg.wifi_password = "sim-password"
  return cfg


def _purge_firmware_modules():
  # enviro/__init__.py runs board detection etc at import time, so each
  # test re-imports the firmware with fresh state
  for name in list(sys.modules):
    if name in ("config", "main", "enviro") or name.startswith("enviro."):
      del sys.modules[name]


def _reset_sims():
  import machine, wakeup, breakout_bme280, breakout_ltr559, pcf85063a, urequests
  import phew
  simtime.clock.reset()
  machine.sim_reset()
  wakeup.sim_reset()
  breakout_bme280.sim_reset()
  breakout_ltr559.sim_reset()
  pcf85063a.sim_reset()
  urequests.sim_reset()
  phew.sim_reset()


@pytest.fixture
def sim(tmp_path, monkeypatch):
  """a freshly booted, simulated enviro grow board with an empty filesystem"""
  # the firmware writes files relative to cwd (readings/, uploads/,
  # last_time.txt, ...) so give each test its own directory
  monkeypatch.chdir(tmp_path)
  _purge_firmware_modules()
  _reset_sims()

  import machine, breakout_bme280, breakout_ltr559, urequests
  from phew import logging as phew_logging

  sys.modules["config"] = _build_config()

  import enviro

  return types.SimpleNamespace(
    enviro=enviro,
    board=enviro.get_board(),
    config=sys.modules["config"],
    machine=machine,
    clock=simtime.clock,
    bme280=breakout_bme280,
    ltr559=breakout_ltr559,
    urequests=urequests,
    logging=phew_logging,
  )


@pytest.fixture
def provisioning(tmp_path, monkeypatch):
  """an unprovisioned simulated grow board that has booted into provisioning
  mode: the captive portal routes are registered and can be driven with
  provisioning.server.sim_get() / sim_post()"""
  import shutil
  import importlib

  # lay out the parts of the device filesystem that provisioning reads
  # with cwd-relative paths (config template + captive portal html)
  (tmp_path / "enviro").mkdir()
  shutil.copy(ROOT / "enviro" / "config_template.py", tmp_path / "enviro" / "config_template.py")
  shutil.copytree(ROOT / "enviro" / "html", tmp_path / "enviro" / "html")

  monkeypatch.chdir(tmp_path)
  # provisioning generates config.py in cwd and imports it
  monkeypatch.syspath_prepend(str(tmp_path))
  _purge_firmware_modules()
  _reset_sims()
  importlib.invalidate_caches()

  # with no config module available the firmware boots straight into
  # provisioning mode and registers the captive portal routes
  import enviro
  import machine
  import phew
  from phew import server

  def read_config():
    # the settings a reboot would see, parsed from the generated config.py
    cfg = {}
    exec((tmp_path / "config.py").read_text(), cfg)
    return cfg

  return types.SimpleNamespace(
    enviro=enviro,
    server=server,
    phew=phew,
    machine=machine,
    read_config=read_config,
  )
