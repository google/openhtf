# Copyright 2017 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Helper functions for downloading and working with files."""

import logging
import os
import shutil
import zipfile

try:  # for 2/3 compatibility
  import urllib2 as urllib  # pylint: disable=g-import-not-at-top
except NameError:
  import urllib.request as urllib  # pylint: disable=g-import-not-at-top

_LOG = logging.getLogger(__name__)


def download(url, fd):
  """Downloads a URL with HTTP to a file descriptor."""
  try:
    request = urllib.urlopen(url)  # Python 2 does not support with blocks
    shutil.copyfileobj(request, fd)
  finally:
    try:
      request.close()
    except NameError:
      pass


def download_file(url, directory):
  with open(os.path.join(directory, url.rsplit('/', 1)[-1]), 'wb') as fd:
    download(url, fd)
    return fd.name


def download_files(remote_paths, host, port, directory, logger=_LOG):
  """Downloads files from http://host:port/path; returns list of local paths."""
  if not os.path.exists(directory):
    os.makedirs(directory)

  local_files = []
  for remote_path in remote_paths:
    url = 'http://{}:{}/{}'.format(host, port, remote_path)
    logger.debug('Downloading "%s"', url)
    local_files.append(download_file(url, directory))
    logger.debug('Downloaded "%s" to "%s"', remote_path, local_files[-1])

  return local_files


def zip_files(files, zip_path, delete_original=False):
  """Compresses a list of files into a zip archive, storing by basename only."""
  with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, True) as zip_file:
    for path in files:
      zip_file.write(path, os.path.basename(path))

      if delete_original:
        os.remove(path)
