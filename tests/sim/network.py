# simulated network module - wifi always connects instantly

STA_IF = 0
AP_IF = 1

def hostname(name=None):
  pass

class WLAN:
  # CYW43_LINK_UP
  sim_status = 3

  def __init__(self, interface=STA_IF):
    pass

  def active(self, state=None):
    if state is None:
      return True

  def status(self):
    return WLAN.sim_status

  def config(self, key=None, **kwargs):
    if key == "mac":
      return b"\xde\xad\xbe\xef\x00\x01"

  def connect(self, ssid, password):
    pass

  def disconnect(self):
    pass

  def ifconfig(self):
    return ("192.168.1.42", "255.255.255.0", "192.168.1.1", "192.168.1.1")

  def isconnected(self):
    return WLAN.sim_status == 3
