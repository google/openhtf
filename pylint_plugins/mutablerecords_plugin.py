
import astroid

from astroid import MANAGER
from pylint import lint

def __init__(self):
  pass
    

def mutables_transform(cls):
  #checking if it's inheriting from a mutablerecords declaration
  if (len(cls.bases) > 0 and isinstance(cls.bases[0], astroid.Call) and 
    cls.bases[0].func.as_string() == 'mutablerecords.Record'):

    try:

      #adding the ones in the list as attributes of the class
      if len(cls.bases[0].args) >= 2:
        for a in cls.bases[0].args[1].elts:
          cls.locals[a] = [None]

      #adding the keys of the dict to the attributes of the class
      if len(cls.bases[0].args) >= 3:
        for a,b in cls.bases[0].args[2].items:
          cls.locals[a.value] = [None]

    except:
      raise SyntaxError('Invalid mutablerecords syntax')



def register(linter):
  MANAGER.register_transform(astroid.ClassDef, mutables_transform)

