"""Utilities for handling command line arguments.

StoreInModule:
  Enables emulating a gflags-esque API (flag affects global value), but one
  doesn't necessarily need to use flags to set values.

  Example usage:
    DEFAULT_VALUE = 0
    ARG_PARSER = argv.ModuleParser()
    ARG_PARSER.add_argument(
        '--override-value', action=argv.StoreInModule,
        default=DEFAULT_VALUE, target='%s.DEFAULT_VALUE' % __name__)

  Then in an entry point (main() function), use that parser as a parent:
    parser = argparse.ArgumentParser(parents=[other_module.ARG_PARSER])
    parser.parse_args()
"""

import argparse


def ModuleParser():
  return argparse.ArgumentParser(add_help=False)


class StoreInModule(argparse.Action):

  def __init__(self, *args, **kwargs):
    self._tgt_mod, self._tgt_attr = kwargs.pop('target').rsplit('.', 1)
    proxy_cls = kwargs.pop('proxy', None)
    if proxy_cls is not None:
      self._proxy = proxy_cls(*args, **kwargs)
    super(StoreInModule, self).__init__(*args, **kwargs)

  def __call__(self, parser, namespace, values, option_string=None):
    if hasattr(self, '_proxy'):
      values = self._proxy(parser, namespace, values)
    if '.' in self._tgt_mod:
      base, mod = self._tgt_mod.rsplit('.', 1)
      module = getattr(__import__(base, fromlist=[mod]), mod)
    else:
      module = __import__(self._tgt_mod)
    setattr(module, self._tgt_attr, values)


class _StoreValueInModule(StoreInModule):
  """Stores a value in a module level variable when set."""

  def __init__(self, const, *args, **kwargs):
    kwargs.update(nargs=0, const=const)
    super(_StoreValueInModule, self).__init__(*args, **kwargs)

  def __call__(self, parser, namespace, values, option_string=None):
    del values  # Unused.
    super(_StoreValueInModule, self).__call__(
        parser, namespace, self.const, option_string=option_string)


class StoreTrueInModule(_StoreValueInModule):
  """Stores True in a module level variable when set."""

  def __init__(self, *args, **kwargs):
    super(StoreTrueInModule, self).__init__(True, *args, **kwargs)


class StoreFalseInModule(_StoreValueInModule):
  """Stores False in module level variable when set."""

  def __init__(self, *args, **kwargs):
    super(StoreFalseInModule, self).__init__(False, *args, **kwargs)
