"""Module for outputting test record to JSON-formatted files."""

import base64
import json
from typing import Any, BinaryIO, Callable, Dict, Iterator, Text, Union

from openhtf.core import test_record
from openhtf.output import callbacks
from openhtf.util import data


class TestRecordEncoder(json.JSONEncoder):

  def default(self, obj: Any) -> Any:
    if isinstance(obj, test_record.Attachment):
      dct = obj._asdict()
      dct['data'] = base64.standard_b64encode(obj.data).decode('utf-8')
      return dct
    return super(TestRecordEncoder, self).default(obj)


def convert_test_record_to_json(
    test_rec: test_record.TestRecord,
    inline_attachments: bool = True, allow_nan: bool = False
    ) -> Dict[Text, Any]:
  """Convert the test record to a JSON object.

  Args:
    test_rec: The test record to convert.
    inline_attachments: Whether attachments should be included inline in the
      output. Set to False if you expect to have large binary attachments. If
      True (the default), then attachments are base64 encoded to allow for
      binary data that's not supported by JSON directly.
    allow_nan: If False, out of range float values will raise ValueError.

  Returns:
    The test record encoded as JSON objects.
  """
  as_dict = data.convert_to_base_types(test_rec, json_safe=(not allow_nan))
  if inline_attachments:
    for phase, original_phase in zip(as_dict['phases'], test_rec.phases):
      for name, attachment in original_phase.attachments.items():
        phase['attachments'][name] = attachment
  return as_dict


def stream_json(
    encoded_test_rec: Dict[Text, Any], allow_nan: bool = False, **kwargs
) -> Iterator[Text]:
  """Convert the JSON object encoded test record into a stream of strings.

  Args:
    encoded_test_rec: The JSON converted test record.
    allow_nan: If False, out of range float values will raise ValueError.
    **kwargs: Additional arguments to be passed to the JSON encoder.

  Returns:
    Iterable of JSON strings.
  """
  json_encoder = TestRecordEncoder(allow_nan=allow_nan, **kwargs)

  # The iterencode return type in typeshed for PY2 is wrong; not worried about
  # fixing it as we are droping PY2 support soon.
  return json_encoder.iterencode(encoded_test_rec)  # pytype: disable=bad-return-type


class OutputToJSON(callbacks.OutputToFile):
  """Return an output callback that writes JSON Test Records.

  Example filename_patterns might be:
    '/data/test_records/{dut_id}.{metadata[test_name]}.json', indent=4)) or
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'
  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.add_output_callback(openhtf.output.callbacks.OutputToJSON(
        '/data/test_records/{dut_id}.{metadata[test_name]}.json'))
  """

  def __init__(self, filename_pattern_or_file: Union[Text, Callable[..., Text],
                                                     BinaryIO],
               inline_attachments: bool = True,
               allow_nan: bool = False, **json_kwargs: Any):
    """Constructor.

    Args:
      filename_pattern_or_file: A format string specifying the filename to write
        to, will be formatted with the Test Record as a dictionary.  May also be
        a file-like object to write to directly.
      inline_attachments: Whether attachments should be included inline in the
        output. Set to False if you expect to have large binary attachments. If
        True (the default), then attachments are base64 encoded to allow for
        binary data that's not supported by JSON directly.
      allow_nan: If False, out of range float values will raise ValueError.
      **json_kwargs: Additional arguments to be passed to the JSON encoder.
    """
    super(OutputToJSON, self).__init__(filename_pattern_or_file)
    self.inline_attachments = inline_attachments
    self.allow_nan = allow_nan
    self._json_kwargs = json_kwargs

  def serialize_test_record(self, test_rec: test_record.TestRecord
                            ) -> Iterator[Text]:
    encoded = convert_test_record_to_json(
        test_rec, inline_attachments=self.inline_attachments,
        allow_nan=self.allow_nan)
    return stream_json(encoded, allow_nan=self.allow_nan,
                       **self._json_kwargs)
