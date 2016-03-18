"""Module for outputting test record to JSON-formatted files."""

from json import JSONEncoder

from openhtf import util
from openhtf.exe import test_state


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
    inline_attachments: Whether attachments should be included inline in the
      output.  Set to False if you expect to have large binary attachments.
  """

  def __init__(self, filename_pattern=None, inline_attachments=True, **kwargs):
    super(OutputToJSON, self).__init__(**kwargs)
    self.filename_pattern = filename_pattern
    self.inline_attachments = inline_attachments

  def default(self, obj):
    if isinstance(obj, BaseException):
      # Just repr exceptions.
      return repr(obj)
    return super(OutputToJSON, self).default(obj)

  # pylint: disable=invalid-name
  def __call__(self, test_record):
    assert self.filename_pattern, 'filename_pattern required'
    if self.inline_attachments:
      as_dict = util.ConvertToBaseTypes(test_record)
    else:
      as_dict = util.ConvertToBaseTypes(test_record, ignore_keys='attachments')
    with open(self.filename_pattern % as_dict, 'w') as f:
      f.write(self.encode(as_dict))
  # pylint: enable=invalid-name
