
import pyvisa

class DMM34461A:

	def write(self,command):
	"""
	Custom write command
	"""
	self.instrument.write(command)	

