"""Output module for outputting to JSON."""

from json import JSONEncoder
from openhtf import conf
from openhtf import util
from openhtf.exe import test_state
from openhtf.io.output import mfg_inspector

from google.protobuf import text_format


class OutputToJSON(JSONEncoder):
  """Return an output callback that writes JSON Test Records.

  An example filename_pattern might be:
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(openhtf.OutputToJson(
        '/data/test_records/%(dut_id)s.%(start_time_millis)s'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.
  """

  def __init__(self, filename_pattern, **kwargs):
    super(OutputToJSON, self).__init__(**kwargs)
    self.filename_pattern = filename_pattern

  def default(self, obj):
    # Handle a few custom objects that end up in our output.
    if isinstance(obj, BaseException):
      # Just repr exceptions.
      return repr(obj)
    if isinstance(obj, conf.Config):
      return obj.dictionary
    if obj in test_state.TestState.State:
      return str(obj)
    return super(OutputToJSON, self).default(obj)

  def __call__(self, test_record):  # pylint: disable=invalid-name
    as_dict = util.convert_to_dict(test_record)
    with open(self.filename_pattern % as_dict, 'w') as f:  # pylint: disable=invalid-name
      f.write(self.encode(as_dict))


class OutputToTestRunProto(object):

  def __init__(self, filename_pattern):
    self.filename_pattern = filename_pattern

  def __call__(self, test_record):
    as_dict = util.convert_to_dict(test_record)
    with open(self.filename_pattern % as_dict, 'w') as f:
      f.write(mfg_inspector.TestRunFromTestRecord(
          test_record).SerializeToString())
    with open((self.filename_pattern + '.text') % as_dict, 'w') as f:
      f.write(text_format.MessageToString(
          mfg_inspector.TestRunFromTestRecord(test_record)))

