# tests for the grow board watering logic, running the real firmware code
# against simulated hardware

PUMP_A, PUMP_B, PUMP_C = 12, 11, 10
MOISTURE_A, MOISTURE_B, MOISTURE_C = 15, 14, 13
PIEZO = 28


def test_board_is_detected_as_grow(sim):
  assert sim.enviro.model == "grow"


def test_pump_runs_when_moisture_below_target(sim):
  sim.config.auto_water = True  # targets default to 50 for all channels
  sim.clock.sleeps.clear()

  sim.board.water([20.0, 50.0, 80.0])

  # channel a is 30 below target -> pump on, run (50 - 20) / 25 = 1.2s, off
  assert sim.machine.Pin.sim_writes(PUMP_A) == [1, 0]
  assert 1.2 in sim.clock.sleeps
  # channels b and c are at/above target -> pumps untouched
  assert sim.machine.Pin.sim_writes(PUMP_B) == []
  assert sim.machine.Pin.sim_writes(PUMP_C) == []


def test_beeps_instead_of_pumping_when_auto_water_disabled(sim):
  sim.config.auto_water = False

  sim.board.water([10.0, 10.0, 10.0])

  for pump in (PUMP_A, PUMP_B, PUMP_C):
    assert sim.machine.Pin.sim_writes(pump) == []
  # the piezo played the drip noise instead
  assert 32768 in sim.machine.PWM.sim_state(PIEZO)["duty_history"]


def test_full_sensor_reading_from_simulated_hardware(sim):
  sim.bme280.sim_reading = (24.0, 99800.0, 51.0)
  sim.ltr559.sim_lux = 321.0
  # moisture sensors emit one transition every n virtual ms
  # (20ms = bone dry, 80ms = standing in water)
  sim.machine.Pin.sim_set_tick_period(MOISTURE_A, 20)  # dry
  sim.machine.Pin.sim_set_tick_period(MOISTURE_B, 50)  # part way
  sim.machine.Pin.sim_set_tick_period(MOISTURE_C, 80)  # soaked

  reading = sim.board.get_sensor_readings(seconds_since_last=0, is_usb_power=False)

  assert reading["temperature"] == 24.0
  assert reading["pressure"] == 998.0
  assert reading["humidity"] == 51.0
  assert reading["luminance"] == 321.0
  assert reading["moisture_a"] == 0.0
  assert 30 < reading["moisture_b"] < 60
  assert reading["moisture_c"] > 80
