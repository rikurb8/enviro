from enviro import logging
from enviro.constants import UPLOAD_SUCCESS, UPLOAD_FAILED
import urequests
import config


def log_destination():
  logging.info(f"> uploading cached readings to url: {config.custom_http_url}")


def _auth():
  if config.custom_http_username:
    return (config.custom_http_username, config.custom_http_password)
  return None


def _send_ack(board, pending):
  if not pending or not pending.get("ack_url"):
    return False
  try:
    response = urequests.post(
      pending["ack_url"],
      auth=_auth(),
      json={"result": pending["result"]}
    )
    success = response.status_code in [200, 201, 202]
    response.close()
    if success:
      board.clear_watering_ack(pending["id"])
      logging.info(f"  - acknowledged watering command {pending['id']}")
    return success
  except Exception as exc:
    logging.debug(f"  - watering acknowledgement failed: {exc}")
    return False


def _handle_watering_response(response):
  from enviro import get_board
  board = get_board()
  if not hasattr(board, "execute_remote_watering"):
    return

  try:
    body = response.json()
  except (ValueError, AttributeError):
    return
  if not isinstance(body, dict):
    return

  command = body.get("watering_command")
  if not isinstance(command, dict):
    return

  result = board.execute_remote_watering(command)
  command_id = command.get("id")
  ack_url = command.get("ack_url")
  if command_id and ack_url:
    board.set_watering_ack(command_id, ack_url, result)
    _send_ack(board, board.pending_watering_ack())


def upload_reading(reading):
  url = config.custom_http_url

  try:
    from enviro import get_board
    board = get_board()
    if hasattr(board, "pending_watering_ack"):
      _send_ack(board, board.pending_watering_ack())

    result = urequests.post(url, auth=_auth(), json=reading)
    if result.status_code in [200, 201, 202]:
      _handle_watering_response(result)
      result.close()
      return UPLOAD_SUCCESS

    logging.debug(f"  - upload issue ({result.status_code} {result.reason})")
    result.close()
  except Exception as exc:
    logging.debug(f"  - an exception occurred when uploading: {exc}")

  return UPLOAD_FAILED
