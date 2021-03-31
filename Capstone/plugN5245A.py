import pyvisa
import time
# PNA Network ANalyzer N5245A


class plugN5245A:
	def _init_(self, address):
		print('Try to connect to', address)
		try:
			self.instrument = pyvisa.ResourceManager().open_resource(address)
			idn = self.instrument.query('*IDN?')
			print('Can not connect to instrument' + address)
		except:
			raise 'Can not connect to instrument' + address
			
	def reset(self):
		""" reset analyzer"""
		self.instrument.write('*RST')
		
	def preset(self):
		""" preset analyzer"""
		self.instrument.write('PRESet')
		
	def start_frequency()
		""" set start frequency in analyzer"""
		self.instrument.write('FREQuency:STARt %G MHZ' % (1.0))
		
	def power_on(self):
		""" turn on power: ON = 1 """			
		self.instrument.write(':OUTPut:STATe %d' % (1))
		
	def power_off(self):
		""" turn off power: OFF = 0 """
		self.instrument.write(':OUTPut:STATe %d' % (0))
		
	def power_limit(self):
		""" set power limit """
		self.instrument.write('POWer123456:LIMit %G' % (1.0))
		
	def read_current_frequency(self):
		""" 
		Choose any number between the min and max frequency limits of the analyzer.
		It will accept min or max instead of a numeric parameter.
		"""
		return float (self.instrument.query_ascii_values('FREQuency:CENTer? %s' % ('MAXimum')))
		
	
	""" 
	S-parameter: S11 and S21
	- set the start frequency
	- set stop frequency
	- set the instrument to measure S11 and S21 
	"""
		 
	def set_start_freq(self):
		""" set start frequency to 88 MHZ"""
		self.instrument.write('FREQuency:STARt %G MHZ' % (88.0))
		
	def set_stop_freq(self):
		""" set stop frequency to 108 MHZ"""
		self.instrument.write('FREQuency:STOP %G MHZ' % (108.0))
		
	def measure_S11(self):
		"""set the instrument to measure S11 port"""
		self.instrument.write(':CALCulate1:PARameter:DEFine "%s",%s' % ('MyMeas', 'S11'))
		
	def measure_S11(self):
		"""set the instrument to measure S21 port"""
		self.instrument.write(':CALCulate1:PARameter:DEFine "%s",%s' % ('MyMeasu', 'S21'))
			
	def close(self):
		self.instrument.close()