#!/usr/bin/python3
import pyvisa

class DMM34461A:

	def write(self,command):
		""" Custom query command """

		self.instrument.write(command)	

