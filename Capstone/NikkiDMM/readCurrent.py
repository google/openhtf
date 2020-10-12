#!/usr/bin/python3

import pyvisa
class DMM34461A:
	def read_current(self):
		
		rm = pyvisa.ResourceManager()
		SCPI_34661A = rm.open_resource('')
		idn = SCPI_34661A.query('*IDN?')
		print('Connected to\n', idn)

		values = SCPI_34661A.query_ascii_values(':MEASure:CURRent:DC?')
		dcCurrent = values[0]
		SCPI_34661A.close()
		rm.close()



