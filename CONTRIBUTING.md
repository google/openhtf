# How To Contribute

We welcome patches and contribution to OpenHTF. It's as easy as submitting a
pull request with your changes in order to kick off the review process. But
first, please read through the rest of this doc.


## Legal Requirements
In order to become a contributor, you first need to sign the appropriate
[Contributor License Agreement](https://cla.developers.google.com/clas).


## Managing Dependencies
The OpenHTF codebase is set up to use pip/virtualenv to manage dependencies.

Pip is the python package manager, while virtualenv is a tool to isolate python
environments. You'll need both in order to work with the OpenHTF codebase.

Pip installs requirements (dependencies) from pypi (the python package index).
It can use a requirements.txt file to know which packages to install. Typically
this file points at hosted package names in pypi to install but it can also
install local packages in development mode (using the -e flag).  This causes pip
to install the dependency using symlinks from the filesystem so changes made to
those files are instantly reflected.

By design, virtualenv and OpenHTF's python dependencies are not included in the
repository. The following steps set up a new virtualenv environment and install
OpenHTF's dependencies into it using pip (steps 5-7 below).


## Dev Environment Setup Steps
To set up an OpenHTF dev environment, follow the steps below.

### Linux
0. Clone into the git repo.
1. `sudo apt-get install python-pip swig libssl-dev python-dev libffi-dev protobuf-compiler`
2. `sudo pip install --upgrade pip`
3. `sudo pip install virtualenv`
4. `(cd to openhtf directory)`
5. `virtualenv venv`
6. `. venv/bin/activate`
7. `python setup.py develop`
