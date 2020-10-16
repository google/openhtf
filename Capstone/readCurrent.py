#!/usr/bin/python3

import pyvisa
class DMM34461A:
	"""
		Connect to DMM 34461A then get current value;

		returen:
			
	"""

	def read_current(self):
		
		return float(self.instrument.query('MEASure:CURRent:DC?'))



