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

import errno
import glob
import os
import platform
import subprocess
import sys

from distutils.command.build import build
from distutils.command.clean import clean
from distutils.cmd import Command
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
        './openhtf/output/proto/*_pb2.py',
        './openhtf/**/*.pyc',
    ]
    os.system('shopt -s globstar; rm -vrf %s' % ' '.join(targets))


class BuildProtoCommand(Command):
  """Custom setup command to build protocol buffers."""
  description = 'Builds the proto files into python files.'
  user_options = [('protoc=', None, 'Path to the protoc compiler.'),
                  ('protodir=', None, 'Path to protobuf install.'),
                  ('indir=', 'i', 'Directory containing input .proto files.'),
                  ('outdir=', 'o', 'Where to output .py files.')]

  def initialize_options(self):
    self.skip_proto = False
    try:
      prefix = subprocess.check_output(
          'pkg-config --variable prefix protobuf'.split()).strip()
    except (subprocess.CalledProcessError, OSError):
      if platform.system() == 'Linux':
        # Default to /usr?
        prefix = '/usr'
      elif platform.system() in ['Mac', 'Darwin']:
        # Default to /usr/local for Homebrew
        prefix = '/usr/local'
      else:
        print ('Warning: mfg-inspector output is not fully implemented for '
               'Windows. OpenHTF will be installed without it.')
        self.skip_proto = True

    self.protoc = os.path.join(prefix, 'bin', 'protoc')
    self.protodir = os.path.join(prefix, 'include')
    self.indir = os.path.join(os.getcwd(), 'openhtf', 'output', 'proto')
    self.outdir = os.path.join(os.getcwd(), 'openhtf', 'output', 'proto')

  def finalize_options(self):
    pass

  def run(self):
    if self.skip_proto:
      print 'Skipping building protocol buffers.'
      return
    # Build regular proto files.
    protos = glob.glob(os.path.join(self.indir, '*.proto'))
    if protos:
      print 'Attempting to build proto files:\n%s' % '\n'.join(protos)
      cmd = [
          self.protoc,
          '--proto_path', self.indir,
          '--proto_path', self.protodir,
          '--python_out', self.outdir,
      ] + protos
      try:
        subprocess.check_call(cmd)
      except OSError as e:
        if e.errno == errno.ENOENT:
          print 'Could not find the protobuf compiler at %s' % self.protoc
          print ('On many Linux systems, this is fixed by installing the '
                 '"protobuf-compiler" and "libprotobuf-dev" packages.')
        raise
      except subprocess.CalledProcessError:
        print 'Could not build proto files.'
        print ('This could be due to missing helper files. On many Linux '
               'systems, this is fixed by installing the '
               '"libprotobuf-dev" package.')
        raise
    else:
      print 'Found no proto files to build.'


# Make building protos part of building overall.
build.sub_commands.insert(0, ('build_proto', None))


INSTALL_REQUIRES = [
    'contextlib2>=0.5.1,<1.0',
    'enum34>=1.1.2,<2.0',
    'mutablerecords>=0.4.1,<2.0',
    'oauth2client>=1.5.2,<2.0',
    'protobuf>=2.6.1,<3.0',
    'pyaml>=15.3.1,<16.0',
    'pyOpenSSL>=17.1.0,<18.0',
    'sockjs-tornado>=1.0.3,<2.0',
    'tornado>=4.3,<5.0',
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
    self.run_command('build_proto')

    import pytest
    cov = ''
    if self.pytest_cov is not None:
      outputs = ' '.join('--cov-report %s' % output
                         for output in self.pytest_cov.split(','))
      cov = ' --cov openhtf ' + outputs

    sys.argv = [sys.argv[0]]
    print('invoking pytest.main with %s' % (self.pytest_args + cov))
    sys.exit(pytest.main(self.pytest_args + cov))


setup(
    name='openhtf',
    version='1.1.0',
    description='OpenHTF, the open hardware testing framework.',
    author='John Hawley',
    author_email='madsci@google.com',
    maintainer='Joe Ethier',
    maintainer_email='jethier@google.com',
    packages=find_packages(exclude='examples'),
    package_data={'openhtf': ['output/web_gui/prebuilt/**/*.*',
                              'output/web_gui/prebuilt/*.*']},
    cmdclass={
        'build_proto': BuildProtoCommand,
        'clean': CleanCommand,
        'test': PyTestCommand,
    },
    install_requires=INSTALL_REQUIRES,
    extras_require={
        'usb_plugs': [
            'libusb1>=1.3.0,<2.0',
            'M2Crypto>=0.22.3,<1.0',
            'python-gflags>=2.0,<3.0',
        ],
        'update_units': [
            'xlrd>=1.0.0,<2.0',
        ],
    },
    setup_requires=[
        'wheel>=0.29.0,<1.0',
    ],
    tests_require=[
        'mock>=2.0.0',
        'pytest>=2.9.2',
        'pytest-cov>=2.2.1',
    ],
)
