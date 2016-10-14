import openhtf
import openhtf.plugs as plugs
from openhtf.util import conf


class ExamplePlug(plugs.BasePlug):   # pylint: disable=no-init
  """Simple Counter Plug."""

  def __init__(self):
    self.count = 0

  def increment(self):
    """Increment our value, return the previous value."""
    self.count += 1

class ExamplePlug2(plugs.BasePlug):   # pylint: disable=no-init
  """Simple Counter Plug."""

  def __init__(self):
    self.count = 0

  def echo(self):
    print "hello world!"

  def increment(self):
    """Increment our value, return the previous value."""
    self.count += 1

@plugs.plug(test_plug=ExamplePlug)
def phase_repeat(test, test_plug):
  test_plug.increment()
  print 'phase_repeat run %s times' % test_plug.count
  if test_plug.count < 20:
    return openhtf.PhaseResult.REPEAT

@openhtf.PhaseOptions(repeat_limit=5)
@plugs.plug(test_plug=ExamplePlug2)
def phase_repeat_with_limit(test, test_plug):
  test_plug.increment()
  print 'phase_repeat_5 run %s times' % test_plug.count
  if test_plug.count < 20:
    return openhtf.PhaseResult.REPEAT

if __name__ == '__main__':
  test = openhtf.Test(phase_repeat, phase_repeat_with_limit)
  test.execute(test_start=lambda: 'RepeatDutID')


