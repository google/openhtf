"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.threads."""

import threading

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import threads


class ExceptionThreadTest(googletest.TestCase):
  """Tests ExceptionSafeThread."""

  def setUp(self):
    self.thread = StubExThread()

  def testFinishCalled(self):
    self.thread.start()
    self.thread.join(5)

    self.assertFalse(self.thread.isAlive(), 'Thread did not finish')

    self.assertIsNone(self.thread.error)
    self.assertFalse(self.thread.e)
    self.assertTrue(self.thread.finished)

  def testThreadException(self):
    self.thread.should_raise = ValueError
    self.thread.start()
    self.thread.join(10)

    self.assertFalse(self.thread.isAlive(), 'Thread did not finish')
    self.assertIsInstance(self.thread.e, ValueError)
    self.assertIsNone(self.thread.error)


class StubExThread(threads.ExceptionSafeThread):

  def __init__(self, *args, **kwargs):
    super(StubExThread, self).__init__(args=args, kwargs=kwargs)

    self.should_raise = False
    self.proc = self.e = self.finished = False
    self.args = self.kwargs = self.error = None

  def _ThreadProc(self, *args, **kwargs):
    if self.proc:
      self.error = 'Proc called more than once.'
    self.proc = True
    self.args = args
    self.kwargs = kwargs

    if self.should_raise:
      raise self.should_raise()

  def _ThreadException(self, e):
    if self.e:
      self.error = 'Exception called more than once.'
    self.e = e

  def _ThreadFinished(self):
    if self.finished:
      self.error = 'Finished called more than once.'
    self.finished = True


class KillableThread(googletest.TestCase):

  class Victim(threads.KillableThread):

    def __init__(self):
      super(type(self), self).__init__()
      self.ready = threading.Event()

    def _ThreadProc(self):
      self.ready.set()
      while True:
        pass

  def testKillsThread(self):
    victim = self.Victim()
    victim.start()
    self.assertTrue(victim.ready.wait(10))
    victim.Kill()
    victim.join(10)
    self.assertFalse(victim.is_alive())


class Looper(googletest.TestCase):

  class Thread(threading.Thread):

    def __init__(self):
      super(Looper.Thread, self).__init__()
      self.count = 0

    @threads.Loop
    def run(self):
      self.count += 1
      if self.count == 3:
        raise RuntimeError()

  def testLooper(self):
    t = self.Thread()
    t.start()
    t.join(10)
    self.assertEquals(3, t.count)

  def testOnce(self):
    t = self.Thread()
    t.run.once(t)
    self.assertEquals(1, t.count)

if __name__ == '__main__':
  googletest.main()
