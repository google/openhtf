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

# pylint: disable=g-importing-member,g-bad-import-order
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
          'pkg-config --variable prefix protobuf'.split()).strip().decode(
              'utf-8')
    except (subprocess.CalledProcessError, OSError):
      if platform.system() == 'Linux':
        # Default to /usr?
        prefix = '/usr'
      elif platform.system() in ['Mac', 'Darwin']:
        # Default to /usr/local for Homebrew
        prefix = '/usr/local'
      else:
        print('Warning: mfg-inspector output is not fully implemented for '
              'Windows. OpenHTF will be installed without it.')
        self.skip_proto = True

    maybe_protoc = os.path.join(prefix, 'bin', 'protoc')
    if os.path.isfile(maybe_protoc) and os.access(maybe_protoc, os.X_OK):
      self.protoc = maybe_protoc
    else:
      print('Warning: protoc not found at %s' % maybe_protoc)
      print('setup will attempt to run protoc with no prefix.')
      self.protoc = 'protoc'

    self.protodir = os.path.join(prefix, 'include')
    self.indir = os.getcwd()
    self.outdir = os.getcwd()

  def finalize_options(self):
    pass

  def run(self):
    if self.skip_proto:
      print('Skipping building protocol buffers.')
      return

    # Build regular proto files.
    protos = glob.glob(
        os.path.join(self.indir, 'openhtf', 'output', 'proto', '*.proto'))

    if protos:
      print('Attempting to build proto files:\n%s' % '\n'.join(protos))
      cmd = [
          self.protoc,
          '--proto_path',
          self.indir,
          '--proto_path',
          self.protodir,
          '--python_out',
          self.outdir,
      ] + protos
      try:
        subprocess.check_call(cmd)
      except OSError as e:
        if e.errno == errno.ENOENT:
          print('Could not find the protobuf compiler at \'%s\'' % self.protoc)
          if sys.platform.startswith('linux'):
            print('On many Linux systems, this is fixed by installing the '
                  '"protobuf-compiler" and "libprotobuf-dev" packages.')
          elif sys.platform == 'darwin':
            print('On Mac, protobuf is often installed via homebrew.')
        raise
      except subprocess.CalledProcessError:
        print('Could not build proto files.')
        print('This could be due to missing helper files. On many Linux '
              'systems, this is fixed by installing the '
              '"libprotobuf-dev" package.')
        raise
    else:
      print('Found no proto files to build.')


# Make building protos part of building overall.
build.sub_commands.insert(0, ('build_proto', None))

INSTALL_REQUIRES = [
    'attrs>=19.3.0',
    'colorama>=0.3.9,<1.0',
    'contextlib2>=0.5.1,<1.0',
    'dataclasses;python_version<"3.7"',
    'inflection',
    'mutablerecords>=0.4.1,<2.0',
    'oauth2client>=1.5.2,<2.0',
    'protobuf>=3.6.0,<4.0',
    'PyYAML>=3.13',
    'pyOpenSSL>=17.1.0,<18.0',
    'sockjs-tornado>=1.0.3,<2.0',
    'tornado>=4.3,<5.0',
    'typing-extensions',
]


class PyTestCommand(test):  # pylint: disable=missing-class-docstring
  # Derived from
  # https://github.com/chainreactionmfg/cara/blob/master/setup.py
  user_options = [
      ('pytest-args=', None, 'Arguments to pass to py.test'),
      ('pytest-cov=', None, 'Enable coverage. Choose output type: '
       'term, html, xml, annotate, or multiple with comma separation'),
  ]

  def initialize_options(self):
    test.initialize_options(self)
    self.pytest_args = ['test']
    self.pytest_cov = None

  def finalize_options(self):
    test.finalize_options(self)
    self.test_args = []
    self.test_suite = True

  def run_tests(self):
    self.run_command('build_proto')

    import pytest  # pylint: disable=g-import-not-at-top
    cov = []
    if self.pytest_cov is not None:
      outputs = []
      for output in self.pytest_cov.split(','):
        outputs.extend(['--cov-report', output])
      cov = ['--cov', 'openhtf'] + outputs

    sys.argv = [sys.argv[0]]
    print('invoking pytest.main with %s' % (self.pytest_args + cov))
    sys.exit(pytest.main(self.pytest_args + cov))


setup(
    name='openhtf',
    version='1.4.4',
    description='OpenHTF, the open hardware testing framework.',
    author='John Hawley',
    author_email='madsci@google.com',
    maintainer='Joe Ethier',
    maintainer_email='jethier@google.com',
    packages=find_packages(),
    package_data={
        'openhtf': [
            'output/proto/*.proto', 'output/web_gui/dist/*.*',
            'output/web_gui/dist/css/*', 'output/web_gui/dist/js/*',
            'output/web_gui/dist/img/*', 'output/web_gui/*.*'
        ]
    },
    python_requires='>=3.6',
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
        ],
        'update_units': ['xlrd>=1.0.0,<2.0',],
        'serial_collection_plug': ['pyserial>=3.3.0,<4.0',],
        'examples': ['pandas>=0.22.0',],
    },
    tests_require=[
        'absl-py>=0.10.0',
        'pandas>=0.22.0',
        'numpy',
        'pytest>=2.9.2',
        'pytest-cov>=2.2.1',
    ],
)
