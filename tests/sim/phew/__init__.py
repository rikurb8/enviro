# minimal fake of the phew library (real one is a git submodule targeting
# micropython) - enviro only uses logging, ntp and the remote_mount flag

remote_mount = False

from . import logging
