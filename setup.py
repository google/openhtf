import glob
import os
import subprocess

from distutils.command.build import build
from distutils.command.clean import clean
from distutils.cmd import Command
from setuptools import find_packages
from setuptools import setup


class build_proto(Command):
  description = "Builds the proto files into python files."""
  user_options = [('grpc-python-plugin=', None, 'Path to the grpc py plugin.'),
                  ('protoc=', None, 'Path to the protoc compiler.'),
                  ('protodir=', None, 'Path to proto files.'),
                  ('outdir=', 'o', 'Where to output .py files.')]

  def initialize_options(self):
    self.grpc_python_plugin = './openxtf/proto/bin/grpc_python_plugin'
    self.protoc = './openxtf/proto/bin/protoc'
    self.protodir = './openxtf/proto'
    self.outdir = './openxtf/proto'

  def finalize_options(self):
    pass

  def run(self):
    # Build regular proto files.
    protos = glob.glob(os.path.join(self.protodir, '*.proto'))
    if protos:
      subprocess.check_call([
          self.protoc,
          '-I', self.protodir,
          '--python_out', self.outdir,
          ] + protos)

    # Build gRPC python proto files.
    # grpc_python_protos = glob.glob(os.path.join(self.protodir,
    #                                             'grpc_python',
    #                                             '*.proto'))
    # if grpc_python_protos:
    #   subprocess.check_call([
    #       self.protoc,
    #       '-I', self.protodir,
    #       '--python_out', os.path.join(self.outdir, 'grpc_python'),
    #       '--grpc_out', os.path.join(self.outdir, 'grpc_python'),
    #       '--plugin=protoc-gen-grpc=%s' % self.grpc_python_plugin,
    #       ] + grpc_python_protos)


# Make our step part of building
build.sub_commands.insert(0, ('build_proto', None))

class clean_proto(clean):

  def run(self):
    clean.run(self)
    files = glob.glob('./openxtf/proto/*_pb2.py*')
    for fname in files:
      os.remove(fname)


setup(name='OpenXTF',
      version='0.9',
      description='Open eXtraneous Testing Framework',
      author='John Hawley',
      author_email='madsci@google.com',
      maintainer='Joe Ethier',
      maintainer_email='jethier@google.com',
      packages=find_packages(exclude='example'),
      cmdclass={'build_proto': build_proto, 'clean': clean_proto}
      )

# setup(name='OpenXTF Example',
#       version='0.9',
#       description='Example test and capability for OpenXTF.',
#       author='John Hawley',
#       author_email='madsci@google.com',
#       packages=['example'],
#       )
