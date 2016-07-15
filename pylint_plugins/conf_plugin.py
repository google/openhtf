
import astroid

from astroid import MANAGER
from pylint import lint

def __init__(self):
  pass

#storing a reference to the openhtf.conf module node
class clss(object):
  conf_node = None
  conf_locals = {}
  current_root = None

def trans_expr(node):
  #checking if it's a call to conf.Declare
  if (isinstance(node.func, astroid.Attribute) and
  	isinstance(node.func.expr, astroid.Name) and
  	node.func.expr.name == 'conf' and
  	node.func.attrname == 'Declare'):
    
    
    if clss.conf_node:
      #keeping track of the current root, refreshing the locals if it changes
      if not clss.current_root or clss.current_root != node.root():
        clss.current_root = node.root()
        clss.conf_node.locals = clss.conf_locals

      #adding the conf attribute to the module's locals
      conf_key_name = None
      if node.args:
	    conf_key_name = node.args[0].value
      else:
	    for keyword in node.keywords:
	      if keyword.arg == 'name':
	        # We assume the name is an astroid.Const(str), so it has a str value.
	        conf_key_name = keyword.value.value
	        break
	    assert conf_key_name != None, "Invalid conf.Declare() syntax"
	      
      clss.conf_node.locals[conf_key_name] = [None]

def conf_transform(cls):
  if cls.name == 'openhtf.conf':
    #putting all the attributes in Configuration into the openhtf.conf node
    cls._locals.update(cls.locals['Configuration'][0].locals)

    #storing reference to this node for future use
    clss.conf_node = cls
    clss.conf_locals.update(cls.locals)


def register(linter):
  MANAGER.register_transform(astroid.Call, trans_expr)
  MANAGER.register_transform(astroid.Module, conf_transform)
