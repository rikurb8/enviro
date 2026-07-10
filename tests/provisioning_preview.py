#!/usr/bin/env python3
# preview the enviro provisioning captive portal in a local browser
#
#   uv run tests/provisioning_preview.py [--port 8080]
#   (or: python3 tests/provisioning_preview.py - no dependencies needed)
#
# boots an unprovisioned simulated grow board (same fakes as the test
# suite) and bridges the captive portal routes onto a real local http
# server, so your browser plays the phone that connects to the board's
# access point. walking through the portal writes a real config.py into
# a temp directory; finishing the flow shows it instead of resetting.

import argparse
import functools
import json
import mimetypes
import os
import sys
import tempfile
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simboot

# messages must show up even when output is piped
print = functools.partial(print, flush=True)


def boot_unprovisioned_board(call_home_url):
  workdir = Path(tempfile.mkdtemp(prefix="enviro-provisioning-"))
  simboot.layout_device_fs(workdir)
  os.chdir(workdir)
  sys.path.insert(0, str(workdir))
  simboot.purge_firmware_modules()
  simboot.reset_sims()
  # with no config module available the firmware boots straight into
  # provisioning mode and registers the captive portal routes
  import enviro  # noqa: F401
  import config
  # Pre-fill the real provisioning form so completing it appears in the
  # dashboard without needing a physical board.
  config.provisioning_call_home_url = call_home_url
  return workdir


def forward_simulated_requests():
  """Make the preview's fake device HTTP client send call-home requests."""
  import urequests
  simulated_post = urequests.post

  class Response:
    def __init__(self, status_code):
      self.status_code = status_code

    def close(self):
      pass

  def post(url, **kwargs):
    # Keep the fake's request log useful when debugging the simulator.
    simulated_post(url, **kwargs)
    payload = json.dumps(kwargs.get("json", {})).encode()
    request = urllib.request.Request(
      url, data=payload, method="POST",
      headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
      return Response(response.status)

  urequests.post = post


class PortalBridge(BaseHTTPRequestHandler):
  phew_server = None
  machine = None
  workdir = None
  base_url = None

  def do_GET(self):
    self._bridge("GET")

  def do_POST(self):
    self._bridge("POST")

  def _bridge(self, method):
    path = urlparse(self.path).path
    if path == "/":
      self._respond(302, b"", "text/html", {"Location": "/provision-welcome"})
      return

    form = {}
    if method == "POST":
      length = int(self.headers.get("Content-Length", 0))
      body = self.rfile.read(length).decode()
      form = {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}

    try:
      # the device only answers on its captive portal domain, so present
      # every request as if it came from there
      result = self.phew_server.sim_request(path, method, form=form,
                                            headers={"host": "pico.wireless"})
    except self.machine.SimulatedReset:
      self._respond(200, self._completion_page(), "text/html")
      return

    self._respond(*self._normalise(path, result))

  def _normalise(self, path, result):
    if isinstance(result, tuple):  # e.g. networks.json: (body, status, content_type)
      body, status, content_type = (result + (200, "text/html"))[:3]
    elif isinstance(result, self.phew_server.Response):
      location = result.headers.get("Location")
      if location:
        # the browser can't resolve the captive portal domain - send it
        # back to this local server instead
        location = location.replace("http://pico.wireless", self.base_url)
        return (result.status, b"", "text/html", {"Location": location})
      body, status = result.body, result.status
      content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    else:  # plain string / rendered template
      body, status, content_type = result, 200, "text/html"

    if isinstance(body, str):
      body = body.encode()
    return (status, body, content_type, {})

  def _respond(self, status, body, content_type, extra_headers=None):
    self.send_response(status)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    for key, value in (extra_headers or {}).items():
      self.send_header(key, value)
    self.end_headers()
    self.wfile.write(body)

  def _completion_page(self):
    config = (self.workdir / "config.py").read_text()
    print("\n> board reset - provisioning complete! generated config.py:\n")
    print(config)
    return (
      "<h1>&#127881; Provisioning complete</h1>"
      "<p>The device would reset now. It attempted to send its provisioning event to the "
      f"<a href='{self.dashboard_url}'>local dashboard</a>. The generated "
      "<code>config.py</code> (also printed to the terminal) is at "
      f"<code>{self.workdir}/config.py</code>:</p>"
      f"<pre style='background:#eee;padding:1em'>{config}</pre>"
    ).encode()


def main():
  parser = argparse.ArgumentParser(description="preview the provisioning portal locally")
  parser.add_argument("--port", type=int, default=8080)
  parser.add_argument("--dashboard-url", default="http://localhost:5001",
                      help="local dashboard URL (default: %(default)s)")
  args = parser.parse_args()
  dashboard_url = args.dashboard_url.rstrip("/")
  call_home_url = f"{dashboard_url}/api/provisioned"

  workdir = boot_unprovisioned_board(call_home_url)
  forward_simulated_requests()
  from phew import server as phew_server
  import machine

  PortalBridge.phew_server = phew_server
  PortalBridge.machine = machine
  PortalBridge.workdir = workdir
  PortalBridge.base_url = f"http://localhost:{args.port}"
  PortalBridge.dashboard_url = dashboard_url

  print(f"\n> simulated device filesystem: {workdir}")
  print(f"> provisioning portal running at {PortalBridge.base_url}")
  print(f"> call-home will be sent to {call_home_url} (start `task server` first; ctrl+c to stop)\n")

  try:
    ThreadingHTTPServer(("localhost", args.port), PortalBridge).serve_forever()
  except KeyboardInterrupt:
    print("\n> stopped")


if __name__ == "__main__":
  main()
