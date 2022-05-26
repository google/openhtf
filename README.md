**DISCLAIMER:** This is not an official Google product.

# OpenHTF
The open-source hardware testing framework.

[![Build Status](https://github.com/google/openhtf/actions/workflows/build_and_deploy.yml/badge.svg?branch=master)](https://github.com/google/openhtf/actions?branch=master)
[![Coverage Status](https://coveralls.io/repos/google/openhtf/badge.svg?branch=master&service=github)](https://coveralls.io/github/google/openhtf?branch=master)

[Issue Stats](http://issuestats.com/github/google/openhtf)

## Overview
OpenHTF is a Python library that provides a set of convenient abstractions
designed to remove as much boilerplate as possible from hardware test setup and
execution, so test engineers can focus primarily on test logic. It aspires to
do so in a lightweight and minimalistic fashion. It is general enough to be
useful in a variety of hardware testing scenarios, from the lab bench to the
manufacturing floor.


## Installing OpenHTF
**NOTE:** We recommend using [virtualenv](https://virtualenv.pypa.io) to create
an isolated Python environments for your projects, so as to protect system-wide
Python packages the OS depends upon. The installation instructions assume you've
_already_ created a virtualenv and activated it if you wish to do so.


### Option 1: Installing via 'pip' (recommended)
The most straightforward way to get the `openhtf` Python package into your
Python environment is simply to install it via
[pip](https://pypi.python.org/pypi). This will install the most recent
production release.

```bash
pip install openhtf
```


### Option 2: Installing from Source
If you want to install from source instead (for example, if you want some new
feature that hasn't made it to the production release yet), you can download
[the source code](https://github.com/google/openhtf) via
[git](https://git-scm.com/) or other means, and install the `openhtf` package
into your Python environment using the standard `setup.py` script.

```bash
python setup.py install
```


## Using OpenHTF
The fastest way to get started is to take a look in the `examples/` directory,
where you'll find sample test scripts and plugs. In addition, many of OpenHTF's
modules are fairly well documented inline through the use of docstrings.

Note: some of the `examples/` require protocol buffer code to be generated via
`python setup.py build` command.  This requires protocol buffer compiler
library to be installed
([additional instructions](CONTRIBUTING.md#setting-up-your-dev-environment)).

## Nomenclature
OpenHTF uses certain nomenclature internally for several of its core concepts.
Some of the more important terms are listed here for clarity.


### DUT (Device Under Test)
DUT refers to an individual piece of hardware being evaluated, exercised, or
tested.


### Test
The top-level abstraction that OpenHTF deals with is the test. A test is just
a series of steps performed on/with a DUT, usually along with some
data-gathering or measurement steps. In the OpenHTF paradigm, tests are
expressed as regular Python programs (.py files) that import and instantiate the
'Test' class from the openhtf module. That way test code is as straightforward
as possible to read and write. This also provides for the flexibility to do
anything in a test that can normally be done in Python. Superficially, what
distinguishes an OpenHTF test from any other Python program is that the OpenHTF
test imports the openhtf package, instantiates the ```Test``` class, and calls
its ```Execute()``` function. From there, OpenHTF manages the setup, execution,
and teardown of the test, keeps track of anything gathered, and provides a
pass/fail result.

At times it may be necessary to disambiguate between different common readings
of the word _test_. In such scenarios we use the following more precise terms:
  
  * **test run** - A single start-to-finish execution of a specific test.
  * **test recipe** - A test definition that may be executed multiple times,
    each time as a distinct test run.
  * **test script** - A .py file that contains a test recipe.


### Station
_Stations_ capture the notion that a given test ran at some point and may run
again. It loosely reflects the idea of physical test stations that process
multiple DUTs over time. OpenHTF writes a breadcrumb to the filesystem (in a
directory that can be set using the `--rundir` flag) each time a test runs, and
all tests that have the same name are considered to be of the same station. This
way the web frontend can display a consolidated list of known tests as a list of
stations.


### Phase
OpenHTF tests are broken down into logical blocks called _phases_. Phases are no
more than normal Python callables (usually functions) combined with the needed
metadata. Writing an OpenHTF test is just a matter of writing a bunch of phase
functions and specifying the order in which they should be executed.


### Measurement
OpenHTF gathers data about a DUT in the form of _measurements_. Usually,
measurements are declared along with a specification that describes what
constitutes a "passing" value. If OpenHTF finishes the test run and one or more
measurements were out of that spec, the result of the whole test run will be
considered a fail.


### Attachment
Sometimes may want to capture additional data that is more complex or free-form
than a measurement. An _attachment_ can link arbitrary binary data to a
test record, along with an optional MIME type.


### Plug
The essence of an OpenHTF test is to interact with a DUT to exercise it in
various ways and observe the result. Sometimes this is done by communicating
directly with the DUT, and other times it's done by communicating with a piece
of test equipment to which the DUT is attached in some way. A _plug_ is a piece
of code written to enable OpenHTF to interact with a particular type of hardware,
whether that be a DUT itself or a piece of test equipment. OpenHTF comes
packaged with a growing collection of useful plugs, but supports the
creation of custom plugs as well.
