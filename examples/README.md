# Running the examples

## Install dependencies

Some examples have their own additional dependencies. They can be installed
with the following command:

```
# Activate your virtualenv if not already done.
pip install pandas
```

## Running the examples

Each example can be run as a Python script, so for `measurements.py`:

```
python examples/measurements.py
```

Running the test will print the outcome on the terminal. You can examine
the run's JSON file, generated in the working directory, to view the
measurements for the run. This example generates a JSON output because it
configures one via output callbacks; read on for more examples with other
types of outputs.

Some examples also have user prompts, you'll have to enter some text at the
prompt to continue the example.

## List of examples

### Canonical examples

1.  [`hello_world.py`](hello_world.py): start here if learning how to write
    an OpenHTF test.
    Comments explain usage of basic OpenHTF features: measurements, phases,
    `TestApi` and the OpenHTF test, and output callbacks.
2.  [`measurements.py`](measurements.py): measurements are the canonical
    mechanism to record text or numeric parameters for a phase.
    This example walks you through defining measurements with pass-fail rules ("validators"), units, dimensions, and how to set the measurements from
    your phases.
3.  [`with_plugs.py`](with_plugs.py): how to define and subclass plugs, and
    use them in a phase.
4.  [`frontend_example.py`](frontend_example.py): How to use the OpenHTF web
    frontend in a test. This gives your test a GUI via the default browser on
    the system.
5.  [`all_the_things.py`](all_the_things.py): demonstates use of plugs,
    measurements, attachments and `PhaseOptions`. Multiple phases are sequenced
    via a `Test` and executed, with some output callbacks defined (JSON file,
    pickle file and console).

### Feature showcases

1.  [`checkpoints.py`](checkpoints.py): checkpoints with measurements can be
    used to stop a test if any phase before the checkpoint had failed
    measurements.
    By default, failed measurements don't stop a test execution.
2.  [`stop_on_first_failure.py`](stop_on_first_failure.py): shows how to use
    `TestOptions`, in this case the `stop_on_first_failure` option, to
    customize test execution.
    Also shows how to set this via a `Configuration`.
3.  [`ignore_early_canceled_tests.py`](ignore_early_canceled_tests.py): shows
    how to customize output callbacks; in this case, JSON output.
4.  [`phase_groups.py`](phase_groups.py): phase groups can be used to combine
    phases with their own setup and teardown logic.
5.  [`repeat.py`](repeat.py): uses `openhtf.PhaseResult.REPEAT` to
    conditionally repeat execution of a phase in a test.

### Tutorials

1. [resistor_tutorial](resistor_tutorial/): Walk-through on how to validate a resistor using Measurements and Plugs. 

