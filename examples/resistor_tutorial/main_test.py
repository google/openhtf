import time

import resistor_plugs

import openhtf as htf
from openhtf.output.callbacks import console_summary
from openhtf.util import configuration, units

CONF = configuration.CONF
SIMULATE_MODE = CONF.declare(
    "simulate", default_value=False, description="Set simulation mode"
)
CONF.load(simulate=True)  # Change to True if running simulated hardware


MultimeterPlug = configuration.bind_init_args(
    resistor_plugs.MultimeterPlug, SIMULATE_MODE
)

PowerSupplyPlug = configuration.bind_init_args(
    resistor_plugs.PowerSupplyPlug, SIMULATE_MODE
)


@htf.measures(
    htf.Measurement("resistor_val")
    .doc("Computed resistor value")
    .in_range(5320, 5880)
    .with_units(units.OHM)
)
@htf.plug(dmm=MultimeterPlug)
@htf.plug(supply=PowerSupplyPlug)
def resistor_test(
    test, dmm: resistor_plugs.MultimeterPlug, supply: resistor_plugs.PowerSupplyPlug
) -> None:
    """Check if resistor value in acceptable.

    Args:
        test (Test): Openhtf Test object
        dmm (MultimeterPlug): Multimeter object
        supply (PowerSupplyPlug): Powr supply object
    """
    supply.connect()
    dmm.connect()

    input_voltage = 4  # in V
    supply.set_voltage(input_voltage)

    time.sleep(3)
    current = float(dmm.read_current()[1])
    measured_r = round(input_voltage / current, 3)
    test.measurements["resistor_val"] = measured_r

    print(f"R value is: {measured_r}")


def main():
    test = htf.Test(resistor_test)
    test.add_output_callbacks(console_summary.ConsoleSummary())
    test.execute()


if __name__ == "__main__":
    main()
