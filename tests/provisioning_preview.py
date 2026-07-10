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
import mimetypes
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simboot

# messages must show up even when output is piped
print = functools.partial(print, flush=True)


def boot_unprovisioned_board():
  workdir = Path(tempfile.mkdtemp(prefix="enviro-provisioning-"))
  simboot.layout_device_fs(workdir)
  os.chdir(workdir)
  sys.path.insert(0, str(workdir))
  simboot.purge_firmware_modules()
  simboot.reset_sims()
  # with no config module available the firmware boots straight into
  # provisioning mode and registers the captive portal routes
  import enviro  # noqa: F401
  return workdir


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
      "<p>The device would reset now. The generated <code>config.py</code> "
      f"(also printed to the terminal) is at <code>{self.workdir}/config.py</code>:</p>"
      f"<pre style='background:#eee;padding:1em'>{config}</pre>"
    ).encode()


def main():
  parser = argparse.ArgumentParser(description="preview the provisioning portal locally")
  parser.add_argument("--port", type=int, default=8080)
  args = parser.parse_args()

  workdir = boot_unprovisioned_board()
  from phew import server as phew_server
  import machine

  PortalBridge.phew_server = phew_server
  PortalBridge.machine = machine
  PortalBridge.workdir = workdir
  PortalBridge.base_url = f"http://localhost:{args.port}"

  print(f"\n> simulated device filesystem: {workdir}")
  print(f"> provisioning portal running at {PortalBridge.base_url} (ctrl+c to stop)\n")

  try:
    ThreadingHTTPServer(("localhost", args.port), PortalBridge).serve_forever()
  except KeyboardInterrupt:
    print("\n> stopped")


if __name__ == "__main__":
  main()
