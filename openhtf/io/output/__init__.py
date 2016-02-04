"""Output module for outputting to JSON."""

import oauth2client.client
import threading

from openhtf import util
from openhtf.io.output import mfg_inspector

OutputToJSON = json_factory.OutputToJSON


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


class UploadToMfgInspector(object):
  """Generate a mfg-inspector TestRun proto and upload it.

  Create an output callback to upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).
  """

  TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
  SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'
  DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                     'uploads/quantum_upload/')

  class _MemStorage(oauth2client.client.Storage):
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
    credentials = oauth2client.client.SignedJwtAssertionCredentials(
        service_account_name=self.user,
        private_key=self.keydata,
        scope=self.SCOPE_CODE_URI,
        user_agent='OpenHTF Guzzle Upload Client',
        token_uri=self.TOKEN_URI)
    credentials.set_store(self._MemStorage())

    testrun = mfg_inspector.TestRunFromTestRecord(test_record)
    try:
      mfg_inspector.UploadTestRun(testrun, self.DESTINATION_URL, credentials)
    except mfg_inspector.UploadFailedError:
      # For now, just log the exception.  Once output is a bit more robust,
      # we can propagate this up and handle it accordingly.
      logging.exception('Upload to mfg-inspector failed!')
