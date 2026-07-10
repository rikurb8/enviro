# simulated pcf85063a external rtc chip

class PCF85063A:
  CLOCK_OUT_OFF = 7
  CLOCK_OUT_1HZ = 6
  CLOCK_OUT_1024HZ = 3
  CLOCK_OUT_32768HZ = 0

  # (year, month, day, hour, minute, second, weekday)
  sim_datetime = (2026, 7, 10, 12, 0, 0, 4)
  sim_alarm = None
  sim_alarm_flag = True  # True so enviro.sleep()'s wait loop exits immediately
  sim_clock_output = None

  def __init__(self, i2c):
    pass

  def datetime(self, value=None):
    if value is None:
      return PCF85063A.sim_datetime
    PCF85063A.sim_datetime = tuple(value)[0:7]

  def enable_timer_interrupt(self, enabled):
    pass

  def enable_alarm_interrupt(self, enabled):
    pass

  def clear_timer_flag(self):
    pass

  def clear_alarm_flag(self):
    pass

  def read_alarm_flag(self):
    return PCF85063A.sim_alarm_flag

  def set_alarm(self, second, minute=None, hour=None, day=None):
    PCF85063A.sim_alarm = (second, minute, hour, day)

  def set_clock_output(self, mode):
    PCF85063A.sim_clock_output = mode

def sim_reset():
  PCF85063A.sim_datetime = (2026, 7, 10, 12, 0, 0, 4)
  PCF85063A.sim_alarm = None
  PCF85063A.sim_alarm_flag = True
  PCF85063A.sim_clock_output = None
