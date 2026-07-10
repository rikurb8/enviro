# simulated wakeup module - reports which gpios were high at boot

sim_gpio_state = 0

def sim_reset():
  global sim_gpio_state
  sim_gpio_state = 0

def get_gpio_state():
  return sim_gpio_state

def get_shift_state():
  return 0
