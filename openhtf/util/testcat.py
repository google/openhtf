# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Output a JSON-encoded log output to standard out.

Takes OpenHTF JSON log outputs and prints out human-readable files.
"""

import argparse
import datetime
import json
import logging


ATTR_MAP = dict(
    red='\033[91m',
    green='\033[92m',
    yellow='\033[93m',
    blue='\033[94m',
    purple='\033[095m',
    cyan='\033[96m',
    white='\033[97m')

LEVEL_MAP = {
    logging.DEBUG:'cyan',
    logging.INFO:'green',
    logging.WARNING:'yellow',
    logging.ERROR:'red',
    logging.CRITICAL:'red'}


def main():
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument(
      'test_json', help='Path of JSON to parse')
  options = parser.parse_args()

  test_output = json.load(open(options.test_json, 'r'))
  for log_record in test_output['log_records']:
    epoch = log_record['timestamp_millis'] / 1000.
    time_str = (
        datetime.datetime.fromtimestamp(epoch).strftime(
            '%Y-%m-%d %H:%M:%S.%f'))
    attr = ATTR_MAP[LEVEL_MAP[log_record['level']]]
    for line in log_record['message'].splitlines():
      print '{attr}{time_str} {source}:{lineno} {line}\033[0m'.format(
          attr=attr,
          time_str=time_str,
          source=log_record['source'],
          lineno=log_record['lineno'],
          line=line.encode('utf-8'))


if __name__ == '__main__':
  main()
