
"""
Created on Aug 10, 2018

@author: Peter Van Sickel - pvs@us.ibm.com
"""

class ICPInstallationException(Exception):
  """
    ICPInstallationException is raised when something unexpected occurs at some 
    point in the installation scripting, after the CloudFormation stack deployment.
  """
#endClass

  
class CommandInterpreterException(Exception):
  """
    CommandInterpreterException is intended to be used when the CommandHelper and various 
    command classes such as KubectlHelper and HelmHelper have unexpected situations.
  """
#endClass
