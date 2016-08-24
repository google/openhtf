
import astroid
from astroid import MANAGER
from pylint import lint


def __init__(self):
  pass


def validate_transform(cls):
  if cls.name == 'openhtf.util.validators':
    # Put all the attrs in Validators into the openhtf.util.validators node.
    cls._locals.update(cls.locals['Validators'][0].locals)


def register(linter):
  MANAGER.register_transform(astroid.Module, validate_transform)
