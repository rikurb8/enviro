# pytest testbench for the enviro firmware
#
# runs the real firmware code under desktop cpython by shadowing all the
# micropython/hardware modules (machine, pimoroni_i2c, phew, urequests, ...)
# with the fakes in tests/sim. time is virtual: sleeps and ticks_ms are
# instant and deterministic. see tests/README.md.

import importlib
import sys
import types

import pytest

import simboot  # side effects: sim modules on sys.path + micropython shims
from simboot import ROOT
import simtime


@pytest.fixture
def sim(tmp_path, monkeypatch):
  """a freshly booted, simulated enviro grow board with an empty filesystem"""
  # the firmware writes files relative to cwd (readings/, uploads/,
  # last_time.txt, ...) so give each test its own directory
  monkeypatch.chdir(tmp_path)
  simboot.purge_firmware_modules()
  simboot.reset_sims()

  import machine, breakout_bme280, breakout_ltr559, urequests
  from phew import logging as phew_logging

  sys.modules["config"] = simboot.build_config()

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
  simboot.layout_device_fs(tmp_path)

  monkeypatch.chdir(tmp_path)
  # provisioning generates config.py in cwd and imports it
  monkeypatch.syspath_prepend(str(tmp_path))
  simboot.purge_firmware_modules()
  simboot.reset_sims()
  importlib.invalidate_caches()

  # with no config module available the firmware boots straight into
  # provisioning mode and registers the captive portal routes
  import enviro
  import machine
  import phew
  import urequests
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
    config=sys.modules["config"],
    urequests=urequests,
    read_config=read_config,
  )
