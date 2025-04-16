import random
import time

import pyvisa

from openhtf.core import base_plugs

### To use pyvisa ###
# Use rm.list_resources() to find the devices plugged in
# this will return a list of the connected devices such as:
# ('USB0::0x1AB1::0x0E11::DP8C1234567890::INSTR',
#   'ASRL1::INSTR', 'ASRL10::INSTR')
#
# Then run device = rm.open_resource(
#     'USB0::0x1AB1::0x0E11::DP8C1234567890::INSTR'
#     )
# to connect to the device.
# You can check the device ID with device.query("*IDN?")


class MultimeterPlug(base_plugs.BasePlug):
    """Plug for control of a multimeter with pyvisa. Using the simulate flag
    will bypass the hardware.

    Args:
        BasePlug (Plug): OpeHTF Plug object.
    """

    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.logger.info("Logging mode is %s", self.simulate)
        self.rm = None
        self.multimeter = None

    def connect(self) -> None:
        """Connect to the device using pysisa.
        Does nothing if using simulation mode.
        """
        if not self.simulate:
            try:
                self.rm = pyvisa.ResourceManager()
                self.multimeter = self.rm.open_resource(
                    "USB0::6833::8458::DM8A265201811::0::INSTR"
                )
                self.logger.info("Connected to Multimeter")
            except ConnectionRefusedError as error:
                self.logger.warning(
                    """Connection refused : %s,
                    Device might already be connected""",
                    error,
                )

            time.sleep(0.1)

    def read_current(self) -> tuple[float]:
        """Read current value from the multimter in A.
        If simultation mode is active, will return a random value.

        Returns:
            tuple[float]: Tuple containing the timestamp
            of the measurement and the actual reading
        """
        timestamp = time.time()

        if not self.simulate:
            current = self.multimeter.query("MEASure:CURRent:DC? AUTO,1E-3")[:-1]
        else:
            current = str(random.uniform(1, 10))

        self.logger.info("Reading current: %s A", current)
        return (timestamp, current)

    def read_voltage(self) -> tuple[float]:
        """Read voltage value from the multimter in V.
        If simultation mode is active, will return a random value.

        Returns:
            tuple[float]: Tuple containing the timestamp
            of the measurement and the actual reading
        """
        timestamp = time.time()

        if not self.simulate:
            voltage = self.multimeter.query("MEASure:VOLTage:DC? 10,1E-3")[:-1]
        else:
            voltage = str(random.uniform(1, 10))

        self.logger.info("Reading voltage: %s V", voltage)
        return (timestamp, voltage)

    def tearDown(self) -> None:
        """Disconnect from the multimeter.
        Important if running multiple tests sequentially.
        This can solve "USB busy" errors.
        """
        if not self.simulate:
            self.rm.close()


class PowerSupplyPlug(base_plugs.BasePlug):
    """Plug for control of a power supply with pyvisa.
    Using the simulate flag will bypass the hardware.
    """

    def __init__(self, simulate: bool = False):
        self.simulate = simulate
        self.rm = None
        self.supply = None

    def connect(self):
        """Connect to the device using pyvisa.
        Does nothing if using simulation mode.
        """
        if not self.simulate:
            try:
                self.rm = pyvisa.ResourceManager()
                self.supply = self.rm.open_resource(
                    "USB0::6833::42152::DP9D264501253::0::INSTR"
                )
                self.supply.write(":OUTP ALL, OFF")
                self.logger.info("Connected to Power Supply")
            except ConnectionRefusedError as error:
                self.logger.warning(
                    """Connection refused : %s, 
                    Device might already be connected""",
                    error,
                )

            time.sleep(0.1)

    def set_voltage(self, voltage: float, channel: str = "CH1") -> None:
        """Set output voltage for the power supply.

        Args:
            voltage (float): Output voltage value (V).
            channel (str, optional): Output channel. Defaults to "CH1".
        """
        if not self.simulate:
            command = f":APPL {channel}, {voltage}"
            self.supply.write(command)
            self.supply.write(f":OUTP {channel}, ON")
        self.logger.info("Setting voltage to: %s V", voltage)

    def close_channels(self) -> None:
        """Shut down all output channels."""
        if not self.simulate:
            for source in ["CH1", "CH2", "CH3"]:
                self.supply.write(f":APPL {source}, 0")
            self.supply.write(":OUTP ALL, OFF")
        self.logger.info("Shutting down all channels")

    def tearDown(self) -> None:
        """Disconnect from the multimeter.
        Important if running multiple tests sequentially.
        This can solve "USB busy" errors.
        """
        if not self.simulate:
            self.close_channels()
            self.rm.close()


if __name__ == "__main__":
    my_multimeter = MultimeterPlug()
    my_supply = PowerSupplyPlug()
    my_multimeter.connect()

    print(my_multimeter.read_current())
