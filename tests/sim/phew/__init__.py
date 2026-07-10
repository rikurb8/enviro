# minimal fake of the phew library (real one is a git submodule targeting
# micropython) - covers what enviro uses: logging, ntp, remote_mount and
# the captive portal pieces (server, access_point, dns)

remote_mount = False

from . import logging
from . import server
from .server import redirect, serve_file, render_template


class SimAccessPoint:
  # wifi networks visible to the board (as scan() ssid entries)
  sim_networks = [b"HomeWifi", b"CoffeeShop"]
  # a client is "connected" from the start so provisioning's wait loop exits
  sim_stations = [(b"\xde\xad\xbe\xef\xf0\x0d",)]

  def __init__(self, ssid, password=None):
    self.ssid = ssid

  def ifconfig(self):
    return ("192.168.4.1", "255.255.255.0", "192.168.4.1", "192.168.4.1")

  def status(self, key=None):
    if key == "stations":
      return list(SimAccessPoint.sim_stations)
    return None

  def scan(self):
    return [(ssid, 11, -50, 4, 5, False) for ssid in SimAccessPoint.sim_networks]


sim_access_points = []

def access_point(ssid, password=None):
  ap = SimAccessPoint(ssid, password)
  sim_access_points.append(ap)
  return ap


def sim_reset():
  logging.sim_reset()
  server.sim_reset()
  sim_access_points.clear()
  SimAccessPoint.sim_networks = [b"HomeWifi", b"CoffeeShop"]
  SimAccessPoint.sim_stations = [(b"\xde\xad\xbe\xef\xf0\x0d",)]
