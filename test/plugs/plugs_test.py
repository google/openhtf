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
import unittest

from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.util import test


class AdderPlug(base_plugs.FrontendAwareBasePlug):

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

  def tearDown(self):  # pylint: disable=g-missing-super-call
    self.state = 'TORN DOWN'


class AdderSubclassPlug(AdderPlug):
  pass


class DummyPlug(base_plugs.BasePlug):
  pass


class TearDownRaisesPlug1(base_plugs.BasePlug):
  TORN_DOWN = False

  def tearDown(self):  # pylint: disable=g-missing-super-call
    type(self).TORN_DOWN = True
    raise Exception()


class TearDownRaisesPlug2(base_plugs.BasePlug):
  TORN_DOWN = False

  def tearDown(self):  # pylint: disable=g-missing-super-call
    type(self).TORN_DOWN = True
    raise Exception()


class PlugsTest(test.TestCase):

  def setUp(self):
    super(PlugsTest, self).setUp()
    self.plug_manager = plugs.PlugManager({AdderPlug})
    AdderPlug.INSTANCE_COUNT = 0

  def tearDown(self):
    self.plug_manager.tear_down_plugs()
    super(PlugsTest, self).tearDown()

  def test_base_plug(self):
    plug = base_plugs.BasePlug()
    self.assertEqual({}, plug._asdict())
    plug.tearDown()

  def test_initialize(self):
    self.assertEqual(0, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs()
    self.assertEqual(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs()
    self.assertEqual(1, AdderPlug.INSTANCE_COUNT)
    self.plug_manager.initialize_plugs({AdderPlug})
    self.assertEqual(1, AdderPlug.INSTANCE_COUNT)
    self.assertIs(
        AdderPlug.LAST_INSTANCE,
        self.plug_manager.provide_plugs(
            (('adder_plug', AdderPlug),))['adder_plug'])
    adder_plug_name = AdderPlug.__module__ + '.AdderPlug'
    self.assertEqual({adder_plug_name: {
        'mro': [adder_plug_name]
    }},
                     self.plug_manager.as_base_types()['plug_descriptors'])
    self.assertEqual({adder_plug_name: {
        'number': 0
    }},
                     self.plug_manager.as_base_types()['plug_states'])
    self.assertEqual('CREATED', AdderPlug.LAST_INSTANCE.state)

  @test.yields_phases
  def test_multiple_plugs(self):

    @plugs.plug(adder_plug=AdderPlug)
    @plugs.plug(other_plug=AdderPlug)
    def dummy_phase(adder_plug, other_plug):
      self.assertEqual(1, AdderPlug.INSTANCE_COUNT)
      self.assertIs(AdderPlug.LAST_INSTANCE, adder_plug)
      self.assertIs(AdderPlug.LAST_INSTANCE, other_plug)

    yield dummy_phase

    @plugs.plug(adder_plug=AdderPlug, other_plug=base_plugs.BasePlug)
    def dummy_phase(adder_plug, other_plug):
      del other_plug  # Unused.
      self.assertEqual(1, AdderPlug.INSTANCE_COUNT)
      self.assertIs(AdderPlug.LAST_INSTANCE, adder_plug)

    yield dummy_phase

  @test.yields_phases
  def test_plug_logging(self):
    """Test that both __init__ and other functions get the good logger."""

    class LoggingPlug(base_plugs.BasePlug):

      def __init__(self):
        self.logger_seen_init = self.logger

      def action(self):
        self.logger_seen_action = self.logger

    @plugs.plug(logger=LoggingPlug)
    def dummy_phase(logger):
      logger.action()
      self.assertIs(logger.logger_seen_init, logger.logger_seen_action)
      self.assertIs(logger.logger_seen_init, self.logger)

    yield dummy_phase

  def test_tear_down_raises(self):
    """Test that all plugs get torn down even if some raise."""
    self.plug_manager.initialize_plugs(
        {TearDownRaisesPlug1, TearDownRaisesPlug2})
    self.plug_manager.tear_down_plugs()
    self.assertTrue(TearDownRaisesPlug1.TORN_DOWN)
    self.assertTrue(TearDownRaisesPlug2.TORN_DOWN)

  def test_plug_updates(self):
    self.plug_manager.initialize_plugs({AdderPlug})
    adder_plug_name = AdderPlug.__module__ + '.AdderPlug'
    update = self.plug_manager.wait_for_plug_update(adder_plug_name, {}, .001)
    self.assertEqual({'number': 0}, update)
    # No update since last time, this should time out (return None).
    self.assertIsNone(
        self.plug_manager.wait_for_plug_update(adder_plug_name, update, .001))

    def _delay_then_update():
      time.sleep(.5)
      self.assertEqual(1, AdderPlug.LAST_INSTANCE.increment())

    threading.Thread(target=_delay_then_update).start()
    start_time = time.time()
    self.assertEqual({'number': 1},
                     self.plug_manager.wait_for_plug_update(
                         adder_plug_name, update, 5))
    self.assertGreater(time.time() - start_time, .2)

  def test_invalid_plug(self):
    with self.assertRaises(base_plugs.InvalidPlugError):
      self.plug_manager.initialize_plugs({object})  # pytype: disable=wrong-arg-types
    with self.assertRaises(base_plugs.InvalidPlugError):
      plugs.plug(adder_plug=object)  # pytype: disable=wrong-arg-types
    with self.assertRaises(base_plugs.InvalidPlugError):
      self.plug_manager.initialize_plugs(
          {type('BadPlug', (base_plugs.BasePlug,), {'logger': None})})
    with self.assertRaises(base_plugs.InvalidPlugError):

      class BadPlugInit(base_plugs.BasePlug):

        def __init__(self):
          self.logger = None

      self.plug_manager.initialize_plugs({BadPlugInit})
    with self.assertRaises(base_plugs.InvalidPlugError):
      self.plug_manager.wait_for_plug_update('invalid', {}, 0)

  def test_duplicate_plug(self):
    with self.assertRaises(plugs.DuplicatePlugError):

      @plugs.plug(adder_plug=AdderPlug)
      @plugs.plug(adder_plug=AdderPlug)
      def dummy_phase(adder_plug):
        del adder_plug  # Unused.

  def test_uses_base_tear_down(self):
    self.assertTrue(base_plugs.BasePlug().uses_base_tear_down())
    self.assertTrue(DummyPlug().uses_base_tear_down())
    self.assertFalse(AdderPlug().uses_base_tear_down())
    self.assertFalse(AdderSubclassPlug().uses_base_tear_down())
    self.assertFalse(TearDownRaisesPlug1().uses_base_tear_down())
