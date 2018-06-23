# How To Contribute

We welcome contributions to OpenHTF! Provided you've satisfied our legal
requirements, contributing is as easy as submitting a pull request with your
changes in order to kick off the review process. But first, please read through
the rest of this doc to help ensure a smooth code review.


## Legal Requirements
In order to become a contributor, you first need to sign the appropriate
[Contributor License Agreement](https://cla.developers.google.com/clas)
(if you happen to be a Google employee, you're already covered).


## Code Reviews
All contributions to OpenHTF, including those made by official maintainers, must
go through code review. Code reviews ensure that the codebase stays as easily
maintainable as possible, and that contributions fully align with the stated
goals of OpenHTF.


### Process Overview
Our code review process generally follows a predictable flow:

1. Fork the OpenHTF repository on Github.
2. Make commits to your fork.
3. Run unit tests and lint and ensure they still pass.
4. Submit a pull request (PR) to merge your fork into the official repo.
5. OpenHTF maintainers will review the PR and make comments.
6. Discuss and make more commits to your fork to address reviewer feedback.
7. Update the PR discussion on github with "PTAL" ("Please Take A Look") to
   indicate readiness for another look from the reviewers.
8. Repeat steps 4-6 until your PR receives an "LGTM" ("Looks Good To Me")
   from at least two official maintainers.
9. One of the maintainers will merge the PR into the main repo.


### Repo Structure and Hygiene
Our code repo follows the "single master" pattern described
[here](http://endoflineblog.com/follow-up-to-gitflow-considered-harmful).
As the name suggests, there is a single persistent "master" branch. Other
branches are all temporary and are deleted once the changes have been merged
back into master. Releases are marked (and created) via git tags.


#### Release Readiness
Our current criteria for release readiness is all unit tests to pass, and
sign-off obtained from a majority of the official maintainers.


#### Mergeability
When making a PR, it helps to try to keep it mergeable into the official repo.
In practice, this usually means periodically rebasing on `google/openhtf:master`
when there are changes upstream after your PR was created.


#### Commits
We generally tend toward squashing commits on merge rather than filling our git
log with merge commits. Sometimes, however, especially for large, sweeping
changes, it makes sense to preserve multiple commits in the history. If you're
authoring such a PR, consider using a rebase with squashes and fixups to reduce 
the commit history down to a commit per salient change.


### Code Standards
For a smooth code review, it helps to make sure your code adheres to standards,
conventions, and design goals for OpenHTF. A best-effort attempt to understand 
and meet these standards before requesting code review can go a long way towards
making the review process as fast and painless as possible.


#### Follow Style Guidelines
OpenHTF's Python code follows the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
We provide a `pylintrc` file at the top level of our repo that you can use with
[pylint](https://www.pylint.org/) to lint your Python code. We expect the 
codebase to produce zero pylint warnings, and we allow the use of explicit
`pylint: disable=...` comments in certain cases where it makes sense.

OpenHTF's built-in web frontend, written in TypeScript and using Angular2,
follows the [Angular2 Style Guide](https://angular.io/styleguide).
We recommend using [codelyzer](https://www.npmjs.com/package/codelyzer) to lint
your frontend code.


#### Write Tests
Our unit test code lives in the 'test' directory side-by-side with the openhtf
module itself in the repo. We look for 80% or better test coverage on new code.
For updates to existing code, we expect a non-negative delta in test coverage.


#### Provide Documentation
OpenHTF code is fairly well-documented through the liberal use of docstrings and
comments in the actual code. If your code is doing something that isn't
immediately intuitive, consider adding clarifying comments.

In addition to inline documentation, adding example scripts to the `examples/`
directory is a great way to express the intended usage of OpenHTF features.


#### Limit Complexity
Code that is complex requires programmers to hold many things in their heads
simultaneously in order to make modifications and fixes. Thus code complexity
can increase the risk of bugs as well as the time and effort needed to fix
them. In hardware testing (more so than in many more computationally intensive
or latency-sensitive applications) maximizing reliability and stability are
often far more important than minimizing code execution time. Therefore OpenHTF
prioritizes leveraging composable components with clean, well-defined
interfaces wherever possible, even at the occasional cost of computational
intensity. Check out
[this great talk](https://www.infoq.com/presentations/Simple-Made-Easy)
for a deeper look at code complexity.


#### Consider OpenHTF's Goals
OpenHTF is designed to abstract away as much boilerplate as possible from
hardware test setup and execution, so test engineers can focus primarily on
test logic. It aspires to do so in a lightweight and minimalistic fashion.
OpenHTF should remain general enough to be useful in a variety of hardware
testing scenarios, from the lab bench to the manufacturing floor.

Try to keep these goals in mind when authoring your contributions.


#### Stick to Existing Structure
The package/module structure of OpenHTF is designed to reflect its core duties.
If you're adding a new module or feature, put some thought into where it best
fits in based on what it does.

```
  openhtf
    |
    | Repository root directory.
    |
    |
    |-> bin
    |
    |     Standalone tools and scripts to help manage the codebase.
    |
    |
    |-> contrib
    |
    |     Standalone scripts that use the OpenHTF package. Nothing in the
    |     OpenHTF package should depend on these.
    |
    |
    |-> examples
    |
    |     Example OpenHTF tests and plugs.
    |
    |
    |-> openhtf
    |     |
    |     |  The OpenHTF Python package.
    |     |
    |     |-> core
    |     |
    |     |     Framework internals that manage test state and execution.
    |     |     The contents of this submodule shouldn't normally need to be
    |     |     accessed from outside the package.
    |     |
    |     |
    |     |-> output
    |     |
    |     |     Manages the framework's output, including UI, logging, and test
    |     |     records.
    |     |
    |     |
    |     |-> plugs
    |     |
    |     |     Extensions for interfacing with various hardware, such as test
    |     |     equipment and DUT's.
    |     |
    |     |
    |     '-> util
    | 
    |           Generic utility functions and miscellaneous tools.
    |           The contents of this submodule should be general enough to be 
    |           usable outside of OpenHTF, meaning it should not be dependent
    |           on other code in the OpenHTF package.
    |
    |
    '-> test

          Unittest code.
```


## Setting Up Your Dev Environment
The OpenHTF codebase is set up to use pip/virtualenv to manage dependencies.

[Pip](https://pip.pypa.io) is the Python package manager, while
[virtualenv](https://virtualenv.pypa.io) is a tool to isolate Python
environments. You'll need both in order to work with the OpenHTF codebase.

Pip installs dependencies from [PyPI](https://pypi.python.org/) (the Python
package index), but it can also install local packages in development mode
(using the `-e` flag). This causes pip to install the dependency using symlinks
from the filesystem so changes made to those files are instantly reflected.

Neither virtualenv nor OpenHTF's Python dependencies are included in the
repository. The following steps set up a new virtualenv environment and install
OpenHTF's dependencies into it using pip.


### Linux (Debian/Ubuntu)
These install instructions assume Bash as the shell environment. If you're using
a shell that's very different from Bash you may need to modify some steps
accordingly.

```bash
# Clone into the repo.
git clone https://github.com/google/openhtf.git

# Install system-level third-party dependencies.
sudo apt-get install python-pip swig libssl-dev python-dev python3-dev \
libffi-dev protobuf-compiler libprotobuf-dev

# Make sure pip is up-to-date.
sudo pip install --upgrade pip

# Install virtualenv via pip.
sudo pip install virtualenv

# Change to the openhtf directory.
cd openhtf

# Create a new virtualenv.
virtualenv venv

# Activate the new virtualenv.
. venv/bin/activate

# Update setuptools.
pip install setuptools --upgrade

# Install openhtf into the virtualenv in dev mode.
python setup.py develop
```

### MacOS
We will use [Homebrew](https://brew.sh/) to install our dependencies and Pip to set up the virtualenv. We recommend installing [Xcode](https://developer.apple.com/xcode/) first as the GCC compiler will be needed for both; however, other GCC compilers not associated with Xcode may work just as well. 

```bash
# Install dependencies.
brew install pkg-config libffi
brew install protobuf

# Clone into the repo.
git clone https://github.com/google/openhtf.git

# Install pip.
sudo easy_install pip

# Make sure pip is up to date.
sudo pip install --upgrade pip

# Install virtualenv via pip.
sudo pip install virtualenv

# Change to the openhtf directory.
cd openhtf

# Create a new virtualenv.
virtualenv venv

# Activate the new virtualenv.
. venv/bin/activate

# Install openhtf into the virtualenv in dev mode.
python setup.py develop
```

If you're having issues with the python setup, it's possible that the problem is due to El Capitan not including ssl headers. This [link](http://adarsh.io/bundler-failing-on-el-capitan/) may help you in that regard. 

## Web Frontend Development
OpenHTF ships with a built-in web gui found in the `openhtf.output.web_gui` module.

We don't expect everyone to go through the steps of building the frontend from
source, so we provide a prebuilt version of the frontend in the
`openhtf/output/web_gui/prebuilt` directory. If you don't plan to contribute to
the built-in frontend, you can feel free to stop reading here; OpenHTF will
automatically use the the prebuilt version of the frontend we include.

If you _do_ plan to contribute to the frontend, read on.

The frontend consists of a server written in Python and an
[Angular2](https://angular.io/) client
written in [Typescript](https://www.typescriptlang.org/).

The client's dependencies are managed with [npm](https://www.npmjs.com/).

Setting your dev environment up to enable work on the frontend requires some
extra steps:

### Linux (Debian/Ubuntu)
```bash
# Change to the frontend directory.
cd openhtf/output/web_gui/src

# Install the frontend's build dependencies.
npm install
```

Once your dev environment is set up for frontend work, you'll be able to build
the frontend with:

```bash
npm run build
```

But for convenience, you'll probably want to start a build process that will
watch the source for changes and re-build the frontend automatically as needed.
We've set up node to do that:

```bash
npm start
```

Now you've got the frontend building, but you still need to serve it. The
frontend server is started as a runnable module. In a terminal where your Python
virtual environment (set up above) is active, start the server with:

```bash
python -m openhtf.output.web_gui
```

If you want the server to automatically restart when changes are detected, use
the `--dev` flag.

Once you're happy with your changes, don't forget to update the prebuilt
version; we've included a script to help:

```bash
npm run update_prebuilt
```

That last step is easy to forget, so try to make it a habit whenever you're
prepping a PR that includes frontend work.
