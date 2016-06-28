"""Utilities for handling command line arguments."""

import argparse
import sys


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
        setattr(sys.modules[self._tgt_mod], self._tgt_attr, values)

