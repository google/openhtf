import logging
import time

import openxtf.capabilities as capabilities


class Example(capabilities.BaseCapability):
  """Example of a simple capablility."""

  def TearDown(self):
    logging.info('Tearing down %s', self)

  def DoStuff(self):
    time.sleep(10)
    return 'Did stuff!'
