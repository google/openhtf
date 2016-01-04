"""Output a TestRun proto for mfg-inspector.com"""

import json
import optparse
import threading
import zlib
import httplib2
from oauth2client.client import SignedJwtAssertionCredentials
from oauth2client.client import Storage
import quantum_data_pb2

DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                   'uploads/quantum_upload/')
TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'


# pylint: disable=g-bad-name
class MemStorage(Storage):
  """Storage class that keeps credentials in memory.

  This provides a thread-safe repository which can be used by httplib objects
  associated with an OAuth2Credential object as they fetch and refresh tokens.

  store = MemStorage()
  creds = SignedJwtAssertionCredentials(...)
  creds.set_store(store)

  h = httplib2.Http()
  creds.authorize(h)  # Fetches and stores token for future Http instances.
  """

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
# pylint: enable=g-bad-name


def UploadTestRun(pathname, credentials):
  """Uploads the TestRun at a particular file.

  Args:
    pathname: The pathname of the test run to upload.
    credentials: An OAuth2Credentials object to use for authenticated uploads.
  """

  with open(pathname) as f:
    data = f.read()

  h = httplib2.Http()
  if credentials.access_token_expired:
    credentials.refresh(h)
  credentials.authorize(h)

  test_run_envelope = quantum_data_pb2.TestRunEnvelope()
  compressed = zlib.compress(data)
  test_run_envelope.payload = compressed
  test_run_envelope.payload_type = quantum_data_pb2.COMPRESSED_TEST_RUN
  serialized = test_run_envelope.SerializeToString()

  _, content = h.request(DESTINATION_URL, 'POST', serialized)
  if content.split('\n', 1)[0] == 'OK':
    print 'OK'
  else:
    results = json.loads(content)
    error = results['error']
    print error

def main():
  parser = optparse.OptionParser()
  parser.add_option('-k', '--key', dest='key', help='oauth key')
  parser.add_option('-u', '--user', dest='user', help='oauth user')
  options, _ = parser.parse_args()

  key = options.key
  user = options.user
  path = options.path

  with open(key) as f:
    keydata = f.read()

  credentials = SignedJwtAssertionCredentials(
      service_account_name=user,
      private_key=keydata,
      scope=SCOPE_CODE_URI,
      user_agent='Guzzle Upload Client',
      token_uri=TOKEN_URI)
  credentials.set_store(MemStorage())

  UploadTestRun(path, credentials)

