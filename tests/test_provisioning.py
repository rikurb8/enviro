# tests for the provisioning flow (captive portal), driving the real
# enviro/provisioning.py handlers through the fake phew server
#
# note: don't import enviro (or enviro.*) at module level - importing the
# package boots the firmware, which must happen inside the fixture

import pytest


def test_boots_into_provisioning_when_unconfigured(provisioning):
  # an access point was brought up with the board type in its name
  assert provisioning.phew.sim_access_points[0].ssid == "Enviro Grow Setup"
  # the web server was started
  assert provisioning.server.sim_runs == [("0.0.0.0", 80)]
  # and a fresh config.py was generated from the template
  assert provisioning.read_config()["provisioned"] is False


def test_welcome_page_renders_for_grow(provisioning):
  page = provisioning.server.sim_get("/provision-welcome")
  assert page.template == "enviro/html/welcome.html"
  assert "Enviro Grow" in page


def test_full_provisioning_flow_writes_config(provisioning):
  server = provisioning.server

  response = server.sim_post("/provision-step-1-nickname", {"nickname": "kitchen-grow"})
  assert response.headers["Location"].endswith("/provision-step-2-wifi")

  response = server.sim_post("/provision-step-2-wifi", {
    "wifi_ssid": "HomeWifi", "wifi_password": "hunter2"})
  assert response.headers["Location"].endswith("/provision-step-3-logging")

  response = server.sim_post("/provision-step-3-logging", {
    "reading_frequency": "15", "upload_frequency": "5"})
  assert response.headers["Location"].endswith("/provision-step-4-destination")

  response = server.sim_post("/provision-step-4-destination", {
    "destination": "http",
    "custom_http_url": "http://example.com/enviro",
    "custom_http_username": "", "custom_http_password": "",
    "mqtt_broker_address": "", "mqtt_broker_username": "", "mqtt_broker_password": "",
    "adafruit_io_username": "", "adafruit_io_key": "",
    "influxdb_org": "", "influxdb_url": "", "influxdb_token": "", "influxdb_bucket": ""})
  # grow boards get the extra sensors step
  assert response.headers["Location"].endswith("/provision-step-grow-sensors")

  response = server.sim_post("/provision-step-grow-sensors", {
    "auto_water": "True",
    "moisture_target_a": "60",
    "moisture_target_b": "55",
    "moisture_target_c": ""})  # left blank -> keeps template default
  assert response.headers["Location"].endswith("/provision-step-5-done")

  server.sim_get("/provision-step-5-done")

  # config.py now contains everything the next boot needs
  cfg = provisioning.read_config()
  assert cfg["provisioned"] is True
  assert cfg["nickname"] == "kitchen-grow"
  assert cfg["wifi_ssid"] == "HomeWifi"
  assert cfg["wifi_password"] == "hunter2"
  assert cfg["reading_frequency"] == 15
  assert cfg["upload_frequency"] == 5
  assert cfg["destination"] == "http"
  assert cfg["custom_http_url"] == "http://example.com/enviro"
  assert cfg["auto_water"] is True
  assert cfg["moisture_target_a"] == 60
  assert cfg["moisture_target_b"] == 55
  assert cfg["moisture_target_c"] == 50


def test_finishing_provisioning_resets_the_board(provisioning):
  with pytest.raises(provisioning.machine.SimulatedReset):
    provisioning.server.sim_post("/provision-step-5-done", {})
  # provisioned flag was written before the reset
  assert provisioning.read_config()["provisioned"] is True


def test_networks_json_lists_visible_ssids(provisioning):
  provisioning.phew.SimAccessPoint.sim_networks = [b"HomeWifi", b"HomeWifi", b"Attic"]
  body, status, content_type = provisioning.server.sim_get("/networks.json")
  assert status == 200
  assert content_type == "application/json"
  import json
  assert sorted(json.loads(body)) == ["Attic", "HomeWifi"]  # deduplicated


def test_captive_portal_redirects_other_hosts(provisioning):
  response = provisioning.server.sim_get(
    "/generate_204", headers={"host": "connectivitycheck.gstatic.com"})
  assert response.status == 302
  assert response.headers["Location"] == "http://pico.wireless/wrong-host-redirect"


def test_catchall_serves_static_files(provisioning):
  response = provisioning.server.sim_get("/footer.html")
  assert response.status == 200
  assert len(response.body) > 0
