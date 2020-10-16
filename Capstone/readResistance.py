#!/usr/bin/python3

import pyvisa

class DMM34461A:
	"""
	Connect to DMM 34461A and read the resistance. 
	parameter self is the instrument.

	return:

	"""
	def read_resistance(self):
		
		return float(self.instrument.query('MEASure:RESistance?'))

