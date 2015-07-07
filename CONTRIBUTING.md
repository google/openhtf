# How To Contribute

We welcome patches and contribution to OpenHTF. It's as easy as submitting a
pull request with your changes in order to kick off the review process. But
first, please read through the rest of this doc.


## Legal Requirements
In order to become a contributor, you first need to sign the appropriate
[Contributor License Agreement](https://cla.developers.google.com/clas).


## Managing Dependencies
The OpenHTF codebase is set up to use pip/virtualenv to manage dependencies for
the python portion (most of the framework itself) and npm to manage javascript
dependencies for the client portion of the included web frontend.


### Python Dependencies
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
OpenHTF's dependencies into it using pip:

1. virtualenv --no-site-packages venv
2. source ./venv/bin/activate
3. pip install -r requirements.txt


### Javascript Dependencies
[NPM](https://www.npmjs.com/) is the nodejs package manager and is often used
to install javascript tools which can be used for building and working with
javascript. It requires nodejs to work, specifically the nodejs-legacy package
which installs nodejs and a symlink from /usr/bin/nodejs to /usr/bin/node for
compabilitiy reasons.

Npm has the concept of global and package dependencies. npm install -g <package>
installs a package to your machines global package repository. This will usually
make it available on the command line. When installing locally npm installs into
a `node_modules` directory which is added to the path. If you're writing an npm
package it's possible to get it to load modules out of this directory pretty
easily.

The included web frontend for OpenHTF has some javascript dependencies that are
not included in the repository. They can be installed using npm:

1. cd openxtf/frontend/client
2. npm install


## One Time Build Steps
Several of the files used are generated ones, namely the js protobuf definitions
we use in the client. These files are not built during the normal client build
process since they rarely change.

*IMPORTANT*
We use pbjs to build the js version of our protocol buffers and it has a bug!
We've submitted a pull request to fix it, but until that happens you must modify
the installed verison of pbjs to generate the js proto. In the interim we've
just left the generated code checked in as a convenience. It's okay to skip this
step and use the already generated file.

If you need to regenerate the protobuf file, the pull request
is here https://github.com/dcodeIO/ProtoBuf.js/issues/222 and the two line diff
you need to apply to ./node_modules/protobufjs/cli/pbjs/targets/json.js is
[here](https://github.com/alusco/ProtoBuf.js/commit/5c64f2f7d5220fd1c8a9f28973b6c964db376bbc).
You can ignore changes to the tests so it only requires modifying one file.

Build the js protobuf with:

    npm run build:proto


## Developing and Building The Client
The client builds and packages a single html, javascript, and two css files
and outputs them to it's dist/ directory. We use npm to build and run tests and
do development. The contents of the dist/ directory are symlinked into the
server directory.

There are more notes below on how to run the client but it's important to note
that when developing you *must* run *npm run build* once before trying to run
the frontend, otherwise it won't have any client files to serve. If you're
installing the openxtf package via setup.py, it will run this step for you.

The full list of commands that npm can invoke is in package.json under the
scripts header. This is an arbitrary key to shell command mapping that makes
it so `npm run <name>` will invoke the corresponding command. In many cases
these are tools we've installed with npm.

So common commands to be aware of:

  * `npm run build` is responsible for building the javascript using a tool
  browserify for the js and stylus for the css and copying it to the dist/
  directory.
  * `npm run watch` uses a similar mechanism to monitor all files in the client
  directory for changes and rebuild the output each time a change is made.
  Use this for developing since it also includes source maps and other
  helpful debug things.
  * `npm run test` Invokes karma to run tests in a single run. You can run
  `test:debug` which invokes karma in watching, interactive mode allowing
  tests to be debugged in chrome and rerun after each change. There's also
  `test:watch` which runs karma in auto-watch mode non-interactively.
  * `npm run start` or `npm start` will run the frontend as a convenience.
