
import astroid

from astroid import MANAGER
from pylint import lint

def __init__(self):
  pass

def validate_transform(cls):
  if cls.name == 'openhtf.util.validators':
    #putting all the attributes in Validators into the openhtf.util.validators node
    cls._locals.update(cls.locals['Validators'][0].locals)

# def YO(cls):
#   if cls.name == 'TimeoutHTTPConnection':
#     #putting all the attributes in Validators into the openhtf.util.validators node
#     import pdb
#     pdb.set_trace()

def register(linter):
  MANAGER.register_transform(astroid.Module, validate_transform)
  #MANAGER.register_transform(astroid.Class, YO)