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


def test_reading_response_executes_and_acknowledges_watering_command(sim):
  sim.config.destination = "http"
  sim.config.custom_http_url = "http://server/api/readings"
  sim.config.upload_frequency = 1
  sim.config.pump_ml_per_second = 2.0
  sim.config.pump_ml_per_second_a = 4.0
  sim.enviro.cache_upload({"moisture_a": 60.0})

  sim.urequests.sim_queue_response(json={
    "watering_command": {
      "id": "command-1",
      "amounts": {"A": 20, "C": 10},
      "ack_url": "http://server/api/watering-commands/command-1/ack",
    }
  })
  sim.urequests.sim_queue_response(status_code=200)

  assert sim.enviro.upload_readings() is True
  assert sim.machine.Pin.sim_writes(12) == [1, 0]
  assert sim.machine.Pin.sim_writes(10) == [1, 0]
  assert 5.0 in sim.clock.sleeps  # channel A override
  assert 5.0 in sim.clock.sleeps  # channel C shared rate
  assert sim.urequests.sim_requests[1]["json"]["result"]["status"] == "completed"
  assert sim.board.pending_watering_ack() is None


def test_failed_watering_ack_is_retried_before_next_upload(sim):
  sim.config.destination = "http"
  sim.config.custom_http_url = "http://server/api/readings"
  sim.config.upload_frequency = 1
  sim.config.pump_ml_per_second = 2.0
  sim.enviro.cache_upload({"moisture_a": 60.0})
  sim.urequests.sim_queue_response(json={
    "watering_command": {
      "id": "retry-command",
      "amounts": {"A": 10},
      "ack_url": "http://server/ack/retry-command",
    }
  })
  sim.urequests.sim_queue_response(status_code=500)

  assert sim.enviro.upload_readings() is True
  assert sim.board.pending_watering_ack()["id"] == "retry-command"

  sim.enviro.cache_upload({"moisture_a": 61.0})
  sim.urequests.sim_queue_response(status_code=200)  # acknowledgement retry
  sim.urequests.sim_queue_response(status_code=201)  # reading upload
  assert sim.enviro.upload_readings() is True
  assert sim.board.pending_watering_ack() is None
  assert sim.machine.Pin.sim_writes(12) == [1, 0]


def test_duplicate_watering_command_is_not_executed_twice(sim):
  sim.config.pump_ml_per_second = 2.0
  command = {"id": "same-command", "amounts": {"B": 10}}

  first = sim.board.execute_remote_watering(command)
  second = sim.board.execute_remote_watering(command)

  assert first["status"] == second["status"] == "completed"
  assert sim.machine.Pin.sim_writes(11) == [1, 0]


def test_watering_command_rejects_unsafe_amount_before_running_pumps(sim):
  sim.config.pump_ml_per_second = 2.0

  result = sim.board.execute_remote_watering({
    "id": "unsafe-command", "amounts": {"A": 10, "B": 101}})

  assert result["status"] == "rejected"
  assert "allowed range" in result["error"]
  assert sim.machine.Pin.sim_writes(12) == []
  assert sim.machine.Pin.sim_writes(11) == []


def test_failed_upload_keeps_the_cached_reading(sim):
  sim.config.destination = "http"
  sim.config.custom_http_url = "http://example.com/enviro"

  sim.enviro.cache_upload({"temperature": 21.0})

  sim.urequests.sim_queue_response(status_code=500)
  assert sim.enviro.upload_readings() is False
  assert sim.enviro.cached_upload_count() == 1
