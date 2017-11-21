# Copyright 2017 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Classes for controlling Frontline bluetooth sniffers.

This module provides control over a variety of Frontline (now owned by Teledyne
Lecroy) bluetooth sniffers. For full details on Frontline's sniffer control
protocol, which this module partially implements, see the reference document:

http://www.fte.com/docs/usermanuals/comprobe%20automation%20server%20protocol.pdf
"""

# TODO: Remove references to a81c.files module and a81c.util module.

import argparse
import contextlib
import datetime
import logging
import os
import socket
import time

DEFAULT_AUTOMATION_PORT = 22901
DEFAULT_HTTP_PORT = 55455
REMOTE_BIN_PATH = (r'C:\Program Files (x86)\Frontline Test System II'
                   r'\Frontline\Executables\Core')
REMOTE_LOG_PATH = r'C:\ble_logs'
VERSION = 'SNIFF00'

_LOG = logging.getLogger(__name__)


class SnifferError(Exception):
  """Raised when a BLE sniffer command fails."""
  def __init__(self, command, response):
    super(SnifferError, self).__init__(
        'Command "{}" failed with response "{}"'.format(command, response))
    self.response = response


class Sniffer(object):
  """Class for controlling a Frontline bluetooth sniffer via Telnet.

  Args:
    host: Hostname or IP address of the sniffer's automation server.
    port: TCP port fort the sniffer's automation server.
    log_path: Path on the sniffer's automation server at which to save logs.
  """
  def __init__(self,
               host='localhost',
               port=DEFAULT_AUTOMATION_PORT,
               log_path=REMOTE_LOG_PATH):
    self._address = host, port
    self._log_path = log_path

    self.capture_id = None
    self.capture_start_time = None
    self._files = []
    self._socket = None

  def _connect(self):
    """Open a connection to the sniffer's automation server."""
    _LOG.info('Connecting to sniffer server at %s:%d', *self._address)
    assert self._socket is None
    self._socket = socket.create_connection(self._address, 10)

    _LOG.info('Stopping any previously running sniffer captures')
    self._socket.settimeout(16)
    try:
      self._sniffer_command('Stop FTS')
    except (SnifferError, socket.timeout):
      pass

    self._socket.settimeout(None)

  def _sniffer_command(self, command, *args):
    """Send command to the sniffer's automation server and wait for response."""
    full_command = ';'.join((command,) + args)
    _LOG.debug('Sniffer command: %s', full_command)
    self._socket.sendall(full_command.encode() + b'\n')

    for line in self._socket.makefile():
      response = line.split(';')
      _LOG.debug('Sniffer response: %s', line.strip())
      if command in response and 'SUCCEEDED' in response:
        return
      raise SnifferError(full_command, line.strip())

  def _export_tab(self, tab):
    ending = '_' + tab.lower().rsplit(':', 1)[1].replace(' ', '_') + '.csv'
    try:
      self._sniffer_command('Export', 'File=' + self.export_prefix + ending,
                            'Tab=' + tab)
    except SnifferError as e:
      _LOG.warning('Failed to export tab %s: %s', tab, e.response)
    else:
      self._files.append(self.export_prefix + ending)

  @property
  def files(self):
    """Iterator over the names of log files created by the sniffer."""
    for path in self._files:
      yield os.path.basename(path)

  @property
  def export_prefix(self):
    """Generate a filename prefix specific to a single sniffer run."""
    return os.path.join(self._log_path, 'sniff_{}_{}'.format(
        self.capture_start_time.strftime('%Y%m%d-%H%M%S'), self.capture_id))

  def start_sniffing(self,
                     bluetooth_mac,
                     capture_id,
                     binary_path=REMOTE_BIN_PATH):
    """Configure the sniffer and start sniffing."""
    self._connect()
    assert self.capture_id is None
    self.capture_id = capture_id
    self.capture_start_time = datetime.datetime.now()

    _LOG.info('Starting BLE sniffer')
    self._sniffer_command('Start FTS', binary_path)
    self._sniffer_command('Config Settings', 'IOParameters', 'FTSLE',
                          'leDevice=0x' + bluetooth_mac.replace(':', ''))
    time.sleep(10)  # Give enough time for FTS to detect sniffer and initialize.
    self._sniffer_command('Start Sniffing')
    self._sniffer_command('Start Capture')

  def stop_sniffing(self):
    """Stop the sniffer and save the collected data."""
    if self.capture_id is None:
      _LOG.warning('Attempted to stop sniffing when no capture is underway')
      return

    self._sniffer_command('Stop Capture')
    self._sniffer_command('Save Capture', self.export_prefix + '.cfa')

    self._files = []
    self._files.append(self.export_prefix + '.cfa')
    self._files.append(self.export_prefix + '.frm')
    self._files.append(self.export_prefix + '.fsc')

    self._export_tab('LE:LE LL')
    self._export_tab('LE:LE DATA')

    self._sniffer_command('Stop FTS')

    _LOG.info('BLE data exported with prefix: %s', self.export_prefix)

    self.reset()

  def reset(self):
    """Reset the Sniffer abstraction to a clean state."""
    if self._socket:
      self._socket.close()
    self._socket = None
    self.capture_id = None
    self.capture_start_time = None

  @contextlib.contextmanager
  def sniff(self, bluetooth_mac, capture_id):
    """Start and stop the sniffer through the context manager interface."""
    self.start_sniffing(bluetooth_mac, capture_id)

    try:
      yield
    finally:
      self.stop_sniffing()


def _init_logging(logger, level):
  """Logging setup for use when this module is invoked as runnable."""
  logger.setLevel(logging.DEBUG)
  log_to_stderr = logging.StreamHandler()
  log_to_stderr.setLevel(level)
  log_to_stderr.setFormatter(
      logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)s: %(message)s',
                        '%Y-%m-%d %H:%M:%S'))
  logger.addHandler(log_to_stderr)


def _parse_args():
  """Argument parsing for use when this module is invoked as runnable."""
  parser = argparse.ArgumentParser(
      description=__doc__ + '\nScript version: ' + VERSION,
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--version', action='version', version=VERSION)
  parser.add_argument(
      '-v', '--verbose', action='store_true', help='enable verbose logging')
  parser.add_argument(
      '-a',
      '--address',
      required=True,
      help='Bluetooth MAC address of the bluetooth device or phone to sniff.')
  parser.add_argument(
      '--host',
      default='localhost',
      help="The sniffer's automation server address.")
  parser.add_argument('--capture_id', default='sniffer', help='capture ID')
  parser.add_argument(
      '-p',
      '--port',
      type=int,
      default=DEFAULT_AUTOMATION_PORT,
      help="The sniffer's automation server port.")
  parser.add_argument(
      '-l',
      '--local_log_path',
      type=str,
      default='',
      help='The path to sniffer logs on the local machine, if applicable.')
  parser.add_argument(
      '-d',
      '--download_port',
      type=int,
      default=DEFAULT_HTTP_PORT,
      help='The port for the HTTP server with the sniffer log files.')
  parser.add_argument(
      '-o',
      '--output',
      default='ble_sniffer_data',
      help='Filename at which to output the collected sniffer data.')
  parser.add_argument(
      '-s',
      '--seconds',
      type=float,
      help='Time to run; If not specified, runs until stopped.')
  return parser.parse_args()


def _run_bluetooth_sniffer(host, port, local_log_path, download_port, address,
                           verbose, capture_id, output, seconds):
  """Run the bluetooth sniffer; for use when module is invoked as runnable.

  Args: All arguments correspond to the matching args defined directly above in
      the _parse_args function. See help strings there for details.
  """
  _init_logging(_LOG, logging.DEBUG if verbose else logging.INFO)

  if not os.path.exists(output):
    os.makedirs(output)

  sniffer = BleSniffer(host, port)
  try:
    sniffer.start_sniffing(address, capture_id)
    util.sleep_or_prompt('BLE sniffer data collection', seconds, _LOG)
  finally:
    sniffer.stop_sniffing()
    if local_log_path:
      sniffer_files = [os.path.join(local_log_path, f) for f in sniffer.files]
    else:
      remote_files = [os.path.join(REMOTE_LOG_PATH, f) for f in sniffer.files]
      sniffer_files = files.download_files(
          remote_files, host, download_port, output)
    files.zip_files(sniffer_files, capture_id + '.zip')


# If invoked as a runnable module, parse args and run the bluetooth sniffer.
if __name__ == '__main__':
  _run_bluetooth_sniffer(**vars(_parse_args()))
