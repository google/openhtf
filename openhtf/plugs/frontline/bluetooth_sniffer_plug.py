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


"""Plugs for controlling Frontline (now Teledyne Lecroy) bluetooth sniffers."""

import textwrap

from openhtf.plugs import device_wrapping
from openhtf.plugs.frontline import bluetooth_sniffer


conf.declare(
    'bluetooth_sniffer_enable',
    description=textwrap.dedent('''\
        Whether or not to configure and enable sniffer control.

        Allows for authoring phases that can be used both with and without
        gathering sniffer data. If authoring such a phase, make sure to check
        the is_enabled property on sniffer plug instance before attempting to
        start or stop the sniffer.'''),
    default_value=False)
conf.declare(
    'bluetooth_sniffer_host',
    description='Host running BLE sniffer software.',
    default_value='localhost')
conf.declare(
    'bluetooth_sniffer_port',
    description='Port the BLE sniffer is running on.',
    default_value=ble_sniffer.DEFAULT_AUTOMATION_PORT)


class BluetoothSnifferPlug(device_wrapping.DeviceWrappingPlug):
  """A plug that controls a Frontline bluetooth sniffer.

  See the wrapped device class for details about which methods and properties
  are available on instances of this plug.

  Example Usage:

    @openhtf.plug(sniffer=bluetooth_sniffer_plug.BluetoothSnifferPlug)
    ...
    def collect_sniffer_data_phase(test, sniffer, ...):
      with sniffer.sniff():
        # Do stuff with blue devices that generates traffic
        ...

  Args:
    bluetooth_sniffer_enable: Whether to configure and enable the sniffer.
    bluetooth_sniffer_host: Hostname or IP address of the host running the
        sniffer automation server.
    bluetooth_sniffer_port: TCP port of the sniffer automation server.

  Wraps:
    openhtf.plugs.frontline.bluetooth_sniffer.Sniffer
  """
  @conf.inject_positional_args
  def __init__(self,
               bluetooth_sniffer_enable,
               bluetooth_sniffer_host,
               bluetooth_sniffer_port):
    # Default to no device if sniffer support is disabled via conf.
    device = None
    if bluetooth_sniffer_enable:
      device = bluetooth_sniffer.Sniffer(
          bluetooth_sniffer_host, bluetooth_sniffer_port)
    super(BluetoothSnifferPlug, self).__init__(device)

  def is_enabled(self):
    """True if sniffer support is enabled and sniffer control is set up."""
    return self._device is not None
