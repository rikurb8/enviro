# tests for enviro/helpers.py


def test_mkdir_safe_is_idempotent(sim):
  # regression: mkdir_safe used errno without importing it, so any call
  # with an already-existing directory (e.g. the second local reading of
  # the day creating "readings/") raised NameError
  sim.enviro.helpers.mkdir_safe("some_dir")
  sim.enviro.helpers.mkdir_safe("some_dir")
