# fake phew.logging - prints to stdout (pytest captures it) and keeps a
# record so tests can assert on logged messages

LOG_INFO = 0b00001
LOG_WARNING = 0b00010
LOG_ERROR = 0b00100
LOG_DEBUG = 0b01000
LOG_EXCEPTION = 0b10000
LOG_ALL = LOG_INFO | LOG_WARNING | LOG_ERROR | LOG_DEBUG | LOG_EXCEPTION

sim_entries = []

def sim_reset():
  sim_entries.clear()

def _log(level, *items):
  message = " ".join(str(item) for item in items)
  sim_entries.append((level, message))
  print(f"[{level}] {message}")

def debug(*items):
  _log("debug", *items)

def info(*items):
  _log("info", *items)

def warn(*items):
  _log("warning", *items)

def error(*items):
  _log("error", *items)

def exception(*items):
  _log("exception", *items)

def log(level, text):
  _log(level, text)

def set_truncate_thresholds(truncate_at, truncate_to):
  pass

def enable_logging_types(types):
  pass

def disable_logging_types(types):
  pass
