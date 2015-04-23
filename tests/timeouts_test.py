"""Tests for google3.googlex.glass.xtf.xdc.shared.timeouts."""

import threading
import time

import google3
import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import timeouts


class PolledTimeoutTest(googletest.TestCase):

  @mock.patch.object(time, 'time', side_effect=[1, 2, 3, 4, 5])
  def testPolling(self, unused_mock):
    timeout = timeouts.PolledTimeout(2)
    self.assertFalse(timeout.Poll())
    self.assertFalse(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    self.assertTrue(timeout.Poll())

  @mock.patch.object(time, 'time', side_effect=[1, 2, 3, 4, 5] * 4)
  def testFactories(self, unused_mock):
    timeout = timeouts.PolledTimeout.FromSeconds(2)
    self.assertFalse(timeout.HasExpired())
    self.assertFalse(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    timeout = timeouts.PolledTimeout.FromSeconds(timeouts.PolledTimeout(2))
    self.assertFalse(timeout.HasExpired())
    self.assertFalse(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    timeout = timeouts.PolledTimeout.FromMillis(2000)
    self.assertFalse(timeout.HasExpired())
    self.assertFalse(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    timeout = timeouts.PolledTimeout.FromMillis(timeouts.PolledTimeout(2))
    self.assertFalse(timeout.HasExpired())
    self.assertFalse(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())
    self.assertTrue(timeout.HasExpired())

  @mock.patch.object(time, 'time', side_effect=[1, 2, 3, 4, 5, 6])
  def testRestart(self, unused_mock):
    timeout = timeouts.PolledTimeout(1)
    self.assertFalse(timeout.Poll())
    self.assertTrue(timeout.Poll())
    timeout.Restart()
    self.assertFalse(timeout.Poll())
    self.assertTrue(timeout.Poll())

  @mock.patch.object(time, 'time', side_effect=[1, 2, 3, 4, 5, 6])
  def testExpire(self, unused_mock):
    timeout = timeouts.PolledTimeout(4)
    self.assertFalse(timeout.HasExpired())
    self.assertFalse(timeout.HasExpired())
    timeout.Expire()
    self.assertTrue(timeout.HasExpired())

  def testLoopUntilWithPolledTimeout(self):
    timeout = timeouts.PolledTimeout(1.5)
    fn = mock.Mock(side_effect=[False, False, False, True])
    result = timeouts.LoopUntilTimeoutOrTrue(timeout, fn, 0)
    self.assertTrue(result)

  def testTakeAtLeast(self):
    start = time.time()
    with timeouts.TakeAtLeastNSeconds(.05):
      time.sleep(.01)
    total = time.time() - start
    self.assertGreater(total, .05)

  def testTakeAtMost(self):
    self.assertTrue(timeouts.TakeAtMostNSeconds(.01, lambda: None))
    self.assertFalse(timeouts.TakeAtMostNSeconds(.01, lambda: time.sleep(.02)))

  def testExecuteAfterDelay(self):
    start_time = time.time()
    def AssertEndTime(foo, bar):
      self.assertEquals('foo', foo)
      self.assertEquals('bar', bar)
      self.assertBetween(time.time() - start_time, .4, .6)
    timeouts.ExecuteAfterDelay(.5, AssertEndTime, 'foo', bar='bar')
    timeouts.ExecuteAfterDelay(
        timeouts.PolledTimeout.FromMillis(500),
        AssertEndTime, 'foo', bar='bar')
    timeouts.ExecuteAfterDelay(None, self.fail)
    self.assertBetween(time.time() - start_time, 0, .1)


class LoopUntilTests(googletest.TestCase):

  def setUp(self):
    self.timeout_patch = mock.patch.object(
        timeouts, 'PolledTimeout', autospec=True)
    self.sleep_patch = mock.patch.object(time, 'sleep')

    self.sleep = self.sleep_patch.start()
    self.timeout = self.timeout_patch.start().return_value
    self.addCleanup(self.sleep_patch.stop)
    self.addCleanup(self.timeout_patch.stop)

  def testLoopUntilValid(self):
    self.timeout.HasExpired.return_value = False
    fn = mock.Mock(side_effect=[1, 1, 1, 2])
    result = timeouts.LoopUntilTimeoutOrValid(None, fn, lambda x: x == 2)
    self.assertEquals(2, result)

  def testLoopUntilNotNone(self):
    self.timeout.HasExpired.return_value = False
    fn = mock.Mock(side_effect=[None, None, {}])
    result = timeouts.LoopUntilTimeoutOrNotNone(None, fn)
    self.assertEquals({}, result)

  def testTimeoutCase(self):
    self.timeout.HasExpired.side_effect = [False, False, True]
    result = timeouts.LoopUntilTimeoutOrTrue(2, lambda: False)
    self.assertFalse(result)

  def testNoneTimeout(self):
    self.timeout.HasExpired.return_value = False
    fn = mock.Mock(side_effect=[False, False, False, True])
    result = timeouts.LoopUntilTimeoutOrTrue(None, fn)
    self.assertTrue(result)

  def testFunctionReturningTrueSucceeds(self):
    self.timeout.HasExpired.return_value = False

    fn = mock.Mock(side_effect=[False, True])
    result = timeouts.LoopUntilTimeoutOrTrue(2, fn)
    self.assertTrue(result)

  def testSleepIsCalled(self):
    self.timeout.HasExpired.side_effect = [False, False, True]
    timeouts.LoopUntilTimeoutOrTrue(2, lambda: False, sleep_s=5)
    self.assertEquals(2, self.sleep.call_count)

  def testOnlyCalledOnceIfMethodIsTrueFirst(self):
    self.timeout.HasExpired.return_value = False
    method = mock.Mock(return_value=True)
    timeouts.LoopUntilTimeoutOrTrue(0, method, sleep_s=5)
    method.assert_called_once_with()

  def testAlwaysCalledOnceIfTimeoutIsZero(self):
    self.timeout.HasExpired.return_value = True
    method = mock.Mock(return_value=False)
    timeouts.LoopUntilTimeoutOrTrue(0, method, sleep_s=5)
    method.assert_called_once_with()


class IntervalTests(googletest.TestCase):

  def setUp(self):
    self.method = mock.Mock(spec=[])
    self.interval = timeouts.Interval(self.method)

  def tearDown(self):
    self.interval.Stop()

  def testRunningFlag(self):
    self.assertFalse(self.interval.running)
    self.assertTrue(self.interval.Start(50))
    self.assertTrue(self.interval.running)

  def testMethodCalledImmediately(self):
    evt = threading.Event()
    self.method.side_effect = evt.set

    self.assertTrue(self.interval.Start(50))
    evt.wait(3)
    self.assertTrue(evt.isSet())

  def testMethodCalledManyTimes(self):
    evt = threading.Event()
    self.method.side_effect = lambda: self.method.call_count == 3 and evt.set()

    self.interval.Start(.2)
    evt.wait(4)
    self.assertTrue(evt.isSet())
    self.assertTrue(self.interval.Stop())
    self.assertEquals(self.method.call_count, 3)

  def testThreadStopsSuccessfully(self):
    self.assertTrue(self.interval.Start(.01))
    self.interval.thread.join(.03)
    self.interval.Stop()
    self.assertFalse(self.interval.thread.isAlive())

    self.assertGreater(self.method.call_count, 0)

  def testStartReturnsFalseIfRunning(self):
    self.assertTrue(self.interval.Start(1))
    self.assertFalse(self.interval.Start(1))
    self.assertTrue(self.interval.Stop())
    self.assertTrue(self.interval.Start(1))

  def testStopTimeouts(self):
    evt = threading.Event()
    self.method.side_effect = evt.wait

    self.interval.Start(0.01)
    self.assertFalse(self.interval.Stop(0.05))

    # Allow our thread to exit
    evt.set()

  def testExecuteForever(self):
    evt = threading.Event()
    self.method.side_effect = evt.set
    interval = None
    try:
      interval = timeouts.ExecuteForever(self.method, 1)
      self.assertTrue(interval.running)
      self.assertTrue(evt.wait(2))
    finally:
      if interval:
        interval.Stop()

  def testJoinInterval(self):
    try:
      interval = timeouts.ExecuteForever(self.method, .01)
      # Ha it's really hard to test that we slept 3 seconds
      # But at least this exercises the code path
      start = time.time()
      self.assertTrue(interval.Join(.03))
      self.assertGreater(time.time() - start, .03)
    finally:
      if interval:
        interval.Stop()

  def testExecuteUntilFalse(self):
    self.method.side_effect = [True, True, False]
    interval = None
    try:
      interval = timeouts.ExecuteUntilFalse(self.method, .01)
      interval.Join(5)
      self.assertEquals(self.method.call_count, 3)
    finally:
      if interval:
        interval.Stop()


class TestRetry(googletest.TestCase):

  def setUp(self):
    self.method = mock.Mock()
    self.raises = mock.Mock(side_effect=ValueError)

  def testRetryUntilValid(self):
    self.method.side_effect = [1, 2, 3, 4, 5]
    timeouts.RetryUntilValidOrLimitReached(
        self.method, 7, lambda r: r == 3, sleep_s=.01)
    self.assertEquals(3, self.method.call_count)

  def testRetryUntilNotNone(self):
    self.method.side_effect = [None, None, None, 1]
    timeouts.RetryUntilNotNoneOrLimitReached(
        self.method, 6, sleep_s=.01)
    self.assertEquals(4, self.method.call_count)

  def testLimitAssertion(self):
    self.assertRaises(AssertionError,
                      timeouts.RetryUntilTrueOrLimitReached,
                      self.raises, 0)

  def testMethodCalledOnlyOnce(self):
    timeouts.RetryUntilTrueOrLimitReached(self.method, 1)
    self.method.assert_called_once_with()

  def testMethodRetried(self):
    self.method.return_value = False
    start = time.time()
    result = timeouts.RetryUntilTrueOrLimitReached(self.method, 3, .01)
    self.assertGreater(time.time() - start, .02)
    self.assertFalse(result)
    self.assertEquals(3, self.method.call_count)

  def testMethodRetriedExceptions(self):
    start = time.time()
    self.assertRaises(ValueError,
                      timeouts.RetryUntilTrueOrLimitReached,
                      self.raises, 3, .01, ValueError)
    self.assertGreater(time.time() - start, .02)
    self.assertEquals(3, self.raises.call_count)

  def testMethodUncaughtExceptions(self):
    self.assertRaises(ValueError,
                      timeouts.RetryUntilTrueOrLimitReached,
                      self.raises, 3, .01, KeyError)
    self.assertEquals(1, self.raises.call_count)

  def testMethodOnlyOnceException(self):
    self.assertRaises(ValueError,
                      timeouts.RetryUntilTrueOrLimitReached,
                      self.raises, 1, ValueError)
    self.raises.assert_called_once_with()

  def testMethodExitedEarlyIfTrue(self):
    self.method.side_effect = [False, True]
    result = timeouts.RetryUntilTrueOrLimitReached(self.method, 3, 0)
    self.assertTrue(result)
    self.assertEquals(2, self.method.call_count)

  def testRetryHelper(self):
    helper = timeouts.RetryHelper(3)
    asserts = [self.assertTrue] * 3 + [self.assertFalse]
    for method in asserts:
      method(helper.RetryIfPossible())


if __name__ == '__main__':
  googletest.main()
