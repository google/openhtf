
import conf_plugin
import mutables_plugin
import tornado_plugin
import astroid
from astroid import MANAGER


def register(linter):
	pass

#for i in range(0,250):
#	print("hello")

def transform(cls):
  if cls.name == 'openhtf.conf':
 	from openhtf import conf
 	#for a in cls.__dict__.items():
 	#	print(a)
 	#print('HELLO THERE ',cls.parent)
 	a = MANAGER.ast_from_class(conf)
  	return a
MANAGER.register_transform(astroid.Module, transform)

#problem: it's still reading it as a module, not a class... 
#look at builder class
#the visit() function seems to be important

#def transform2(cls):
#  print(type(cls))
#MANAGER.register_transform(astroid.Class, transform2)