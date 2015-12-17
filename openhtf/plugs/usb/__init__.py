# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Plugs that provide access to USB devices via ADB/Fastboot.

For details of what these interfaces look like, see adb_device.py and
fastboot_device.py.

To use these plugs:
  from openhtf import plugs
  from openhtf.plugs import usb

  @plugs.RequiresPlug(adb=usb.AdbPlug)
  def MyPhase(test, adb):
    adb.Shell('ls')
"""
import commands
import logging

import openhtf.plugs as plugs
from openhtf import conf
from openhtf.plugs.usb import adb_device
from openhtf.plugs.usb import fastboot_device
from openhtf.plugs.usb import local_usb

conf.Declare('usb_server', 'USB Server IP/Hostname')
conf.Declare('usb_server_port', 'USB Server Port',
             default_value=10000)
conf.Declare('libusb_rsa_key', 'A private key file for use by libusb auth.')
conf.Declare('device_type', 'android, fastboot or general usb type')
conf.Declare('usb_hub', 'local or Ethersyncy')

_LOG = logging.getLogger(__name__)

class GeneralUsbAttributeError(Exception):
  """Indicates the usb class/subclass/protocol info was invalid."""

class general_usb(object):
  def __init__(self, usb_class=None, usb_subclass=None, usb_protocol=None):
    self.usb_class = usb_class
    self.usb_subclass = usb_subclass
    self.usb_protocol = usb_protocol

  @property
  def CLASS(self):
    return self.usb_class
  @property
  def SUBCLASS(self):
    return self.usb_subclass
  @property
  def PROTOCOL(self):
    return self.usb_protocol

""" Config file example for device at Ethersync
device_type: android (fastboot, general)
usb_hub: 
  Ethersync:
   prot_addr: EtherSyncca9166.214

---- Config file example for android/fastboot usb at local 
device_type: android (fastboot)
usb_hub: local

---- Config file example for android/fastboot usb at local
device_type: general
usb_hub: 
   local:
      class: xxxxx
      subclass: xxxxx
      protocol: xxxxx
      vendor_id:  xxxx (optional)
      product_id: xxxxx(optional)
      serial: (device serial number, optional)
"""


def _get_usb_serial(port_addr):
  """Get a usb serial based on the Cambrionix unit mac address in configuration."""
  cmd = '/usr/local/google/home/amyxchen/esuit64 -t "DEVICE INFO,%s"' % port_addr.strip()
  info = commands.getstatusoutput(cmd)[1]
  serial = None

  if "SERIAL" in info:
    serial_info = info.split('SERIAL:')[1]
    serial = serial_info.split('\n')[0].strip()
    _LOG.info('get serial:%s on port:%s' % (serial, port_addr))
  else:
    raise GeneralUsbAttributeError('No USB device detected')
  return serial

def _open_usb_handle():
  dev_type = conf.Config().device_type
  usb_hub = conf.Config().usb_hub
  serial = None
  vendor_id = None
  product_id = None
  device = None
      
  if isinstance(usb_hub, dict):
    if usb_hub.has_key('Ethersync'):
      device = usb_hub['Ethersync']
      if isinstance(device, dict) and device.has_key('port_addr'):
        serial = _get_usb_serial(device['port_addr'])
      else:
        raise GeneralUsbAttributeError('Ethersync needs port_addr address to be set')
    else:
      device = usb_hub['local']
  else:
    device = usb_hub

  if dev_type == 'fastboot':
    device = fastboot_device
  elif dev_type == 'android':
    device = adb_device
  elif dev_type == 'general':
    if isinstance(device, dict):
      try:
        vendor_id = device['vendor_id']
      except KeyError:
        pass
      try:
        product_id = device['product_id']
      except KeyError:
        pass
      try:
        serial = device['serial']
      except KeyError:
        pass

      try:
        device = general_usb(device['class'], device['subclass'], device['protocol'])
      except KeyError:
        raise GeneralUsbAttributeError('must set class\subclass\protocol for \
                                        general type device:%s', device)
    else:
      raise GeneralUsbAttributeError('must set attribute for general \
                                      device:%s', device)
  else:
    raise GeneralUsbAttributeError('must set device type')

  return local_usb.LibUsbHandle.Open(
         interface_class=device.CLASS,
         interface_subclass=device.SUBCLASS,
         interface_protocol=device.PROTOCOL,
         serial_number=serial,
         vendor_id=vendor_id,
         product_id=product_id)

# pylint: disable=too-few-public-methods
class FastbootPlug(plugs.BasePlug):
  """Plug that provides fastboot."""

  def __new__(cls):
    handle = _open_usb_handle()
    device = fastboot_device.FastbootDevice.Connect(handle)
    device.TearDown = device.Close  # pylint: disable=invalid-name
    return device


class AdbPlug(plugs.BasePlug):
  """Plug that provides ADB."""
  def __new__(cls):
    kwargs = {}
    if conf.Config().libusb_rsa_key:
      kwargs['rsa_keys'] = [adb_device.M2CryptoSigner(
          conf.Config().libusb_rsa_key)]
    handle = _open_usb_handle()
    device = adb_device.AdbDevice.Connect(handle, **kwargs)
    device.TearDown = device.Close  # pylint: disable=invalid-name
    return device

class UsbPlug(plugs.BasePlug):
  """Plug that provides general USB."""

  def __new__(cls):
    device = _open_usb_handle()
    device.TearDown = device.Close  # pylint: disable=invalid-name
  
    return device