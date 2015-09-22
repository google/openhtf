**DISCLAIMER:** This is not an official Google product.

[![Build Status](https://travis-ci.org/amyxchen/openhtf.svg)](https://travis-ci.org/amyxchen/openhtf)

# OpenHTF
The open-source hardware testing framework.


## Design Philosophy
OpenHTF is designed to abstract away nearly all boiler plate of hardware test
setup and execution, so test engineers can focus entirely on writing actual
tests. It aspires to do so in the most lightweight and minimalistic way
possible. It is general enough to be useful in a variety of hardware testing
scenarios, from the lab bench to the manufacturing floor.


## Duties of a Hardware Testing Framework
OpenHTF attempts to distill the core duties any hardware testing framework must
perform, handle each one in a clean, sensible fashion, and avoid any additional
fluff. Those duties are (with example tasks):

  * Manage configuration for each test.
    * e.g. Load calibration data from a configuration file.
    * e.g. Use a configuration file to point testers to networked test
      equipment.
  * Provide consistent testrun I/O.
    * e.g. Output records in the same format across all test stations in a
      manufacturing line, making it easier to write systems to ingest and
      analyze test results.
    * e.g. Have a uniform frontend across test stations for intuitive operator
      interactions.
    * e.g. Monitor all stations from a central frontend.
  * Manage test start and execution.
    * e.g. Plug in a DUT and have a test start automatically.
    * e.g. Ensure every instance of a test runs the same logic in the same
      order.
  * Provide hardware interface tools.
    * e.g. Provide shared hardware interfaces wrappers for things like USB,
      UART, GPIO, etc.
    * e.g. Allow user-written hardware interface wrappers at higher layers of
      abstraction, like Android ADB.

The package/module structure of OpenHTF is designed to reflect its core duties
in a clear, obvious fashion.

```
  .-----------------.
  |     openhtf     |
  |-----------------|
  | Python package. |
  '-----------------'
          |
          |    .---------------------------------.
          |    |              conf               |
          |--->|---------------------------------|
          |    | Reads and stores configuration. |
          |    '---------------------------------'
          |
          |    .-------------------------.
          |    |           exe           |
          |--->|-------------------------|
          |    | Manages test execution. |
          |    '-------------------------'
          |
          |    .----------------------------------------.
          |    |                   io                   |
          |--->|----------------------------------------|
          |    | Manages UI, logging, and test records. |
          |    '----------------------------------------'
          |
          |    .---------------------------------------------------.
          |    |                       plugs                       |
          |--->|---------------------------------------------------|
          |    | Extensions for interfacing with various hardware. |
          |    '---------------------------------------------------'
          |
          |    .-----------------------------------.
          |    |               util                |
          '--->|-----------------------------------|
               | Utility functions and misc tools. |
               '-----------------------------------'
```


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
expressed as regular python programs (.py files) that import and instantiate the
'Test' class from the openhtf module. That way test code is as straightforward
as possible to read and write. This also provides for the flexibility to do
anything in a test that can normally be done in python. Superficially, what
distinguishes an OpenHTF test from any other python program is that the OpenHTF
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
Stations capture the notion that a given test ran at some point and may run
again. It loosely reflects the idea of physical test stations that process
multiple DUTs over time. OpenHTF writes a breadcrumb to the filesystem (in a
directory that can be set using the --rundir flag) each time a test runs, and
all tests that have the same name are considered to be of the same station. This
way the web frontend can display a consolidated list of known tests as a list of
stations.


### Phase
OpenHTF tests are broken down into logical blocks called phases. Phases are no
more than normal python callables (usually functions) combined with the needed
metadata. Writing an OpenHTF test is just a matter of writing a bunch of phase
functions and specifying the order in which they should be executed.


### Measurement
OpenHTF gathers data about a DUT in the form of measurements. Usually,
measurements are declared along with a specification that desribes what
constitutes a "passing" value. If OpenHTF finishes the test run and one or more
measurements were out of that spec, the result of the whole test run will be
considered a fail.


### Attachment
Sometimes may want to capture additional data that is more complex or free-form
than a measurement. To that end, OpenHTF can attach arbitrary binary data to a
test record along with an optional MIME type.


### Plug
The essence of an OpenHTF test is to interact with a DUT to exercise it in
various ways and observe the result. Sometimes this is done by communicating
directly with the DUT, and other times it's done by communicating with a piece
of test equipment to which the DUT is attached in some way. A plug is a piece of
code written to enable OpenHTF to interact with a particular type of hardware,
whether that be a DUT itself or a piece of test equipment. OpenHTF comes
packaged with a growing collection of useful plugs, but supports the
creation of custom plugs as well.
