import logging

from openxtf.lib import capabilities


class Example(capabilities.BaseCapability):
	"""Example of a simple capablility."""

  def TearDown(self):
  	logging.info('Tearing down %s', self)

	def DoStuff(self):
		return 'Did stuff!'
