# simulated i2c bus
#
# the devices present on the bus determine which board enviro detects:
#   56 -> indoor, 35 -> grow/weather (grow if pin 12 reads low), else urban
# default is a grow board (ltr559 + rtc + bme280)

sim_devices = [0x23, 0x51, 0x77]  # 0x23 = 35 = ltr559

class PimoroniI2C:
  def __init__(self, sda, scl, baudrate=100000):
    pass

  def scan(self):
    return list(sim_devices)

  def writeto_mem(self, addr, memaddr, buf):
    pass

  def readfrom_mem(self, addr, memaddr, nbytes):
    return bytes(nbytes)
