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


import astroid

from astroid import MANAGER
from pylint import lint


def __init__(self):
  pass
    

def mutable_record_transform(cls):
  """Transform mutable records usage by updating locals."""
  if not (len(cls.bases) > 0
          and isinstance(cls.bases[0], astroid.Call)
          and cls.bases[0].func.as_string() == 'mutablerecords.Record'):
    return

  try:
    # Add required attributes.
    if len(cls.bases[0].args) >= 2:
      for a in cls.bases[0].args[1].elts:
        cls.locals[a] = [None]

    # Add optional attributes.
    if len(cls.bases[0].args) >= 3:
      for a,b in cls.bases[0].args[2].items:
        cls.locals[a.value] = [None]

  except:
    raise SyntaxError('Invalid mutablerecords syntax')


def register(linter):
  """Register transform with the linter."""
  MANAGER.register_transform(astroid.ClassDef, mutable_record_transform)
