
import astroid
from astroid import MANAGER



def register(linter):
	pass



def conf_transform(cls):
  if cls.name == 'openhtf.conf':
  	import pdb;pdb.set_trace()
	cls._locals.update(cls.locals['Configuration'][0])

MANAGER.register_transform(astroid.Module, conf_transform)

#def conf_transform2(func):
#  print(func)
  #if func.name == 'Declare':
    #print(func.name)
 	#func._locals.update(func.locals['Configuration'][0])

#MANAGER.register_transform(astroid.Statement, conf_transform2)
