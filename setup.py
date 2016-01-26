# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Setup script for OpenHTF."""

import os
import sys

from distutils.command.clean import clean
from setuptools import find_packages
from setuptools import setup
from setuptools.command.test import test


class CleanCommand(clean):
  """Custom logic for the clean command."""

  def run(self):
    clean.run(self)
    targets = [
        './dist',
        './*.egg-info',
        './openhtf/proto/*_pb2.py',
        '**/*.pyc',
        '**/*.tgz',
    ]
    os.system('rm -vrf %s' % ' '.join(targets))


requires = [  # pylint: disable=invalid-name
    'contextlib2==0.4.0',
    'enum34==1.1.2',
    'Flask==0.10.1',
    'inotify==0.2.4',
    'libusb1==1.3.0',
    'M2Crypto==0.22.3',
    'MarkupSafe==0.23',
    'mutablerecords==0.2.6',
    'pyaml==15.3.1',
    'python-gflags==2.0',
    'PyYAML==3.11',
    'Rocket==1.2.4',
    'singledispatch==3.4.0.3',
    'Werkzeug==0.10.4',
]


class PyTestCommand(test):
  # Derived from
  # https://github.com/chainreactionmfg/cara/blob/master/setup.py
  user_options = [
      ('pytest-args=', None, 'Arguments to pass to py.test'),
      ('pytest-cov=', None, 'Enable coverage. Choose output type: '
       'term, html, xml, annotate, or multiple with comma separation'),
  ]

  def initialize_options(self):
    test.initialize_options(self)
    self.pytest_args = 'test'
    self.pytest_cov = None

  def finalize_options(self):
    test.finalize_options(self)
    self.test_args = []
    self.test_suite = True

  def run_tests(self):
    import pytest
    cov = ''
    if self.pytest_cov is not None:
      outputs = ' '.join('--cov-report %s' % output
                         for output in self.pytest_cov.split(','))
      cov = ' --cov openhtf ' + outputs
    sys.exit(pytest.main(self.pytest_args + cov))


setup(
    name='openhtf',
    version='1.0',
    description='OpenHTF, the open hardware testing framework.',
    author='John Hawley',
    author_email='madsci@google.com',
    maintainer='Joe Ethier',
    maintainer_email='jethier@google.com',
    packages=find_packages(exclude='example'),
    cmdclass={
        'clean': CleanCommand,
        'test': PyTestCommand,
    },
    install_requires=requires,
)
