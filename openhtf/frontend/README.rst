OpenHTF Client
==============

Pronounced OX this is the client for the openhtf frontend.

How to work on the client
=======================
This package uses pip/virtualenv for the python code and npm to manage the build
the client and its dependencies.

What is NPM?
-------------------------
[NPM](https://www.npmjs.com/) is the nodejs package manager and is often used
to install javascript tools which can be used for building and working with
javascript.  It requires nodejs to work, specifically the nodejs-legacy package
which installs nodejs and a symlink from /usr/bin/nodejs to /usr/bin/node for
compabilitiy reasons.

    apt-get install nodejs-legacy npm

Npm has the concept of global and package dependencies.  npm install -g <package>
installs a package to your machines global package repository.  This will usually
make it available on the command line.  When installing locally npm installs into
a `node_modules` directory which is added to the path.  If you're writing an npm
package it's possible to get it to load modules out of this directory pretty easily.

*IMPORTANT*: Once you install npm you need to upgrade NPM since the debian one is
old as dirt (like 1.x vs 2.x).  To update npm run:

    npm install -g npm

And what about pip?
--------------------------
Pip is the python package manager, it and virtualenv (a way to isolate python
dependencies need to be installed to get going).  To get started with pip:

    sudo apt-get install python-pip
    sudo pip install --upgrade pip
    sudo pip install virtualenv

Pip installs requirements (dependencies) from pypi (the python package index).
It can use a _requirements.txt_ file to know which packages to install.
Typically this file points at hosted package names in pypi to install but it
can also install local packages in development mode (using the -e flag).  This
causes pip to install the dependency using symlinks from the filesystem so
changes made to those files are instantly reflected, we use this extensively.

Getting Started and Initialization
----------------------
This package uses virtualenv, none of the deps nor virtualenv environment is
checked in so you'll need to install it yourself.  As such you'll need to do the
following one-time initialization to setup your virtualenv.

1. virtualenv --no-site-packages venv
2. source ./venv/bin/activate
3. pip install -r requirements.txt  # installs local packages to the env in devmode
4. cd client
5. npm install  # sets up javascript tools

One time build steps
++++++++++++++++++++++

Several of the files used are generated ones, namely the js protobuf definitions
we use in the client.  These files are not built during the normal client build
process since they rarely change.  I recommend you build this now (READ IMPORTANT
NOTE FIRST):

    npm run build:proto

*IMPORTANT*
We use pbjs to build the js version of our protocol buffers and it has a bug!
I've submitted a pull request to fix this bug but until that happens you *MUST*
modify the installed verison of pbjs to generate the js proto.  In the interim
I've just left the generated code checked-in as a convenience so it's okay to
skip this step and use the already generated file.

If you need to regenerate the protobuf file, the pull request
is here https://github.com/dcodeIO/ProtoBuf.js/issues/222 and the two line diff
you need to apply to ./node_modules/protobufjs/cli/pbjs/targets/json.js is
[here](https://github.com/alusco/ProtoBuf.js/commit/5c64f2f7d5220fd1c8a9f28973b6c964db376bbc)
you can ignore changes to the tests so it only requires modifying one file.

There's unfortunately no way to use pbjs how we're using it and workaround this
pretty fundament bug.

Developing and Building The Client
--------------------------
The client builds and packages a single html, javascript, and two css files
and outputs them to it's dist/ directory.  We use npm to build and run tests
and do development.  The contents of the dist/ directory are symlinked into
the pip package under *oxc/static*.

There's more notes below on how to run the client but it's important to note
that when developing you *must* run *npm run build* once before trying to
run the frontend otherwise it won't have any client files to serve.  If you're
installing the package via setup.py it wil run this for you.

The full list of commands that npm can invoke is in package.json under the
scripts header.  This is an arbitrary key to shell command mapping that makes
it so `npm run <name>` will invoke the corresponding command.  In many cases
these are tools we've installed with npm.

So common commands to be aware of:

- `npm run build` is responsible for building the javascript using a tool
  browserify for the js and stylus for the css and copying it to the dist/
  directory.
- `npm run watch` uses a similar mechanism to monitor all files in the client
  directory for changes and rebuild the output each time a change is made.
  Use this for developing since it also includes source maps and other
  helpful debug things.
- `npm run test` Invokes karma to run tests in a single run. You can run
  `test:debug` which invokes karma in watching, interactive mode allowing
  tests to be debugged in chrome and rerun after each change. There's also
  `test:watch` which runs karma in auto-watch mode non-interactively.
- `npm run start` or `npm start` will run the frontend as a convenience.
