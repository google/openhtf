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


"""OpenHTF base plugs for thinly wrapping existing device abstractions.

Sometimes you already have a Python interface to a device or instrument; you
just need to put that interface in plug form to get it into your test phase.
Device-wrapping plugs are your friends in such times.
"""

from contextlib import contextmanager
import functools
import textwrap
import threading
import serial

import openhtf


class DeviceWrappingPlug(openhtf.plugs.BasePlug):
  """A base plug for wrapping existing device abstractions.

  Subclass instances must override the _device attribute to which normal
  attribute access will be delegated. Subclasses can use the
  @conf.inject_positional_args decorator on their constructors to get any
  configuration needed to construct the inner device instance.

  Example:
    class BleSnifferPlug(DeviceWrappingPlug):
      ...
      @conf.inject_positional_args
      def __init__(self, ble_sniffer_host, ble_sniffer_port):
        super(BleSnifferPlug, self).__init__(
            ble_sniffer.BleSniffer(ble_sniffer_host, ble_sniffer_port))
        ...

  Because not all third-party device and instrument control libraries can be
  counted on to do sufficient logging, some debug logging is provided here in
  the plug layer to show which attributes were called and with what arguments.

  Args:
    device: The device to wrap; must not be None.

  Raises:
    openhtf.plugs.InvalidPlugError: The _device attribute has the value None
        when attribute access is attempted.
  """
  def __init__(self, device):
    super(DeviceWrappingPlug, self).__init__()
    self._device = device

  def __getattr__(self, attr):
    if self._device is None:
      raise openhtf.plugs.InvalidPlugError(
        'DeviceWrappingPlug instances must set the _device attribute.')

    attribute = getattr(self._device, attr)

    if not callable(attribute):
      return attribute

    def arg_string(arg):
      """Returns a stdout-friendly string representation of the argument"""
      arg_repr = repr(arg)
      return arg_repr if len(arg_repr) < 40 else '<{} of length {}>'.format(
          type(arg).__name__, len(arg_repr))

    functools.wraps(attribute, assigned=('__name__', '__doc__'))
    def logging_wrapper(*args, **kwargs):
      args_strings = tuple(arg_string(arg) for arg in args)
      kwargs_strings = tuple(
          ('%s=%s' % (key, arg_val(val)) for key, val in kwargs.items()))
      log_line = '%s calling "%s" on device.' % (type(self).__name__, attr)
      if args_strings or kwargs_strings:
        log_line += ' Args: \n  %s' % (', '.join(args_strings + kwargs_strings))
      self.logger.debug(log_line)
      return attribute(*args, **kwargs)

    return logging_wrapper
