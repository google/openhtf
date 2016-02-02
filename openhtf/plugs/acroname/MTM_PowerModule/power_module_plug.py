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
from brainstem.stem import MTMUSBStem
from brainstem.defs import model_info

# _LOG = logging.getLogger("openhtf.example.plugs.acroname.power_module_plug.py")
_LOG = logging.getLogger(__name__)

conf.Declare('serial_number_of_EtherStem',
             description='Serial number of EtherStem that connects PowerModule to Ethernet.')

conf.Declare('MTM_PowerModule',
             description='MTM Power Module configurations voltage output in uV and current limit in uA.')

# conf.Declare('default_power_module_current_limit',
#             description='Defalut power module current limit in uA.')

conf.Declare('MTM_PowerModule_Connection',
             description='MTM Power Module COnnection Parameters.')


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

class PowerModuleShortCircuitError(Exception):
 """Short Circuit Found on Power Module."""

class DisconnectPowerModuleError(Exception):
 """Error disconnecting power module."""


def CheckReturnCode(code, action_str):
  if not code:
    _LOG.info("Result of %s: %d", action_str, code)
  else:
    _LOG.error("""Error connecting to power module through 
      EtherStem while attempting to %s: %d""", action_str,code)
    raise ConnectingToPowerModuleThroughEtherStemError() 


class PowerSupplyControl(plugs.BasePlug):   # pylint: disable=no-init
  """Acronmae power module control plug."""
  

  def __init__(self):
    config = conf.Config()
    self.connection_type = config.MTM_PowerModule_Connection['link_type']
    self.link_module_serial_number = config.MTM_PowerModule_Connection['link_serial_number']
    self.power_module_serial_number = config.MTM_PowerModule_Connection['power_module_serial_number']
    self.voltage = config.MTM_PowerModule['voltage_output']
    self.current_limit = config.MTM_PowerModule['current_limit']
    self.is_first_time_setup = config.MTM_PowerModule_Connection['first_time_setup']
    self.MTMPowerModuleAddress = 6
    self.routerAddress = 4
    if self.connection_type == 'MTM_EtherStem':
      self.link_stem = MTMEtherStem()
    elif self.connection_type == 'MTM_USBStem': 
      self.link_stem = MTMUSBStem()

    self.power_module = MTMPM1()
    
    """
    if self.connection_type == 'MTM_EtherStem':
      self.stem_list = discover.find_all(Spec.TCPIP)
    elif self.connection_type == 'MTM_USBStem': 
      self.stem_list = discover.find_all(Spec.USB)
    elif self.connection_type == 'USB':
      self.serial_number = config.MTM_PowerModule_Connection['power_module_serial_number']
      self.stem_list = discover.find_all(Spec.USB)
    """
  def DiscoverAndConnectModule(self):
    """
    Discover a power module if it is not connected yet.
    Connect the one with the serial number specified in config yaml file.
    """
    # spec = discover.find_first_module(Spec.TCPIP)
    print "Is power module connected?"
    print self.power_module.is_connected()

    if self.connection_type == 'USB':
      res = self.power_module.connect(self.power_module_serial_number)
      if self.is_first_time_setup:
        res = self.power_module.system.setRouter(self.MTMPowerModuleAddress)
        #CheckReturnCode(res, "setRouterAddress")
      
        res = self.power_module.system.save()
        #CheckReturnCode(res, "LinkStemSave")

        res = self.power_module.system.reset()
        #CheckReturnCode(res, "PowerModulereset")
    
      
      print "res = "+str(res)
      print("is power module connected? %d"%self.power_module.is_connected())
      CheckReturnCode(res, "power_module.connect")
      _LOG.info("Connected to Power Module with serial number: ",hex(self.power_module_serial_number).upper())
      print("Connected to Power Module with serial number: 0x%X" % self.power_module_serial_number)
    
    else:
      print "Connecting to link stem..."
      
      res = self.link_stem.connect(self.link_module_serial_number)
      print "res = "+str(res)
      CheckReturnCode(res, "link_stem.connect")
      _LOG.info("Connected to Link Module with serial number: ",hex(self.link_module_serial_number).upper())
      print("Connected to Link Module with serial number: 0x%X" % self.link_module_serial_number)
      
      if self.is_first_time_setup:
        # connect to the power module through the link stem's lnik
        res = self.power_module.connect_through_link_module(self.link_stem)

        # These configruation need to be done once only unless there is hardware change in the network
        res = self.link_stem.i2c[0].setPullup(1)
        #CheckReturnCode(res, "LinkStemsetPullUp")

        #res = self.link_stem.system.save()
        #CheckReturnCode(res, "LinkStemSave")
        
        # set link stem object to talk to the power module 
        # res = self.link_stem.setModuleAddress(self.MTMPowerModuleAddress)
        # CheckReturnCode(res, "setModuleAddress")

        # get the module address the link_stem's link is connected to
        # we will set this as the BrainStem network router
        
        #res = self.link_stem.module()
        #routerAddress = res
        #print "link stem's module address %d" %routerAddress

        # set the link stem's module address offsets to 0
        # we will assume the link stem hardware offsets are 0
        res = self.link_stem.system.setModuleSoftwareOffset(0)

        # set the link stem's router address
        res = self.link_stem.system.setRouter(self.routerAddress)
        #CheckReturnCode(res, "setRouterAddress")
      
        res = self.power_module.system.setRouter(self.routerAddress)
        #CheckReturnCode(res, "setRouterAddress")

        res = self.link_stem.system.save()
        CheckReturnCode(res, "LinkStemSave")

        res = self.power_module.system.save()
        #CheckReturnCode(res, "PowerModuleSave")
    
        res = self.power_module.system.reset()
        #CheckReturnCode(res, "PowerModulereset")
    
        res = self.link_stem.system.reset()
        CheckReturnCode(res, "Linkreset")
        
      # res = self.power_module.connect_through_link_module(self.EtherStem)
      # CheckReturnCode(res, "PowerModuleConnectThroughLink")
      # res = self.link_stem.connect(self.link_module_serial_number)
      # CheckReturnCode(res, "PowerModuleConnectThroughLink")
      # res = self.power_module.connect_through_link_module(self.link_stem)
      # CheckReturnCode(res, "PowerModuleConnectThroughLink")
    
    

    '''
    if not self.stem_list:
      _LOG.info('None EtherStem is found.')
      raise NoneEtherStemFoundError
    for stem in self.stem_list:
      # print "stem: "+str(stem)
      if stem.serial_number == self.serial_number:
        stem_index = self.stem_list.index(stem)
        spec = self.stem_list[stem_index]
        # EtherStemFound = True
        break
    else:
      _LOG.info('No Matching EtherStem is found.')
      raise NoMatchingEtherStemFoundError
    '''  
    
    # codes below is to connect EtherStem
    
    # print "spec = "+str(spec)
    # res = self.EtherStem.connect_from_spec(spec)
    # print("Result of Connecting to EtherStem: " +str(res))

    # codes below is to connect Power Module through EtherStem
    # TO CONSIDER USB LOCAL CONNECTION CASE
    
    


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
        digital0State = self.power_module.digital[0].getState()
        nAttempts = nAttempts -1
        print "power_module digital0State: %d" %digital0State.value
        _LOG.info("power_module digital0State: "+str(digital0State.value))
    if digital0State.value != 1:
        _LOG.info("digital0State: "+str(digital0State.value))
        # print "digital0State: %d" %digital0State.value
        self.power_module.rail[0].setEnableExternal(0)
        self.power_module.digital[0].setState(0)
        _LOG.info("Power module is not in right state.There is short circuit. Close connection.")
        raise PowerModuleShortCircuitError
        # print "Power module is not in right state. Close connection."
        # return False
    else:
        # print "Power module is in right state. Continue."
        return True

  def ConfigurePowerSupply(self):  # pylint: disable=no-self-use
    """Set Voltage, Current Limit, operational mode, kelvin sensing mode..."""
    res_list=[]
    if self.is_first_time_setup:
      #This is one time setup:
      res = self.power_module.rail[0].setKelvinSensingMode(1)
      res_list.append(res)

      res = self.power_module.rail[0].setOperationalMode(1)
      #auto mode: 0
      res_list.append(res)

    #res = self.power_module.rail[0].setVoltage(self.voltage)
    self.ChangeVoltage(self.voltage)
    res_list.append(res)

    res = self.power_module.rail[0].setCurrentLimit(self.current_limit)
    res_list.append(res)

    if all(result == 0 for result in res_list):
      print "Succeed in configuring and turning on power supply."
      _LOG.info("Succeed in configuring and turning on power supply.")
    else:
      # print "Error configuring and turning on power supply."
      _LOG.info("Error configuring and turning on power supply.")
      print "configuration result list: "+str(res_list)
      raise ConfigurePowerSupplyError

  def TurnOnPowerSupply(self):
    """"""
    res = self.power_module.rail[0].setEnableExternal(1)
    voltage_meas = self.GetVoltage()
    if res == 0 and ( 
      (self.voltage-0.5e6)<=voltage_meas<=(self.voltage+500000)):
      # print "Succeed in turning on power supply."
      _LOG.info("Succeed in turning on power supply.")
    else:
      print "Error enabling rail0: res = "+str(res)
      print "GetVoltage: %d"%voltage_meas
      # print "Error turning on power supply."
      _LOG.info("Error turning on power supply.")
      raise TurnOnPowerSupplyError

  def GetVoltage(self):
    """Measure voltage and return voltage value."""
    res = self.power_module.rail[0].getVoltage()
    vmeas=0.0
    if res.error == 0:
      vmeas = res.value
    else:
      print "GetVoltage(): Error getting power module voltage: %d"%(res.error)
      if not res.value:
        print "GetVoltage(): %.3f" % (res.value)
    # print ("vmeas = %d uV" %vmeas)
    # v = round((float(vmeas)/float(1000000)))
    return vmeas

  def GetCurrent(self):
    """Measure current and return current value."""
    imeas = self.power_module.rail[0].getCurrent().value
    error = self.power_module.rail[0].getCurrent().error
    print("GetCurrent Error:%d"%error)
    # print("imeas=%d uA" %imeas)
    # i = float(imeas/1000000)
    return imeas

  def ChangeVoltage(self, voltage_uV):
    """Change output voltage value."""
    # res1 = self.power_module.rail[0].setEnableExternal(0)
    # sleep(0.5)
    for i in range(3):
      res = self.power_module.rail[0].setVoltage(voltage_uV)
      sleep(0.1)
      vmeas_uV = self.GetVoltage()
      # print "change vmeas=: %d"%vmeas_uV
      if res==0 and (
        (voltage_uV-500000)<=vmeas_uV<=(voltage_uV+500000)):
        # res3 = self.power_module.rail[0].setEnableExternal(1)
        # if res3 ==0:
        # print "Succeed in changing voltage."
        _LOG.info("Succeed in changing voltage.")
        break
        #else:
        #  raise ChangeVoltageError
      elif i==2:
        print "Error in changing voltage: res: %d" %res
        print "vmeas_uV=: %d"%vmeas_uV
        _LOG.info("Error in changing voltage.")
        raise ChangeVoltageError


  def ChangeCurrentLimit(self,current_limit_uA):
    """Change current limit value."""
    # res1 = self.power_module.rail[0].setEnableExternal(0)
    # sleep(0.5)
    res2 = self.power_module.rail[0].setCurrentLimit(current_limit_uA)
    # print ("vmeas = %d uV" %vmeas)
    # v = round((float(vmeas)/float(1000000)))
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

  def PowerOff(self):
    """"""
    for i in range(3):
      res = self.power_module.rail[0].setEnableExternal(0)
      if res == 0:
        # print "Succeed in turning off power supply."
        _LOG.info("Succeed in turning off power supply.")
        break
      elif i==2:
        # print "Error turning off power supply:"
        print "res = %d" %res
        _LOG.info("Error turning of power supply.")
        raise TurnOffPowerSupplyError

  def Disconnect(self):
    """"""
    self.power_module.disconnect()
    self.link_stem.disconnect()