"""Module to handle launching a URL no matter the environment."""

import os
import pwd
import subprocess
import sys
import webbrowser

# DO NOT MERGE
# import utmp

X11_SOCKET_DIR = '/tmp/.X11-unix'
XAUTHORITY = '.Xauthority'
UTMP = '/var/run/utmp'


def _get_running_display():
  sockets = os.listdir(X11_SOCKET_DIR)
  if not sockets:
    raise ValueError('No running X11 display.')
  if len(sockets) > 1:
    raise ValueError(
        'Multiple X11 displays to choose from. Set DISPLAY to clarify: '
        '%s' % sockets)
  return sockets[0].replace('X', ':')


def _get_display_owner(display):
  # DO NOT MERGE
  # for entry in utmp.UtmpFile():
  #   if entry.ut_host == display:
  #     return entry.ut_user
  raise ValueError('Cannot detect X11 owner from %s' % UTMP)


def launch(url):
  """Launches the given URL even when run as root."""
  if os.environ.get('DISPLAY') is not None:
    webbrowser.open(url)
    return

  # No DISPLAY specified, so we have to find one.
  env = os.environ.copy()
  display = _get_running_display()
  env['DISPLAY'] = display
  # Then we have to assume their .Xauthority file, which by default is in
  # their home directory. If it's not, we don't support the system.
  owner = _get_display_owner(display)
  pwd_info = pwd.getpwnam(owner)
  if os.getuid() != pwd_info.pw_uid and os.getuid() != 0:
    # If we have to switch users and we're not running as root, then we're
    # going to have different errors later so raise something obvious now.
    raise ValueError(
        'Cannot run as non-root without DISPLAY set. Either set DISPLAY or '
        'run as root.')

  env['HOME'] = pwd_info.pw_dir
  xauth_path = os.path.join(pwd_info.pw_dir, XAUTHORITY)
  if not os.path.exists(xauth_path):
    raise ValueError(
        'This system is unsupported. %s does not exist' % xauth_path)

  env['XAUTHORITY'] = xauth_path
  # We can't use the webbrowser module because, if we're running as root,
  # we need to provide a custom preexec_fn that fixes that.
  def demote():
    os.setsid()
    os.setgid(pwd_info.pw_gid)
    os.setuid(pwd_info.pw_uid)
  # We assume google-chrome exists here. If it doesn't, this raises an OSError.
  popen = subprocess.Popen(
      ['google-chrome', url], close_fds=True, preexec_fn=demote, env=env)
  popen.poll()


if __name__ == '__main__':
  launch(sys.argv[1])
