
import tornado.web
import json


class ExampleHandler(tornado.web.RequestHandler):

  def initialize(self, station_store, host, port, path):
    self.host = host
    self.port = port

  def get(self, param):
    example_dict = {'port': self.port, 'host': self.host, 'param': param}
    self.write(json.JSONEncoder().encode(example_dict))


handlers=[(r'/example/(.*)', ExampleHandler)]

configs={'class':'ExamplePlugin',
		 'tag':'example-plugin',
		 'icon':'pets',
		 'label':'example'}
