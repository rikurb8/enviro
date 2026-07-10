# fake phew.server - registers routes instead of running a web server, and
# lets tests drive the handlers directly with sim_get()/sim_post()

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

sim_routes = {}
sim_catchall_handler = None
sim_runs = []

def sim_reset():
  global sim_catchall_handler
  sim_routes.clear()
  sim_catchall_handler = None
  sim_runs.clear()


class Response:
  def __init__(self, body="", status=200, headers=None):
    self.body = body
    self.status = status
    self.headers = headers or {}


class RenderedTemplate(str):
  # behaves like the rendered html string, but also remembers which
  # template produced it so tests can assert on that instead of markup
  def __new__(cls, content, template, params):
    self = super().__new__(cls, content)
    self.template = template
    self.params = params
    return self


class SimRequest:
  def __init__(self, method="GET", path="/", form=None, headers=None, query=None):
    self.method = method
    self.path = path
    self.form = form or {}
    self.headers = headers or {}
    self.query = query or {}
    self.query_string = ""
    self.data = {}


def route(path, methods=["GET"]):
  def _decorator(handler):
    sim_routes[path] = handler
    return handler
  return _decorator

def catchall():
  def _decorator(handler):
    global sim_catchall_handler
    sim_catchall_handler = handler
    return handler
  return _decorator

def run(host="0.0.0.0", port=80):
  # on the device this blocks forever serving requests; in the simulator
  # it returns immediately and tests invoke the handlers themselves
  sim_runs.append((host, port))

def redirect(url, status=302):
  return Response("", status, {"Location": url})

def serve_file(file):
  with open(_resolve(file), "rb") as f:
    return Response(f.read())

def render_template(template, **params):
  # like real phew, {{...}} blocks are python expressions evaluated with
  # the template parameters in scope. anything that fails evaluates to ""
  with open(_resolve(template)) as f:
    content = f.read()

  def _evaluate(match):
    try:
      scope = {"render_template": render_template}
      scope.update(params)
      return str(eval(match.group(1), scope))
    except Exception:
      return ""

  content = re.sub(r"{{(.*?)}}", _evaluate, content, flags=re.DOTALL)
  return RenderedTemplate(content, template, params)

def _resolve(path):
  # device paths are cwd-relative; fall back to the repo checkout so
  # templates resolve even if a test didn't copy enviro/html into its cwd
  if os.path.exists(path):
    return path
  return str(_REPO_ROOT / path)


# --- simulator helpers: drive the captive portal like a browser would ------
def sim_request(path, method="GET", form=None, headers=None):
  if headers is None:
    headers = {"host": "pico.wireless"}
  request = SimRequest(method=method, path=path, form=form, headers=headers)
  handler = sim_routes.get(path, sim_catchall_handler)
  if handler is None:
    raise AssertionError(f"no route or catchall registered for {path}")
  return handler(request)

def sim_get(path, headers=None):
  return sim_request(path, "GET", headers=headers)

def sim_post(path, form=None):
  return sim_request(path, "POST", form=form)
