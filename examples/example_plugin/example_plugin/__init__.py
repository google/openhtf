
import tornado.web
import json


class ExampleHandler(tornado.web.RequestHandler):

	def initialize(self, host, port):
		self.host = host
		self.port = port

	def get(self, param):
		example_dict = {'port': self.port, 'host': self.host, 'param': param}
		self.write(json.JSONEncoder().encode(example_dict))


handler=([r'/example/(.*)', ExampleHandler],
		 ['host','port'])

configs={'class':'ExamplePlugin',
		 'tag':'example-plugin',
		 'icon':'pets',
		 'label':'example'}
