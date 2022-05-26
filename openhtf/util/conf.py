# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Legacy interface to OpenHTF configuration.

Prefer using CONF from openhtf.util.configuration as an object:
  from openhtf.util import configuration

  CONF = configuration.CONF

  CONF.declare(...)
"""
# pytype: skip-file
import sys

from openhtf.util import configuration

# Swap out the module for a singleton instance of Configuration so we can
# provide __getattr__ and __getitem__ functionality at the module level.
sys.modules[__name__] = configuration.CONF
