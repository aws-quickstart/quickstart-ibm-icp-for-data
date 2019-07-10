'''
Created on Dec 7, 2018

@author: petervansickel
'''

import os, pwd
from yapl.utilities.Trace import Trace,Level

TR = Trace(__name__)

class runas(object):
  """
    Context manager for changing user (su)
    
    Got the ideas for this code from:
    https://stackoverflow.com/questions/1770209/run-child-processes-as-different-user-from-a-long-running-process 
  """
  def __init__(self, runas_name):
    object.__init__(self)
    self.user_name = os.environ.get('USER')
    self.user_home = os.environ.get('HOME')
    #self.user_pwd = os.getcwd()
    self.user_uid = os.getuid()
    self.user_gid = os.getgid()
    pw_record = pwd.getpwnam(runas_name)
    self.runas_name      = pw_record.pw_name
    self.runas_home      = pw_record.pw_dir
    self.runas_uid       = pw_record.pw_uid
    self.runas_gid       = pw_record.pw_gid
      
  #endDef

  def __enter__(self):
    methodName = "__enter__"
    os.environ[ 'HOME'     ]  = self.runas_home
    os.environ[ 'LOGNAME'  ]  = self.runas_name
    os.environ[ 'USER'     ]  = self.runas_name
    os.setgid(self.runas_gid)
    os.setuid(self.runas_uid)
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName, "runas_name: %s, uid: %d, gid: %d" % (self.runas_name, os.getuid(), os.getgid()))
    #endIf
  #endDef

  def __exit__(self, etype, value, traceback):
    methodName = "__exit__"
    os.setgid(self.user_gid)
    os.setuid(self.user_uid)
    os.environ[ 'HOME'     ]  = self.user_home
    os.environ[ 'LOGNAME'  ]  = self.user_name
    os.environ[ 'USER'     ]  = self.user_name
        
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName, "user_name: %s, uid: %d, gid: %d" % (self.user_name, os.getuid(), os.getgid()))
    #endIf
  #endDef

#endClass

