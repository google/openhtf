"""Module for outputting test record to JSON-formatted files."""

import base64
import output_to_file
from json import JSONEncoder
from openhtf.exe import test_state
from openhtf.util import data


class OutputToJSON(JSONEncoder, output_to_file.OutputToFile):
  """Return an output callback that writes JSON Test Records.

  Example filename_patterns might be:
    '/data/test_records/{dut_id}.{metadata[test_name]}.json', indent=4)) or
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(openhtf.OutputToJson(
        '/data/test_records/{dut_id}.{metadata[test_name]}.json'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.  May also be a
      file-like object to write to directly.
    inline_attachments: Whether attachments should be included inline in the
      output. Set to False if you expect to have large binary attachments. If
      True (the default), then attachments are base64 encoded to allow for
      binary data that's not supported by JSON directly.
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

  def GetData(self):
    self.data = self.encode(self.test_record_dict)

  # pylint: disable=invalid-name
  def __call__(self, test_record):
    self.test_record = test_record
    assert self.filename_pattern, 'filename_pattern required'
    if self.inline_attachments:
      self.test_record_dict = data.ConvertToBaseTypes(test_record)
      for phase in self.test_record_dict['phases']:
        for value in phase['attachments'].itervalues():
          value['data'] = base64.standard_b64encode(value['data'])
    else:
      self.test_record_dict = data.ConvertToBaseTypes(test_record, ignore_keys='attachments')
    self.Save()
