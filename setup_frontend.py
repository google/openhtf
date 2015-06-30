from distutils.command.build import build
from distutils.cmd import Command
from setuptools import setup, find_packages
import os
import subprocess

class CustomBuild(build):
  """Custom build which modifies the build setup to build our client."""
  description = "Builds the client javascript."""
  user_options = build.user_options + [
                     ('clientdir=', 'c', 'Location of client directory.'),
                     ('regenproto', 'r', 'True to regenerate the js proto files.'),
                     ('npmpath=', 'n', 'Path to npm')]

  def initialize_options(self):
    self.clientdir = './client'
    self.regenproto = False  # change to true when pbjs is fixed
    self.npmpath = '/usr/local/bin/npm'
    build.initialize_options(self)

  def run(self):
    if self.regenproto:
      subprocess.check_call([self.npmpath, 'run', 'build:proto'],
          cwd=self.clientdir)
    subprocess.check_call([self.npmpath, 'run', 'build'], cwd=self.clientdir)
    build.run(self)

setup(
    name='oxc',
    version='0.0.2',
    author='Alex Lusco',
    author_email='alusco@google.com',
    packages=find_packages('oxc', exclude=['*_test.py']),
    scripts=['bin/frontend.py'],
    license='LICENSE',
    description='The OpenXTF client frontend',
    long_description=open('README.rst').read(),
    install_requires=[
        'flask',
        'python-gflags',
        'Rocket',
        'requests',
        'openxtf'
    ],
    classifers = ('Private :: Do Not Upload',),
    cmdclass={'build': CustomBuild}
)
