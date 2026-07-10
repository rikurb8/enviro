# simulated bme280 temperature/pressure/humidity sensor

# (temperature in c, pressure in pa, humidity in %)
sim_reading = (22.5, 101325.0, 45.0)

def sim_reset():
  global sim_reading
  sim_reading = (22.5, 101325.0, 45.0)

class BreakoutBME280:
  def __init__(self, i2c, address=0x76):
    pass

  def read(self):
    return sim_reading
