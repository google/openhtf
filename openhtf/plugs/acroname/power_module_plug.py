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


"""Acroname power module plug for OpenHTF."""


import logging
import time
from time import sleep

import openhtf.conf as conf
import openhtf.plugs as plugs

from brainstem import discover
from brainstem.link import Spec
from brainstem.stem import MTMPM1
from brainstem.stem import MTMEtherStem
from brainstem.stem import USBStem
from brainstem.defs import model_info

# _LOG = logging.getLogger("openhtf.example.plugs.acroname.power_module_plug.py")
_LOG = logging.getLogger(__name__)

conf.Declare('serial_number_of_EtherStem',
             description='Serial number of EtherStem that connects PowerModule to Ethernet.')

conf.Declare('default_power_module_voltage_output',
             description='Defalut power module voltage output in uV.')

conf.Declare('default_power_module_current_limit',
             description='Defalut power module current limit in uA.')

class NoneEtherStemFoundError(Exception):
 """No EtherStem module is found on the network."""

class NoMatchingEtherStemFoundError(Exception):
 """No EtherStem module matching the target EtherStem is found on the network."""

class ConnectingToEtherStemError(Exception):
 """Error connecting to EtherStem."""

class ConnectingToPowerModuleThroughEtherStemError(Exception):
 """Error connecting power module through EtherStem."""

class ConfigurePowerSupplyError(Exception):
 """Error configuring power supply."""

class TurnOnPowerSupplyError(Exception):
 """Error turning on power supply."""

class ChangeVoltageError(Exception):
 """Error changing voltage."""

class ChangeCurrentLimitError(Exception):
 """Error changing current limit."""

class TurnOffPowerSupplyError(Exception):
 """Error turning off power supply."""

 


class PowerSupplyControl(plugs.BasePlug):   # pylint: disable=no-init
  """Acronmae power module control plug."""
  

  def __init__(self):
    config = conf.Config()
    self.serial_number = config.serial_number_of_EtherStem
    self.voltage = config.default_power_module_voltage_output
    self.current_limit = config.default_power_module_current_limit
    self.MTMPowerModuleAddress = 6
    self.routerAddress = 4
    self.EtherStem = MTMEtherStem()
    self.power_module = MTMPM1()

  def DiscoverAndConnectModule(self):
    """
    Discover all EtherStems on network.
    Connect the one with the serial number specified in config yaml file.
    The connection from server to EtherStem is Ethernet via TCPIP.
    """
    # codes below is to discover EtherStem on network
    stem_list = discover.find_all(Spec.TCPIP)
    EtherStemFound = False
    if not stem_list:
      _LOG.info('None EtherStem is found.')
      raise NoneEtherStemFoundError
    for stem in stem_list:
      print "stem: "+str(stem)
      if stem.serial_number == self.serial_number:
        stem_index = stem_list.index(stem)
        spec = stem_list[stem_index]
        EtherStemFound = True
        break
    if not EtherStemFound:
      _LOG.info('No Matching EtherStem is found.')
      raise NoMatchingEtherStemFoundError
      
    
    # codes below is to connect EtherStem
    _LOG.info("Connecting to EtherStem with serial number:0x%X" %self.serial_number)
    print("Connecting to EtherStem with serial number: 0x%X" % self.serial_number)
    print "spec = "+str(spec)
    res = self.EtherStem.connect_from_spec(spec)
    print("Result of Connecting to EtherStem: " +str(res))
    if res != 0:
      _LOG.info("Error of connecting to EtherStem:"+str(res))
      raise ConnectingToEtherStemError
    else:
      _LOG.info("Connecting to EtherStem Succeed.")

    # codes below is to connect Power Module through EtherStem
    res_list=[]

    res = self.EtherStem.i2c[0].setPullup(1)
    res_list.append(res)
    _LOG.info("Result of setting link stem pullups:"+str(res))

    res = self.EtherStem.system.save()
    res_list.append(res)
    _LOG.info("Result of saving link stem:"+str(res))
    
    res = self.EtherStem.setModuleAddress(self.MTMPowerModuleAddress)
    res_list.append(res)
    _LOG.info("Result of setting power module's module address:"+str(res))

    res = self.EtherStem.system.setRouter(self.routerAddress)
    res_list.append(res)
    _LOG.info("Result of setting power module's router address:"+str(res))
    
    res = self.EtherStem.system.save()
    res_list.append(res)
    _LOG.info("Result of saving link stem:"+str(res))
    
    res = self.EtherStem.system.reset()
    res_list.append(res)
    _LOG.info("Result of resetting link stem:"+str(res))
    
    res = self.power_module.connect_through_link_module(self.EtherStem)
    res_list.append(res)
    _LOG.info("Result of connecting power module through EtherStem:"+str(res))

    if all(results == 0 for results in res_list):
      _LOG.info("Success in connecting power module through EtherStem.")
    else:
      _LOG.info("Error connecting power module through EtherStem.")
      raise ConnectingToPowerModuleThroughEtherStemError


  def NoShortCircuit(self):
    """
    Check if there is short on Power Module by driving one GPIO high.
    And read GPIO state to ensure it is actually high.
    """
    self.power_module.digital[0].setConfiguration(1)
    self.power_module.digital[0].setState(1)
    digital0State = self.power_module.digital[0].getState()
    nAttempts = 3
    while (digital0State.value != 1) and nAttempts:
        self.power_module.digital[0].setConfiguration(1)
        self.power_module.digital[0].setState(1)
        digital0State = self.power_module.digital[0].getState()
        nAttempts = nAttempts -1
        # print "power_module digital0State: %d" %digital0State.value
        _LOG.info("power_module digital0State: "+str(digital0State.value))
    if digital0State.value != 1:
        _LOG.info("digital0State: "+str(digital0State.value))
        # print "digital0State: %d" %digital0State.value
        self.power_module.rail[0].setEnableExternal(0)
        self.power_module.digital[0].setState(0)
        self.power_module.disconnect()
        _LOG.info("Power module is not in right state. Close connection.")
        # print "Power module is not in right state. Close connection."
        return False
    else:
        # print "Power module is in right state. Continue."
        return True

  def ConfigurePowerSupply(self):  # pylint: disable=no-self-use
    """Set Voltage, Current Limit, operational mode, kelvin sensing mode..."""
    res_list=[]

    res = self.power_module.rail[0].setVoltage(self.voltage)
    res_list.append(res)

    res = self.power_module.rail[0].setKelvinSensingMode(1)
    res_list.append(res)

    res = self.power_module.rail[0].setOperationalMode(1)
    res_list.append(res)

    res = self.power_module.rail[0].setCurrentLimit(self.current_limit)
    res_list.append(res)

    if all(result == 0 for result in res_list):
      # print "Succeed in configuring and turning on power supply."
      _LOG.info("Succeed in configuring and turning on power supply.")
    else:
      # print "Error configuring and turning on power supply."
      _LOG.info("Error configuring and turning on power supply.")
      raise ConfigurePowerSupplyError

  def TurnOnPowerSupply(self):
    """"""
    res = self.power_module.rail[0].setEnableExternal(1)
    sleep(0.1)
    if res == 0 and ( 
      (self.voltage-100000)<=self.GetVoltage()<=(self.voltage+100000)):
      # print "Succeed in turning on power supply."
      _LOG.info("Succeed in turning on power supply.")
    else:
      # print "Error turning on power supply."
      _LOG.info("Error turning on power supply.")
      raise TurnOnPowerSupplyError

  def GetVoltage(self):
    """Measure voltage and return voltage value."""
    vmeas = self.power_module.rail[0].getVoltage().value
    # print ("vmeas = %d uV" %vmeas)
    # v = round((float(vmeas)/float(1000000)))
    return vmeas

  def GetCurrent(self):
    """Measure current and return current value."""
    imeas = self.power_module.rail[0].getCurrent().value
    # print("imeas=%d uA" %imeas)
    # i = float(imeas/1000000)
    return imeas

  def ChangeVoltage(self, voltage):
    """Change output voltage value."""
    # res1 = self.power_module.rail[0].setEnableExternal(0)
    # sleep(0.5)
    for i in range(3):
      res = self.power_module.rail[0].setVoltage(voltage)
      sleep(0.5)
      vmeas= self.GetVoltage()
      print "vmeas=: %d"%vmeas
      if res==0 and (
        (voltage-100000)<=vmeas<=(voltage+100000)):
        # res3 = self.power_module.rail[0].setEnableExternal(1)
        # if res3 ==0:
        # print "Succeed in changing voltage."
        _LOG.info("Succeed in changing voltage.")
        break
        #else:
        #  raise ChangeVoltageError
      elif i==2:
        print "Error in changing voltage: res: %d" %res
        # print "vmeas=: %d"%vmeas
        _LOG.info("Error in changing voltage.")
        raise ChangeVoltageError


  def ChangeCurrentLimit(self,current_limit):
    """Change current limit value."""
    # res1 = self.power_module.rail[0].setEnableExternal(0)
    # sleep(0.5)
    res2 = self.power_module.rail[0].setCurrentLimit(current_limit)
    # print ("vmeas = %d uV" %vmeas)
    # v = round((float(vmeas)/float(1000000)))
    sleep(0.5)
    if res2==0:
      # print "Succeed in changing current limit."
      _LOG.info("Succeed in changing current limit..")
      """
      res3 = self.power_module.rail[0].setEnableExternal(1)
      if res3 ==0:
        # print "Succeed in changing voltage."
        _LOG.info("Succeed in changing voltage.")
      else:
        raise ChangeCurrentLimitError
      """
    else:
      # print "Error in changing current limit.."
      _LOG.info("Error in changing current limit..")
      raise ChangeCurrentLimitError

  def TurnOffAndDisconnect(self):
    """"""
    for i in range(3):
      res = self.power_module.rail[0].setEnableExternal(0)
      sleep(0.5)
      if res == 0:
        # print "Succeed in turning off power supply."
        _LOG.info("Succeed in turning off power supply.")
        self.power_module.disconnect()
        break
      elif i==2:
        print "Error turning off power supply:"
        print "res = %d" %res
        _LOG.info("Error turning of power supply.")
        raise TurnOffPowerSupplyError
