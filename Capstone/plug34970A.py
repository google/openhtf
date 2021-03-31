import pyvisa
import time
# start of Data_Logger_for_Temp_and_Voltage

class plug34970A:
	def _init_(self, address):
		print('Try to connect to', address)
		try:
			self.instrument = pyvisa.ResourceManager().open_resource(address)
			idn = self.instrument.query('*IDN?')
			print('Can not connect to instrument' + address)
		except:
			raise 'Can not connect to instrument' + address
			
	def reset(self):
		""" reset """
		self.instrument.write('*RST')
		
	def preset(self):
		""" preset """
		self.instrument.write('PRESet')
		
	
	def conf_temperature(self):
		""" configure temperatur with channel 101, 102, 103"""
		self.instrument.write(':CONFigure:TEMPerature %s,%s,(%s)' % ('TCouple', 'J', '@101,102,103'))
	
		
	def scan_temp_channel(self):
		""" scan channels"""
		self.instrument.write(':ROUTe:SCAN (%s)' % ('@101,102,103'))	
		
	def conf_voltage(self):
		""" configure temperatur with channel 105, 106, 107"""
		self.instrument.write(':CONFigure:VOLTage:DC (%s)' % ('@105,106,107'))

	
	def scan_voltage_channel(self):
		""" scan voltage channel"""
		self.instrument.write(':ROUTe:SCAN (%s)' % ('@105,106,107'))
		
	def init(self):
		"""starts measurement """
		self.instrument.write(':INITiate')
		
	def fetch(self):
		"""Fetches data from memory after the scan list was completed """
		readings = self.instrument.query(':FETCh?')
		
	def close(self):
		self.instrument.close()

# end of Data_Logger_for_Temp_and_Voltage