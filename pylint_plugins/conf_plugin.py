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


def __init__(self):
  pass


CONF_NODE = None  # AST node representing the conf module.
CONF_LOCALS = {}
CURRENT_ROOT = None


def transform_declare(node):
  """Transform conf.declare calls by stashing the declared names."""
  global CURRENT_ROOT

  if not (isinstance(node.func, astroid.Attribute)
          and isinstance(node.func.expr, astroid.Name)
          and node.func.expr.name == 'conf'
          and node.func.attrname == 'declare'):
    return

  conf_key_name = None
  if node.args:
    conf_key_name = node.args[0].value
  else:
    for keyword in node.keywords:
      if keyword.arg == 'name':
        # Assume the name is an astroid.Const(str), so it has a str value.
        conf_key_name = keyword.value.value
        break
    assert conf_key_name != None, "Invalid conf.declare() syntax"

  if CONF_NODE:
    # Keep track of the current root, refreshing the locals if it changes.
    if not CURRENT_ROOT or CURRENT_ROOT != node.root():
      CURRENT_ROOT = node.root()
      CONF_NODE.locals = CONF_LOCALS
      CONF_NODE.locals[conf_key_name] = [None]

  else:
    CONF_LOCALS[conf_key_name] = [None]


def transform_conf_module(cls):
  """Transform usages of the conf module by updating locals."""
  global CONF_NODE

  if cls.name == 'openhtf.conf':
    # Put all the attributes in Configuration into the openhtf.conf node.
    cls._locals.update(cls.locals['Configuration'][0].locals)

    # Store reference to this node for future use.
    CONF_NODE = cls
    CONF_LOCALS.update(cls.locals)


def register(linter):
  """Register all transforms with the linter."""
  MANAGER.register_transform(astroid.Call, transform_declare)
  MANAGER.register_transform(astroid.Module, transform_conf_module)
