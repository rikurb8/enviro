import config
from phew import logging

DEFAULT_USB_POWER_TEMPERATURE_OFFSET = 4.5
DEFAULT_REMOTE_WATERING_MAX_ML = 100
DEFAULT_REMOTE_WATERING_MAX_SECONDS = 60


def add_missing_config_settings():
  try:
    # check if ca file parameter is set, if not set it to not use SSL by setting to None
    config.mqtt_broker_ca_file
  except AttributeError:
    warn_missing_config_setting("mqtt_broker_ca_file")
    config.mqtt_broker_ca_file = None

  try:
    config.usb_power_temperature_offset
  except AttributeError:
    warn_missing_config_setting("usb_power_temperature_offset")
    config.usb_power_temperature_offset = DEFAULT_USB_POWER_TEMPERATURE_OFFSET

  try:
    config.wifi_country
  except AttributeError:
    warn_missing_config_setting("wifi_country")
    config.wifi_country = "GB"

  try:
    config.provisioning_call_home_url
  except AttributeError:
    warn_missing_config_setting("provisioning_call_home_url")
    config.provisioning_call_home_url = None

  defaults = {
    "pump_ml_per_second": None,
    "pump_ml_per_second_a": None,
    "pump_ml_per_second_b": None,
    "pump_ml_per_second_c": None,
    "remote_watering_max_ml": DEFAULT_REMOTE_WATERING_MAX_ML,
    "remote_watering_max_seconds": DEFAULT_REMOTE_WATERING_MAX_SECONDS,
  }
  for setting, default in defaults.items():
    if not hasattr(config, setting):
      warn_missing_config_setting(setting)
      setattr(config, setting, default)

def warn_missing_config_setting(setting):
    logging.warn(f"> config setting '{setting}' missing, please add it to config.py")
