# virtual clock for the simulator
#
# every call to time.ticks_ms() advances the clock by 1ms and every call
# to time.sleep() advances it by the requested duration, so tests that
# exercise timing loops (moisture sensing, pump runs) complete instantly
# and deterministically. sleeps are recorded so tests can assert on pump
# run durations.

class Clock:
  def __init__(self):
    self.reset()

  def reset(self):
    self.now_ms = 0
    self.sleeps = []

  def ticks_ms(self):
    self.now_ms += 1
    return self.now_ms

  def peek_ms(self):
    # read the clock without advancing it (used by simulated pins)
    return self.now_ms

  def sleep(self, seconds):
    self.sleeps.append(seconds)
    self.now_ms += int(seconds * 1000)

  def sleep_ms(self, ms):
    self.sleep(ms / 1000)

clock = Clock()
