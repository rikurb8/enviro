# fake phew.ntp

# (year, month, day, hour, minute, second, weekday, yearday)
sim_timestamp = (2026, 7, 10, 12, 0, 0, 4, 191)

def fetch(synch_with_rtc=True, timeout=10):
  return sim_timestamp
