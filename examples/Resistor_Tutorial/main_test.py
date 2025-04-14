"""main_test.py"""

import time

from plugs import MultimeterPlug, PowerSupplyPlug

from openhtf.output.callbacks import console_summary
from openhtf import Test
from openhtf import measures, Measurement
from openhtf import plug
from openhtf.util import configuration



CONF = configuration.CONF
SIMULATE_MODE = CONF.declare("simulate",
                             default_value=False,
                             description="Set simulation mode")
CONF.load(simulate=True)


SimulatedMultimeterPlug = configuration.bind_init_args(
    MultimeterPlug, SIMULATE_MODE
    )
SimulatedPowerSupplyPlug = configuration.bind_init_args(
    PowerSupplyPlug, SIMULATE_MODE
    )

@measures(
        Measurement("resistor_val")
        .doc("Computed resistor value")
        .in_range(5320, 5880)
)
@plug(dmm=SimulatedMultimeterPlug)
@plug(supply=SimulatedPowerSupplyPlug)
def resistor_test(test, dmm:MultimeterPlug, supply:PowerSupplyPlug) -> None:
    """Check if resistor value in acceptable.

    Args:
        test (Test): Openhtf Test object
        dmm (MultimeterPlug): Multimeter object
        supply (PowerSupplyPlug): Powr supply object
    """
    supply.connect()
    dmm.connect()

    input_voltage = 4 #in V
    supply.set_voltage(input_voltage)

    time.sleep(3)
    current = float(dmm.read_current()[1])
    measured_r = round(input_voltage/current, 3)
    test.measurements["resistor_val"] = measured_r

    print(f"R value is: {measured_r}")

def main():
    """Create and execute the test. 
    """
    test = Test(resistor_test)
    test.add_output_callbacks(console_summary.ConsoleSummary())
    test.execute()

if __name__ == "__main__":
    main()
