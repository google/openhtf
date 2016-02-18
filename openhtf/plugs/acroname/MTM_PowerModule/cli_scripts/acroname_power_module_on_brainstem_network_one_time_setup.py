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

"""
The following network configurations need to be specified for each test station
"""
link_type='USB' # 3 types to choose from: 'MTM_USBStem', 'MTM_EtherStem', 'USB'
link_serial_number = 0xCB6B1A04 # Change this to the serial number of the link stem (EtherStem or MTM_USBStem); Ignore this if link_type is 'USB'
# EtherStem: 0xD6760719
# MTM_USBStem: 0xCB6B1A04
power_module_serial_number= 0x2B8BFAE4 # Change this to the serial number of the power module
router_address= 4 # Do not change
power_module_address = 6 # Do not change



if link_type == 'MTM_EtherStem':
    link_stem = MTMEtherStem()
elif link_type == 'MTM_USBStem': 
    link_stem = MTMUSBStem()

power_module = MTMPM1()
    

if link_type == 'USB':
      # spec = discover.find_all(Spec.USB)
      #spec = discover.find_module(Spec.USB,self.power_module_serial_number)
      # print "spec: "+str(spec)
      # print "USB serial number: 0x" + str(hex(spec[0].serial_number))
  res = power_module.connect(power_module_serial_number)
  # print "power module connection res: %d"%res

  res = power_module.system.setRouter(power_module_address)
  #CheckReturnCode(res, "setRouterAddress")
      
  res = power_module.system.save()
  #CheckReturnCode(res, "LinkStemSave")

  res = power_module.system.reset()
  #CheckReturnCode(res, "PowerModulereset")
  sleep(0.1)

  print("power module USB connection result? %d"%power_module.is_connected())
  if power_module.is_connected():
    print "Network set up OK"
  else:
    print "Network set up failed. Please retry."
  #CheckReturnCode(res, "power_module.connect")
      
else:
  # print "Connecting to link stem..."
  # spec = discover.find_all(Spec.USB)
  # print "spec: "+str(spec)
  # spec = discover.find_module(Spec.USB,power_module_serial_number)
  # print "spec: "+str(spec)
      
  res = link_stem.connect(link_serial_number)
  #CheckReturnCode(res, "link_stem.connect")
  print "Is link stem connected now?"
  print link_stem.is_connected()

  res = power_module.connect_through_link_module(link_stem)

  res = link_stem.i2c[0].setPullup(1)
  #CheckReturnCode(res, "LinkStemsetPullUp")

        # set link stem object to talk to the power module 
        # res = self.link_stem.setModuleAddress(self.MTMPowerModuleAddress)
        # CheckReturnCode(res, "setModuleAddress")

        # get the module address the link_stem's link is connected to
        # we will set this as the BrainStem network router
        
        #res = self.link_stem.module()
        #routerAddress = res

        # set the link stem's module address offsets to 0
        # we will assume the link stem hardware offsets are 0
  res = link_stem.system.setModuleSoftwareOffset(0)

  # set the link stem's router address
  res = link_stem.system.setRouter(router_address)
  #CheckReturnCode(res, "setRouterAddress")
      
  res = power_module.system.setRouter(router_address)
  #CheckReturnCode(res, "setRouterAddress")

  res = link_stem.system.save()
  #CheckReturnCode(res, "LinkStemSave")

  res = power_module.system.save()
  #CheckReturnCode(res, "PowerModuleSave")
    
  res = power_module.system.reset()
  #CheckReturnCode(res, "PowerModulereset")
    
  res = link_stem.system.reset()
  #CheckReturnCode(res, "Linkreset")
  sleep(0.1)
  print("power module USB connection result? %d"%power_module.is_connected())
  if power_module.is_connected():
    print "Network set up OK"
  else:
    print "Network set up failed. Please retry."