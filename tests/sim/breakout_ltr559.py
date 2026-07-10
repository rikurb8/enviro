# simulated ltr559 light/proximity sensor

sim_lux = 400.0
sim_proximity = 0

def sim_reset():
  global sim_lux, sim_proximity
  sim_lux = 400.0
  sim_proximity = 0

class BreakoutLTR559:
  LUX = 0
  PROXIMITY = 1

  def __init__(self, i2c):
    pass

  def get_reading(self):
    return [sim_lux, sim_proximity]
