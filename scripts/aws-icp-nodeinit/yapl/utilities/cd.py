'''
Created on Dec 4, 2018

@author: Peter Van Sickel - pvs@us.ibm.com
'''
import os
from yapl.utilities.Trace import Trace, Level

TR = Trace(__name__)
"""
Got the cd context manager from:
https://stackoverflow.com/questions/431684/how-do-i-change-directory-cd-in-python/13197763#13197763

"""
class cd:
  """
    Context manager for changing the current working directory
  """
  def __init__(self, newPath):
    self.newPath = os.path.expanduser(newPath)
  #endDef

  def __enter__(self):
    self.savedPath = os.getcwd()
    if (TR.isLoggable(Level.FINEST)):
      TR.finest("__enter__","Current working directory: %s changing to: %s" % (self.savedPath, self.newPath))
    #endIf
    os.chdir(self.newPath)
  #endDef

  def __exit__(self, etype, value, traceback):
    os.chdir(self.savedPath)
    if (TR.isLoggable(Level.FINEST)):
      TR.finest("__exit__","Reverted current working directory to: %s" % self.savedPath)
    #endIf
  #endDef
#endClass


