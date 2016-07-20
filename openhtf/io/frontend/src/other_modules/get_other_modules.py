# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License


"""One-off script to download third-party deps that don't play well with npm."""


import argparse
import os
import urllib

TARGETS = [
    'http://cdn.jsdelivr.net/sockjs/1/sockjs.min.js',  # sockjs
]


def main():
  """Download all the targets."""

  parser = argparse.ArgumentParser(description='get_other_modules.py',
                                   prog='python get_other_modules.py')
  parser.add_argument('--force', action='store_true',
                      help='Force download even if target files already exist.')
  args = parser.parse_args()

  for src in TARGETS:
    filename = src.split('/')[-1].split('#')[0].split('?')[0]
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if args.force or not os.path.exists(dst):
      urllib.urlretrieve(src, dst)


if __name__ == '__main__':
  main()
