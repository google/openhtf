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


import glob
import os
import subprocess

from distutils.command.build import build
from distutils.command.clean import clean
from distutils.cmd import Command
from setuptools import find_packages
from setuptools import setup


class BuildClientCommand(Command):
  """Build OpenHTF frontend client."""
  description = "Builds the client javascript."""
  user_options = build.user_options + [
      ('clientdir=', 'c', 'Location of client directory.'),
      ('regenproto', 'r', 'True to regenerate the js proto files.'),
      ('npmpath=', 'n', 'Path to npm')]

  def initialize_options(self):
    self.clientdir = './openhtf/frontend/client'
    self.regenproto = False  # change to true when pbjs is fixed
    self.npmpath = '/usr/local/bin/npm'

  def finalize_options(self):
    pass

  def run(self):
    if self.regenproto:
      subprocess.check_call([self.npmpath, 'run', 'build:proto'],
                            cwd=self.clientdir)
    subprocess.check_call([self.npmpath, 'run', 'build'], cwd=self.clientdir)
    build.run(self)


class BuildProtoCommand(Command):
  """Custom setup command to build protocol buffers."""
  description = "Builds the proto files into python files."""
  user_options = [('grpc-python-plugin=', None, 'Path to the grpc py plugin.'),
                  ('protoc=', None, 'Path to the protoc compiler.'),
                  ('protodir=', None, 'Path to proto files.'),
                  ('outdir=', 'o', 'Where to output .py files.')]

  def initialize_options(self):
    self.grpc_python_plugin = './bin/grpc_python_plugin'
    self.protoc = './bin/protoc'
    self.protodir = './openhtf/io/proto'
    self.outdir = './openhtf/io/proto'

  def finalize_options(self):
    pass

  def run(self):
    # Build regular proto files.
    protos = glob.glob(os.path.join(self.protodir, '*.proto'))
    if protos:
      print "Attempting to build regular protos:\n%s" % '\n'.join(protos)
      subprocess.check_call([
          self.protoc,
          '-I', self.protodir,
          '--python_out', self.outdir,
          ] + protos)
    else:
      print "Found no regular protos to build."

    # Build gRPC python proto files.
    grpc_python_protos = glob.glob(os.path.join(self.protodir,
                                                'grpc_python',
                                                '*.proto'))
    if grpc_python_protos:
      print "Attempting to build grpc_python protos:\n%s" % '\n'.join(
          grpc_python_protos)
      subprocess.check_call([
          self.protoc,
          '-I', os.path.join(self.protodir, 'grpc_python'),
          '--python_out', self.outdir,
          '--grpc_out', self.outdir,
          '--plugin=protoc-gen-grpc=%s' % self.grpc_python_plugin,
          ] + grpc_python_protos)
    else:
      print "Found no grpc_python protos to build."


# Make building protos part of building overall.
build.sub_commands.insert(0, ('build_proto', None))


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


requires = [    # pylint: disable=invalid-name
    'contextlib2==0.4.0',
    'enum==0.4.4',
    'Flask==0.10.1',
    'itsdangerous==0.24',
    'Jinja2==2.7.3',
    'libusb1==1.3.0',
    'M2Crypto==0.22.3',
    'MarkupSafe==0.23',
    'protobuf==2.6.1',
    'pyaml==15.3.1',
    'python-gflags==2.0',
    'PyYAML==3.11',
    'Rocket==1.2.4',
    'singledispatch==3.4.0.3',
    'six==1.9.0',
    'Werkzeug==0.10.4',
]


setup(
    name='openhtf',
    version='0.9',
    description='Open Hardware Testing Framework',
    author='John Hawley',
    author_email='madsci@google.com',
    maintainer='Joe Ethier',
    maintainer_email='jethier@google.com',
    packages=find_packages(exclude='example'),
    scripts=['bin/dumpdata.py'],
    cmdclass={
        'build_client': BuildClientCommand,
        'build_proto': BuildProtoCommand,
        'clean': CleanCommand,
    },
    install_requires=requires,
)
