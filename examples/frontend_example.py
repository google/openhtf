# Copyright 2018 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Simple OpenHTF test which launches the web GUI client."""

import openhtf as htf
from openhtf.util import conf

from openhtf.output.servers import station_server
from openhtf.output.web_gui_server import web_launcher
from openhtf.plugs import user_input


@htf.measures(htf.Measurement('hello_world_measurement'))
def hello_world(test):
  test.logger.info('Hello World!')
  test.measurements.hello_world_measurement = 'Hello Again!'


if __name__ == '__main__':
  conf.load(station_server_port='4444')
  with station_server.StationServer() as server:
    web_launcher.launch('http://localhost:4444')
    for i in range(5):
      test = htf.Test(hello_world)
      test.add_output_callbacks(server.publish_final_state)
      test.execute(test_start=user_input.prompt_for_test_start())
