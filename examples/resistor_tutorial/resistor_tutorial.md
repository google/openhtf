## Introduction
The goal of this tutorial is to familarize yourself with some OpenHTF basic functionalities. We'll do so by trying to determine the resistance value of a resistor. This will include using a programmable power supply as well as a digital multimeter. 

We will apply a voltage to the resistor, and measure the corresponding current in the circuit. Using Ohm's law $V = R.I$, this should give us an estimate of the resistance value of the resistor : $R = V/I$  
We will then be able to determine if the resistor if good or bad by comparing the measured value to a threshold.

During this tutorial, you will learn how to use OpenHTF Plugs, Measurements and Configurations. 


## Writing your first test
The first step of this tutorial is to create a `main_test.py` that will contain our test:

```python
# main_test.py

import openhtf as htf

def resistor_test(test):
    """A placeholder phase that we will fill out later in the example."""

def main():
    test = htf.Test(resistor_test)
    test.execute()

if __name__ == "__main__":
    main()
```
After execution of the script, you should see as an output in the console that the test has passed : 

```shell
(.venv-htf)$ python main_test.py

======================= test: openhtf_test  outcome: PASS ======================
```

That was easy enough! Now let's start actually testing things. For this, we are going to use the measurement feature of Openhtf. We will tell Openhtf that a certain value inside of a Phase is something we want to measure and the result of the Phase depends on the value that is measured. This is done using a decorator above the Test Phase definition: 

## Making a Measurement

```python
# main_test.py

import openhtf as htf

@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        )
def resistor_test(test):
    """A placeholder phase that we will fill out later in the example."""

def main():
    test = htf.Test(resistor_test)
    test.execute()

if __name__ == "__main__":
    main()
```

If you run the test, You should see that it fails : 

```shell
(.venv-htf)$ python main_test.py

======================= test: openhtf_test  outcome: FAIL ======================
```
That is because OpenHTF was told that the `resistor_test` Phase was supposed to make a measurement called `resistor_val`, but since we never declared that measurement's value in the `resistor_test` Phase OpenHTF plays it safe and returns a **FAIL** status.  

> *Note* : You might have noticed that there isn't a lot of information explaining exactly why the test failed. We can change that by adding a few lines to use an output callback:

```python
# main_test.py

from openhtf.output.callbacks import console_summary
import openhtf as htf


@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        )
def resistor_test(test):
    """A placeholder phase that we will fill out later in the example."""

def main():
    test = htf.Test(resistor_test)
    test.add_output_callbacks(console_summary.ConsoleSummary())
    test.execute()

if __name__ == "__main__":
    main()
```

This gives us a more detailed output which is very helpful for debugging when developing tests : 
```shell
(.venv-htf)$ python main_test.py
:FAIL
failed phase: resistor_test [ran for 0.00 sec]
  failed_item: resistor_val (Outcome.UNSET)
    measured_value: UNSET
    validators:


======================= test: openhtf_test  outcome: FAIL ======================
```

To define the measurement, we just need to add the line : `test.measurements["resistor_val"] = 10` inside of our `resistor_test` phase. We set it as an arbitrary value for now, but soon this will be given by an actual measurement.

```python
@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        )
def resistor_test(test):
    test.measurements["resistor_val"] = 10

```

## Creating Plugs

To move on with our test definition, we need to be able to communicate with lab instruments. In our case, this is going to be a multimeter and a power supply. OpenHTF is meant to be very modular so the boilerplate code that allows us to interact with each device is going to be implemented inside of a `Plug` object in a seperate script. All we need to do for testing is to import the Plugs we need within our test script, and then interact with the device using the Plugs API. 

The goal is not to dive into how to develop Plugs, so we'll just provide the code for the multimeter and the power supply. The tutorial was developed with a Rigol DM858 and Rigol DP932E, but it also includes a simulation mode so you can run everything without the hardware. 


To use your plugs in a test phase, import them in your script and then declare them inside of a decorator for your test phase : 

```python
import resistor_plugs

import time
```
and then 
```python
@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        )
@htf.plug(dmm=resistor_plugs.MultimeterPlug)
@htf.plug(supply=resistor_plugs.PowerSupplyPlug)
def resistor_test(test, dmm: resistor_plugs.MultimeterPlug, supply: resistor_plugs.PowerSupplyPlug) -> None:
    test.measurements["resistor_val"] = 10
```

All that's left to do is to connect to the instruments, set the voltage, read the resulting current through the circuit and calculate the resistor value: 

```python
@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        .with_units(units.OHM)
        )
@htf.plug(dmm=resistor_plugs.MultimeterPlug)
@htf.plug(supply=resistor_plugs.PowerSupplyPlug)
def resistor_test(test, dmm: resistor_plugs.MultimeterPlug, supply: resistor_plugs.PowerSupplyPlug) -> None:
    supply.connect()
    dmm.connect()
    
    input_voltage = 5 #in V
    supply.set_voltage(input_voltage)
    time.sleep(3) # add a short wait for the voltage and current to stabilize
    current = float(dmm.read_current()[1])

    measured_r = input_voltage/current
    test.measurements["resistor_val"] = measured_r
    print(f"R value is: {measured_r}")
```

At this point we can either run the tutorial with some actual hardware, or we can use the simulation mode. 

We'll start off with actual hardware, but check out the [Simulation mode](#using-simulation-mode) as it includes some information on how to use OpenHTF's configuration settings.

### Hardware connection
To interact with the hardware, we'll be using pyvisa under the hood. This library provides an easy interfacing solution to most devices that accept SCPI commands. Learning how to use pyvisa is out of scope here however.

Make sure to have your instruments (multimeter and power supply) wired properly, with the resistor and the ammeter in series.


Install the required libraries : 
```shell 
(.venv-htf)$ pip install pyvisa pyvisa-py pyusb
```

Then run the script : 

```shell
(.venv-htf)$ python main_test.py
R value is: 5866.153540919828
:PASS


======================= test: openhtf_test  outcome: PASS ======================
```

Cool! This test was done with a resistor rated at $5.6\text K\Omega$ $\pm 5 \%$ so our measured value of $5.87 \text K\Omega$ is fine.

The final step is going to be to add a rule so that our test fails if we have a bad resistor. For that $5\%$ margin, it means we want values in the $[5.320\text K\Omega: 5.880\text K\Omega]$ range. 

OpenHTF provides a convenient feature called a Validator to check this easily. Since we want to check the value of our measurement, we define this validation rule inside of the measurement decorator. For now we're using one of the default validators but it is possible to make your own custom validators for more specific use cases.

This is also a good opportunity to mention the `openhtf.utils.units` library that OpenHTF provides. This allows you to declare the unit of a measurement within the `@htf.measures()` statement.

```python
from openhtf.util import units

@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        .in_range(5320, 5880)
        .with_units(units.OHM)
)
@htf.plug(dmm=resistor_plugs.MultimeterPlug)
@htf.plug(supply=resistor_plugs.PowerSupplyPlug)
def resistor_test(test, dmm: resistor_plugs.MultimeterPlug, supply: resistor_plugs.PowerSupplyPlug) -> None:
```

And now if we run the test with a resistor that is out of range (here a 220 $\Omega$ resistor), we get a fail: 

```shell
(.venv-htf)$ python main_test.py
R value is: 220.493
:FAIL
failed phase: resistor_test [ran for 3.38 sec]
  failed_item: resistor_val (Outcome.FAIL)
    measured_value: 220.493
    validators:
      validator: 5320 <= x <= 5880


======================= test: openhtf_test  outcome: FAIL ======================
```
Congratulations, you have a working OpenHTF test that can be deployed in a resistor manufacturing plant!

## Using Simulation mode

As mentionned previously, this tutorial can also be done without actual hardware. For this we will use the fact that our plugs have been provided with a simulation mode. In this case, they will return random values when querying data. 

This means we won't have any correlation between the applied voltage and the measured current, but at least we can check that our test sequence works. 

Right now, we make the call to our plugs inside of the `@plug(dmm=MultimeterPlug)` decorator. However this does not allow us to use the fact that our MultimeterPlug object can be instantiated with the `simulate` argument which we will need: 

```python
class MultimeterPlug(BasePlug):
    def __init__(self, simulate: bool = False)-> None:
        self.simulate = simulate
```

To do so, we'll use the configurations built in OpenHTF : `from openhtf.util import configuration`.  
Then we load the useful configuration parameters inside of a configuration object:

```python
CONF = configuration.CONF
SIMULATE_MODE = CONF.declare("simulate", 
                             default_value=False, 
                             description="Set if the test setup is in simulation mode")
CONF.load(simulate=True)
```

Finally, we create instances of the MultimeterPlug and PowerSupplyPlug that use this configuration. All that is left to do is to make sure we call these new plugs inside of our phase decorators:

```python
MultimeterPlug = configuration.bind_init_args(resistor_plugs.MultimeterPlug, SIMULATE_MODE)
PowerSupplyPlug = configuration.bind_init_args(resistor_plugs.PowerSupplyPlug, SIMULATE_MODE)

@htf.measures(
        htf.Measurement("resistor_val")
        .doc("Computed resistor value")
        .in_range(5320, 5880)
        .with_units(units.OHM)
)
@htf.plug(dmm=MultimeterPlug)
@htf.plug(supply=PowerSupplyPlug )
def resistor_test(test, dmm: resistor_plugs.MultimeterPlug, supply: resistor_plugs.PowerSupplyPlug) -> None:
```


> *Note* : In this example we're manually declaring and uploading a configuration parameter, but it is also possible to load these parameters from a yaml file or a dict. You can read the `configuration.py` module doc for more details.   

If we run it, we'll have a random current value, so the test will most likely fail with our validator, but at least we have something running:

```shell
(.venv-htf)$ python main_test.py
R value is: 0.733
:FAIL
failed phase: resistor_test [ran for 3.00 sec]
  failed_item: resistor_val (Outcome.FAIL)
    measured_value: 0.733
    validators:
      validator: 5320 <= x <= 5880


======================= test: openhtf_test  outcome: FAIL ======================
```
