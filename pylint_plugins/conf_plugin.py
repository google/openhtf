
import astroid

from astroid import MANAGER
from pylint import lint

def __init__(self):
  pass


#didn't change/work on this yet
def wrap_add_message(func):
  def add_message(msg_descr, line=None, node=None, args=None, confidence=None):
    kwargs = {'confidence': confidence} if confidence else {}
    if (msg_descr != 'no-member' or
        args[0:2] != ('Module', 'openhtf.conf')):
      return func(msg_descr, line, node, args, **kwargs)
    # We're sure it's a no-member warning for the openhtf.conf module.
    try:
      if args[2] in node.root()._declared_conf_keys:
        # We found a declaration for the symbol, just skip this message.
        return
    except AttributeError:
      pass

    # TODO(maddychan): Figure out how to add a custom failure message here.
    return func('no-member', line, node, args, **kwargs)

  return add_message

#storing a reference to the openhtf.conf module node
clss = []
clss_locals = {}
current_root = []

def trans_expr(node):
  if (isinstance(node.func, astroid.Attribute) and
      isinstance(node.func.expr, astroid.Name) and
      node.func.expr.name == 'conf' and
      node.func.attrname == 'Declare'):

    #import pdb
    #pdb.set_trace()

    #keeping track of the current root, refreshing the locals if it changes
    if current_root == []:
    	current_root.append(node.root())
    elif current_root[0] != node.root():
    	current_root[0] = node.root()
    	clss[0].locals = clss_locals

    #adding the conf attribute to the module's locals
    if node.args and clss:
    	clss[0].locals[node.args[0].value] = [None]
  

    # madsci's stuff - didn't use it sorry.... 
    #  
    # else:
    #   for keyword in node.keywords:
    #     if keyword.arg == 'name':
    #       # We assume the name is an astroid.Const(str), so it has a str value.
    #       conf_key_name = keyword.value.value
    #       break
    #   else:
    #     # TODO(maddychan): Figure out how to cleanly report a pylint error,
    #     # here the error is invalid conf.Declare() syntax (no name given).
    #     pass
    # #try:
    # #  node.root()._declared_conf_keys.append(conf_key_name)
    # #except AttributeError:
    # #  node.root()._declared_conf_keys = [conf_key_name]




def conf_transform(cls):
  if cls.name == 'openhtf.conf':
    #putting all the attributes in Configuration into the openhtf.conf node
    cls._locals.update(cls.locals['Configuration'][0].locals)

    #storing reference to this node for future use
    clss.append(cls)
    clss_locals.update(cls.locals)


def register(linter):
  MANAGER.register_transform(astroid.Call, trans_expr)
  MANAGER.register_transform(astroid.Module, conf_transform)
  linter.add_message = wrap_add_message(linter.add_message)
