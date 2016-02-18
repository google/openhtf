"""Module for uploading JSON-formatted test record files to server."""

import os
import shutil
import logging
import requests

from json import JSONEncoder
from openhtf import conf
from openhtf.io.output.json_factory import OutputToJSON

conf.Declare('project', 'project name')
conf.Declare('data_server', 'data server')
_LOG = logging.getLogger(__name__)

class UploadJSON(OutputToJSON):
  """Return an output callback that upload JSON Test Records to data server.

  An example filename_pattern might be:
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(UploadJson(
        '/data/test_records/%(dut_id)s.%(start_time_millis)s'))
  
    in config.yaml:
       data_server:  http://your_data_server_entry
  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.
    inline_attachments: Whether attachments should be included inline in the
      output.  Set to False if you expect to have large binary attachments.
  """

  def __init__(self, filename_pattern=None, inline_attachments=True, **kwargs):
    super(UploadJSON, self).__init__(filename_pattern, inline_attachments, **kwargs)
    self.headers = {'Accept' : 'application/json',
                 'Content-Type' : 'application/json'}
    self.data_server = None
    self.file_dir = filename_pattern.split('%')[0]
    self.save_dir = None

  # pylint: disable=invalid-name
  def __call__(self, test_record):
    super(UploadJSON, self).__call__(test_record)
  # pylint: enable=invalid-name
    if not self.data_server:
      config = conf.Config()
      project = config.project
      server = config.data_server
   
      if server:
        self.data_server = server + project
      else:
        raise ValueError('No data_server set')
    
    for f in self.IterFile(self.file_dir):
      resp = requests.post(self.data_server, data=open(f, 'rb'),
                             headers=self.headers)
      if resp.status_code == 200:
        if not self.save_dir:
          self.save_dir = os.path.join(self.file_dir, 'saved')
          os.mkdir(self.save_dir)
        shutil.move(f, self.save_dir)
        #os.remove(f)  //keep the record for the time being
        _LOG.info('Test record successfully loaded to servers.')
      else:
        _LOG.warning('Error on upload test_record to server rc:%d, file:%s',
                     resp.status_code, f)
  
  def IterFile(self, file_dir):
    """ Iterate the files under the given dir """ 
    files = os.listdir(file_dir)
    for f in os.listdir(file_dir):
      cur_file = os.path.join(file_dir, f)
      if os.path.isfile(cur_file):
        yield cur_file
