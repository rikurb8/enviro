# simulated machine module (MicroPython hardware API)
import simtime

class Pin:
  IN = 0
  OUT = 1
  OPEN_DRAIN = 2
  PULL_UP = 1
  PULL_DOWN = 2

  # shared state per pin id so every Pin(12) sees the same simulated pin
  _states = {}

  def __init__(self, id, mode=-1, pull=None, value=None):
    self.id = id
    state = Pin._states.setdefault(id, {"value": 0, "writes": [], "tick_period_ms": None})
    if value is not None:
      state["value"] = value

  def init(self, mode=-1, pull=None, value=None):
    if value is not None:
      Pin._states[self.id]["value"] = value

  def value(self, x=None):
    state = Pin._states[self.id]
    if x is None:
      if state["tick_period_ms"]:
        # simulate a square wave (used by the grow moisture sensors)
        return (simtime.clock.peek_ms() // state["tick_period_ms"]) % 2
      return state["value"]
    state["value"] = x
    state["writes"].append(x)

  def on(self):
    self.value(1)

  def off(self):
    self.value(0)

  # --- simulator helpers -----------------------------------------------
  @classmethod
  def sim_state(cls, id):
    return cls._states.setdefault(id, {"value": 0, "writes": [], "tick_period_ms": None})

  @classmethod
  def sim_set_value(cls, id, value):
    cls.sim_state(id)["value"] = value

  @classmethod
  def sim_set_tick_period(cls, id, period_ms):
    # make the pin oscillate like a moisture sensor: one transition
    # every period_ms of (virtual) time
    cls.sim_state(id)["tick_period_ms"] = period_ms

  @classmethod
  def sim_writes(cls, id):
    return cls.sim_state(id)["writes"]


class PWM:
  _states = {}

  def __init__(self, pin):
    self.id = pin.id if isinstance(pin, Pin) else pin
    PWM._states.setdefault(self.id, {"freq": None, "duty_history": []})

  def freq(self, f=None):
    if f is None:
      return PWM._states[self.id]["freq"]
    PWM._states[self.id]["freq"] = f

  def duty_u16(self, duty=None):
    history = PWM._states[self.id]["duty_history"]
    if duty is None:
      return history[-1] if history else 0
    history.append(duty)

  @classmethod
  def sim_state(cls, id):
    return cls._states.setdefault(id, {"freq": None, "duty_history": []})


class Timer:
  ONE_SHOT = 0
  PERIODIC = 1

  def __init__(self, id=-1):
    pass

  # callbacks are not executed in the simulator (only used for the
  # activity led animation)
  def init(self, mode=PERIODIC, period=-1, callback=None):
    pass

  def deinit(self):
    pass


class RTC:
  # 8-tuple: (year, month, day, weekday, hour, minute, second, subsecond)
  _datetime = (2026, 7, 10, 4, 12, 0, 0, 0)

  def datetime(self, value=None):
    if value is None:
      return RTC._datetime
    RTC._datetime = tuple(value)


class ADC:
  def __init__(self, pin):
    pass

  def read_u16(self):
    return 30000


class SimulatedReset(Exception):
  # raised instead of resetting the board so tests regain control
  pass


def reset():
  raise SimulatedReset()

def unique_id():
  return b"\x01\x02\x03\x04\x05\x06\x07\x08"

def freq(*args):
  return 133000000


def sim_reset():
  Pin._states.clear()
  PWM._states.clear()
  RTC._datetime = (2026, 7, 10, 4, 12, 0, 0, 0)
