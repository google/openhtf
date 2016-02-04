"""Output module for outputting to JSON."""

import oath2client.client

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

  # pylint: disable=invalid-name
  def __call__(self, test_record):
    assert self.filename_pattern, 'filename_pattern required'
    as_dict = util.convert_to_dict(test_record)
    with open(self.filename_pattern % as_dict, 'w') as f:
      f.write(self.encode(as_dict))
  # pylint: enable=invalid-name


class OutputToTestRunProto(object):
  """Return an output callback that writes mfg-inspector TestRun Protos.

  An example filename_pattern might be:
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(openhtf.OutputToTestRunProto(
        '/data/test_records/%(dut_id)s.%(start_time_millis)s'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.
  """

  def __init__(self, filename_pattern):
    self.filename_pattern = filename_pattern

  def __call__(self, test_record):
    as_dict = util.convert_to_dict(test_record)
    with open(self.filename_pattern % as_dict, 'w') as f:
      f.write(mfg_inspector.TestRunFromTestRecord(
          test_record).SerializeToString())


class OutputToMfgInspector(object):
  """Generate a mfg-inspector TestRun proto and upload it.

  Create an output callback to upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).
  """

  TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
  SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'
  DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                     'uploads/quantum_upload/')

  class _MemStorage(oath2client.client.Storage):
    """Helper Storage class that keeps credentials in memory."""
    def __init__(self):
      self._lock = threading.Lock()
      self._credentials = None

    def acquire_lock(self):
      self._lock.acquire(True)

    def release_lock(self):
      self._lock.release()

    def locked_get(self):
      return self._credentials

    def locked_put(self, credentials):
      self._credentials = credentials

  def __init__(self, user, keydata):
    self.user = user
    self.keydata = keydata

  def __call__(self, test_record):
    credentials = oath2client.client.SignedJwtAssertionCredentials(
        service_account_name=self.user,
        private_key=self.keydata,
        scope=self.SCOPE_CODE_URI,
        user_agent='OpenHTF Guzzle Upload Client',
        token_uri=self.TOKEN_URI)
    credentials.set_store(self._MemStorage())

    testrun = mfg_inspector.TestRunFromTestRecord(
        util.convert_to_dict(test_record))
    try:
      mfg_inspector.UploadTestRun(testrun, self.DESTINATION_URL, credentials)
    except mfg_inspector.UploadFailedError:
      # For now, just log the exception.  Once output is a bit more robust,
      # we can propagate this up and handle it accordingly.
      logging.exception('Upload to mfg-inspector failed!')
=======
    with open((self.filename_pattern + '.text') % as_dict, 'w') as f:
      f.write(text_format.MessageToString(
          mfg_inspector.TestRunFromTestRecord(test_record)))

>>>>>>> origin/proto_output
