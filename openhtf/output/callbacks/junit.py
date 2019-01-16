"""Module for outputting test record to JUNIT-formatted files."""

import base64
from junit_xml import TestSuite, TestCase

from openhtf.output import callbacks
from openhtf.util import data
import six


class OutputToJUNIT(callbacks.OutputToFile):
  """Return an output callback that writes JSON Test Records.
  Example filename_patterns might be:
    '/data/test_records/{dut_id}.{metadata[test_name]}.json', indent=4)) or
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'
  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.add_output_callback(openhtf.output.callbacks.OutputToJson(
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
    super(OutputToJUNIT, self).__init__(filename_pattern)
    self.inline_attachments = inline_attachments

    # Conform strictly to the JSON spec by default.
    kwargs.setdefault('allow_nan', False)
    self.allow_nan = kwargs['allow_nan']
    self.test_cases = []

  def serialize_test_record(self, test_record):
    dict_test_record = self.convert_to_dict(test_record)

    for phase in dict_test_record["phases"]:
      output = []
      for _, phase_data in phase["measurements"].items():

        output.extend(["name: " + phase_data["name"],
                       "validators: " + str(phase_data["validators"]),
                       "measured_value: " + str(phase_data["measured_value"]),
                       "outcome: " + phase_data["outcome"], "\n"])

      if phase["outcome"] == "PASS":
        self.test_cases.append(
            TestCase(phase["name"],
                     dict_test_record["dut_id"] + "." +
                     dict_test_record["metadata"]["test_name"],
                     (phase["end_time_millis"] -
                      phase["start_time_millis"]) * 1000,
                     "\n".join(output),
                     ''))
      else:
        self.test_cases.append(
            TestCase(phase["name"],
                     dict_test_record["dut_id"] + "." +
                     dict_test_record["metadata"]["test_name"],
                     (phase["end_time_millis"] -
                      phase["start_time_millis"]) * 1000,
                     "\n".join(output),
                     ''))

    return TestSuite.to_xml_string([TestSuite("Test", self.test_cases)])

  def convert_to_dict(self, test_record):
    as_dict = data.convert_to_base_types(test_record,
                                         json_safe=(not self.allow_nan))

    if self.inline_attachments:
      for phase, original_phase in zip(as_dict['phases'], test_record.phases):
        for name, attachment in six.iteritems(phase['attachments']):
          original_data = original_phase.attachments[name].data
          attachment['data'] = base64.standard_b64encode(
              original_data).decode('utf-8')
    return as_dict
