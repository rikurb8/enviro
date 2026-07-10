# simulated urequests module
#
# tests queue up responses with sim_queue_response() and inspect what the
# firmware sent via sim_requests. this is the main hook for testing
# "call home" behaviour: queue a response whose body contains watering
# commands and assert the firmware acts on it.

sim_requests = []       # list of dicts: method, url, kwargs
sim_responses = []      # queue of SimResponse to hand out (fifo)
sim_default_status = 200

def sim_reset():
  global sim_default_status
  sim_requests.clear()
  sim_responses.clear()
  sim_default_status = 200

def sim_queue_response(status_code=200, text="", json=None, reason=""):
  sim_responses.append(SimResponse(status_code, text, json, reason))

class SimResponse:
  def __init__(self, status_code=200, text="", json=None, reason=""):
    self.status_code = status_code
    self.text = text
    self.reason = reason
    self._json = json

  def json(self):
    import ujson
    if self._json is not None:
      return self._json
    return ujson.loads(self.text)

  def close(self):
    pass

def _request(method, url, **kwargs):
  sim_requests.append({"method": method, "url": url, **kwargs})
  if sim_responses:
    return sim_responses.pop(0)
  return SimResponse(sim_default_status)

def get(url, **kwargs):
  return _request("GET", url, **kwargs)

def post(url, **kwargs):
  return _request("POST", url, **kwargs)

def put(url, **kwargs):
  return _request("PUT", url, **kwargs)
