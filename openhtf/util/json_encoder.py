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

import base64
import json

from openhtf.core import test_record


class TestRecordEncoder(json.JSONEncoder):
  """JSON encoder that supports Attachments."""
  def default(self, obj):
    if isinstance(obj, test_record.Attachment):
      dct = obj._asdict()
      dct['data'] = base64.standard_b64encode(obj.data).decode('utf-8')
      return dct
    return super(TestRecordEncoder, self).default(obj)
