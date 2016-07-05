# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import threading
import time

import openhtf

from openhtf import plugs
from openhtf.util import test


class AdderPlug(plugs.BasePlug):

  INSTANCE_COUNT = 0
  LAST_INSTANCE = None

  def __init__(self):
    type(self).INSTANCE_COUNT += 1
    type(self).LAST_INSTANCE = self
    self.state = 'CREATED'
    self.number = 0

  def _asdict(self):
    return {'number': self.number}

  def increment(self):
    self.number += 1
    return self.number

  def TearDown(self):
    self.state = 'TORN DOWN'


class TearDownRaisesPlug1(plugs.BasePlug):
  TORN_DOWN = False
  def TearDown(self):
    type(self).TORN_DOWN = True
    raise Exception()


class TearDownRaisesPlug2(plugs.BasePlug):
  TORN_DOWN = False
  def TearDown(self):
    type(self).TORN_DOWN = True
    raise Exception()


class PlugsTest(test.TestCase):

  def setUp(self):
    self.logger = object()
    self.plug_manager = plugs.PlugManager({AdderPlug}, self.logger)

  def tearDown(self):
    self.plug_manager.TearDownPlugs()

  def test_base_plug(self):
    plug = plugs.BasePlug()
    self.assertEquals({}, plug._asdict())
    plug.TearDown()

  def test_initialize(self):
    self.assertEquals(0, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.InitializePlugs()
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.InitializePlugs()
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.InitializePlugs({AdderPlug})
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.assertIs(
        AdderPlug.LAST_INSTANCE,
        self.plug_manager.ProvidePlugs(
            (('adder_plug', AdderPlug),))['adder_plug'])
    self.assertItemsEqual(
        {'plugs_test.AdderPlug'}, self.plug_manager._asdict())
    self.assertIs(
        AdderPlug.LAST_INSTANCE,
        self.plug_manager._asdict()['plugs_test.AdderPlug'])
    self.assertEquals('CREATED', AdderPlug.LAST_INSTANCE.state)

  @test.yields_phases
  def test_multiple_plugs(self):
    @plugs.plug(adder_plug=AdderPlug)
    @plugs.plug(other_plug=AdderPlug)
    def dummy_phase(test_api, adder_plug, other_plug):
      self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
      self.assertIs(AdderPlug.LAST_INSTANCE, adder_plug)
      self.assertIs(AdderPlug.LAST_INSTANCE, other_plug)
    yield dummy_phase
      
    @plugs.plug(adder_plug=AdderPlug,
                other_plug=plugs.BasePlug)
    def dummy_phase(test_api, adder_plug, other_plug):
      self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
      self.assertIs(AdderPlug.LAST_INSTANCE, adder_plug)
    yield dummy_phase

  def test_tear_down_raises(self):
    """Test that all plugs get torn down even if some raise."""
    self.plug_manager.InitializePlugs({
      TearDownRaisesPlug1, TearDownRaisesPlug2})
    self.plug_manager.TearDownPlugs()
    self.assertTrue(TearDownRaisesPlug1.TORN_DOWN)
    self.assertTrue(TearDownRaisesPlug2.TORN_DOWN)

  def test_plug_updates(self):
    self.plug_manager.InitializePlugs({AdderPlug})
    update = self.plug_manager.WaitForPlugUpdate(
        'plugs_test.AdderPlug', {}, .001)
    self.assertEquals({'number': 0}, update)
    # No update since last time, this should time out (return None).
    self.assertIsNone(self.plug_manager.WaitForPlugUpdate(
        'plugs_test.AdderPlug', update, .001))

    def _delay_then_update():
      time.sleep(.5)
      self.assertEquals(1, AdderPlug.LAST_INSTANCE.increment())
    threading.Thread(target=_delay_then_update).start()
    start_time = time.time()
    self.assertEquals({'number': 1}, self.plug_manager.WaitForPlugUpdate(
        'plugs_test.AdderPlug', update, 5))
    self.assertGreater(time.time() - start_time, .2)
  
  def test_invalid_plug(self):
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.InitializePlugs({object})
    with self.assertRaises(plugs.InvalidPlugError):
      plugs.plug(adder_plug=object)
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.InitializePlugs({
          type('BadPlug', (plugs.BasePlug,), {'logger': None})})
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.WaitForPlugUpdate('invalid', {}, 0)

  def test_duplicate_plug(self):
    with self.assertRaises(plugs.DuplicatePlugError):
      @plugs.plug(adder_plug=AdderPlug)
      @plugs.plug(adder_plug=AdderPlug)
      def dummy_phase(test, adder_plug):
        pass
