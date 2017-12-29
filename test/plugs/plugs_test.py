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

import mock
import openhtf

from openhtf import plugs
from openhtf.util import test


class AdderPlug(plugs.FrontendAwareBasePlug):

  INSTANCE_COUNT = 0
  LAST_INSTANCE = None

  def __init__(self):
    super(AdderPlug, self).__init__()
    type(self).INSTANCE_COUNT += 1
    type(self).LAST_INSTANCE = self
    self.state = 'CREATED'
    self.number = 0

  def _asdict(self):
    return {'number': self.number}

  def increment(self):
    self.number += 1
    self.notify_update()
    return self.number

  def tearDown(self):
    self.state = 'TORN DOWN'


class TearDownRaisesPlug1(plugs.BasePlug):
  TORN_DOWN = False
  def tearDown(self):
    type(self).TORN_DOWN = True
    raise Exception()


class TearDownRaisesPlug2(plugs.BasePlug):
  TORN_DOWN = False
  def tearDown(self):
    type(self).TORN_DOWN = True
    raise Exception()


class PlugsTest(test.TestCase):

  def setUp(self):
    self.logger = mock.MagicMock()
    self.plug_manager = plugs.PlugManager({AdderPlug}, self.logger)
    AdderPlug.INSTANCE_COUNT = 0

  def tearDown(self):
    self.plug_manager.tear_down_plugs()

  def test_base_plug(self):
    plug = plugs.BasePlug()
    self.assertEquals({}, plug._asdict())
    plug.tearDown()

  def test_initialize(self):
    self.assertEquals(0, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs()
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs()
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs({AdderPlug})
    self.assertEquals(1, AdderPlug.INSTANCE_COUNT)
    self.assertIs(
        AdderPlug.LAST_INSTANCE,
        self.plug_manager.provide_plugs(
            (('adder_plug', AdderPlug),))['adder_plug'])
    self.assertItemsEqual(self.plug_manager._asdict(), {
        'plug_descriptors': {
            'plugs_test.AdderPlug': plugs.PlugDescriptor('plugs_test.AdderPlug'),
        },
        'plug_states': {
            'plugs_test.AdderPlug': {'number': 0},
        },
        'xmlrpc_port': None,
    })
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

  @test.yields_phases
  def test_plug_logging(self):
    """Test that both __init__ and other functions get the good logger."""
    class LoggingPlug(plugs.BasePlug):
      def __init__(self):
        self.logger_seen_init = self.logger

      def action(self):
        self.logger_seen_action = self.logger

    @plugs.plug(logger=LoggingPlug)
    def dummy_phase(test_api, logger):
      logger.action()
      self.assertIs(logger.logger_seen_init, logger.logger_seen_action)
      self.assertIs(logger.logger_seen_init, self.logger)

    yield dummy_phase

  def test_tear_down_raises(self):
    """Test that all plugs get torn down even if some raise."""
    self.plug_manager.initialize_plugs({
      TearDownRaisesPlug1, TearDownRaisesPlug2})
    self.plug_manager.tear_down_plugs()
    self.assertTrue(TearDownRaisesPlug1.TORN_DOWN)
    self.assertTrue(TearDownRaisesPlug2.TORN_DOWN)

  def test_plug_updates(self):
    self.plug_manager.initialize_plugs({AdderPlug})
    update = self.plug_manager.wait_for_plug_update(
        'plugs_test.AdderPlug', {}, .001)
    self.assertEquals({'number': 0}, update)
    # No update since last time, this should time out (return None).
    self.assertIsNone(self.plug_manager.wait_for_plug_update(
        'plugs_test.AdderPlug', update, .001))

    def _delay_then_update():
      time.sleep(.5)
      self.assertEquals(1, AdderPlug.LAST_INSTANCE.increment())
    threading.Thread(target=_delay_then_update).start()
    start_time = time.time()
    self.assertEquals({'number': 1}, self.plug_manager.wait_for_plug_update(
        'plugs_test.AdderPlug', update, 5))
    self.assertGreater(time.time() - start_time, .2)

  def test_invalid_plug(self):
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.initialize_plugs({object})
    with self.assertRaises(plugs.InvalidPlugError):
      plugs.plug(adder_plug=object)
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.initialize_plugs({
          type('BadPlug', (plugs.BasePlug,), {'logger': None})})
    with self.assertRaises(plugs.InvalidPlugError):
      class BadPlugInit(plugs.BasePlug):
        def __init__(self):
          self.logger = None
      self.plug_manager.initialize_plugs({BadPlugInit})
    with self.assertRaises(plugs.InvalidPlugError):
      self.plug_manager.wait_for_plug_update('invalid', {}, 0)

  def test_duplicate_plug(self):
    with self.assertRaises(plugs.DuplicatePlugError):
      @plugs.plug(adder_plug=AdderPlug)
      @plugs.plug(adder_plug=AdderPlug)
      def dummy_phase(test, adder_plug):
        pass
