#!/usr/bin/python3

import pyvisa

class DMM34461A:

	def read_resistance(self):
		
		rm = pyvisa.ResourceManager()
		SCPI_34661A = rm.open_resource('')
		idn = SCPI_34661A.query('*IDN?')
		print('Connected to\n', idn)

		values = SCPI_34661A.query_ascii_values(':MEASure:RESistance?')
		resistance = values[0]
		return resistance
		SCPI_34661A.close()
		rm.close()
