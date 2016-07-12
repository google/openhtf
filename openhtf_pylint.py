
import astroid

from astroid import MANAGER
from pylint import lint


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


def trans_expr(node):
  if (isinstance(node.func, astroid.Attribute) and
      isinstance(node.func.expr, astroid.Name) and
      node.func.expr.name == 'conf' and
      node.func.attrname == 'Declare'):
    import pdb;pdb.set_trace()
    #print('hello?\n\n\n')
    # We're declaring a conf key, stash it in the root (astroid.Module).
    if node.args:
      conf_key_name = node.args[0].value
    else:
      for keyword in node.keywords:
        if keyword.arg == 'name':
          # We assume the name is an astroid.Const(str), so it has a str value.
          conf_key_name = keyword.value.value
          break
      else:
        # TODO(maddychan): Figure out how to cleanly report a pylint error,
        # here the error is invalid conf.Declare() syntax (no name given).
        pass
    try:
      node.root()._declared_conf_keys.append(conf_key_name)
    except AttributeError:
      node.root()._declared_conf_keys = [conf_key_name]


def register(linter):
  MANAGER.register_transform(astroid.Call, trans_expr)
  linter.add_message = wrap_add_message(linter.add_message)
