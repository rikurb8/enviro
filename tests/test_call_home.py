# tests for the upload / call-home flow, running the real firmware code
# with a fake urequests so no network is involved
#
# this is the place to test a custom "call home controls the watering"
# destination: queue a response carrying watering commands with
# sim.urequests.sim_queue_response(json={...}) and assert the firmware
# acts on it (e.g. pump pins via sim.machine.Pin.sim_writes)
#
# note: don't import enviro (or enviro.*) at module level - importing the
# package boots the firmware, which must happen inside the sim fixture


def test_reading_is_cached_then_uploaded_over_http(sim):
  sim.config.destination = "http"
  sim.config.custom_http_url = "http://example.com/enviro"
  sim.config.upload_frequency = 1

  reading = {"temperature": 21.0, "moisture_a": 30.0}
  sim.enviro.cache_upload(reading)
  assert sim.enviro.cached_upload_count() == 1
  assert sim.enviro.is_upload_needed()

  sim.urequests.sim_queue_response(status_code=200)
  assert sim.enviro.upload_readings() is True
  assert sim.enviro.cached_upload_count() == 0

  request = sim.urequests.sim_requests[0]
  assert request["method"] == "POST"
  assert request["url"] == "http://example.com/enviro"
  assert request["json"]["readings"] == reading
  assert request["json"]["model"] == "grow"
  assert request["json"]["nickname"] == "simulator"


def test_failed_upload_keeps_the_cached_reading(sim):
  sim.config.destination = "http"
  sim.config.custom_http_url = "http://example.com/enviro"

  sim.enviro.cache_upload({"temperature": 21.0})

  sim.urequests.sim_queue_response(status_code=500)
  assert sim.enviro.upload_readings() is False
  assert sim.enviro.cached_upload_count() == 1
