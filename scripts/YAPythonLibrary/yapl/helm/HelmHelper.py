"""
Created on Nov 2, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

DESCRIPTION:
  Module to assist with programmatically executing helm commands in Python.
  
NOTES:
  The implementation originated as a generalized way to run helm installations.
  The implementation has only been tested in a very limited scope in the context
  of installing certain applications on ICP.
  
  It is assumed Helm has been installed and configured.
"""


from yapl.utilities.Trace import Trace
from yapl.exceptions.Exceptions import MissingArgumentException,\
  InvalidArgumentException


TR = Trace(__name__)

"""
  HelmCommandArgs holds a list of recognized commands and the names of the 
  attributes in the yaml file that define the command arguments.
  These arguments are "nameless" in the command line. In the yaml, the arguments
  get a name as noted in HelmCommandArgs table.  The arguments are then added
  to the command line in the createCommands() method.
"""
HelmCommandArgs = {
    "repo add": ['name', 'url'],
    "repo update": [],
    "install": ['chart']
  }

class HelmHelper(object):
  """
    Class to support the installation of applications on an ICP cluster using
    Helm and helm charts.
    
    It is assumed Helm has been installed and is available at the command line.
    
    It is assumed the PKI cert files needed to interact with Tiller have been 
    configured in the ~/.helm directory of the caller. 
  """


  def __init__(self):
    """
      Constructor
    """
    object.__init__(self)
  #endDef
  
  
  def createCommands(self,cmdDocs,start,**kwargs):
    """
      Return a list of command dictionaries, each with a command list and a command string.  

      Processing of cmdDocs will stop as soon as a doc kind that is not helm is encountered.

      All cmdDocs that are processed will be marked with a status attribute with the value PROCESSED.
       
      For each command dictionary in the returned list, either the list or the string can be used with 
      subprocess.call().  The command string is useful for emitting trace.
      
      The command dictionary looks like:
      { cmdList: [ ... ], cmdString: "..." }
      
      cmdDocs - a list of 1 or more YAML documents loaded from yaml.load_all()
      by the caller.
      
      For the ICP installation, helm is configured on the boot node such that all of the
      appropriate cert files are in place in the ~/.helm directory.
      TBD: I don't think we need to add the cert arguments.
      Implicit in each command are the following arguments:
        --ca-file
        --cert-file
        --key-file
    """
    if (not cmdDocs):
      raise MissingArgumentException("A non-empty list of command documents (cmdDocs) must be provided.")
    #endIf

    commands = []

    for i in range(start,len(cmdDocs)):      
      doc = cmdDocs[i]
      
      kind = doc.get('kind')
      if (not kind or kind != 'helm'): break; # done
      
      command = doc.get('command')
      if (not command):
        raise InvalidArgumentException("A helm command document: %s, must have a command attribute." % doc)
      #endIf

      cmdStr = "helm"
      cmdList = [ 'helm' ]
      
      cmdList.append(command)
      cmdStr = "%s %s" % (cmdStr,command)
      
      #cmdList.extend(["--ca-file", self.ClusterCertPath, "--cert-file", self.HelmCertPath, "--key-file", self.HelmKeyPath])
      #cmdStr = "%s --ca-file %s --cert-file %s --key-file %s" % (cmdStr,self.ClusterCertPath,self.HelmCertPath,self.HelmKeyPath)
      
      flags = doc.get('flags')
      if (flags):
        for flag in flags:
          if (len(flag) > 1):
            # multi-character flags get a double dash
            cmdList.append('--%s' % flag)
            cmdStr = "%s --%s" % (cmdStr,flag)
          else:
            # single character flags get a single dash
            cmdList.append('-%s' % flag)
            cmdStr = "%s -%s" % (cmdStr,flag)
          #endIf          
        #endFor
      #endIf
        
      options = doc.get('options')
      if (options):
        optionNames = options.keys()
        for optionName in optionNames:
          value = options.get(optionName)
          if (len(optionName) > 1):
            cmdList.append("--%s" % optionName)
            cmdStr = "%s --%s" % (cmdStr,optionName)
          else:
            cmdList.append("-%s" % optionName)
            cmdStr = "%s -%s" % (cmdStr,optionName)
          #endIf
          cmdList.append(value)
          cmdStr = "%s %s" % (cmdStr,value)
        #endFor
      #endIf
      
      setValues = doc.get('set-values')
      if (setValues):
        setNames = setValues.keys()
        for name in setNames:
          cmdList.append('--set')
          valueStr = "{name}={value}".format(name=name,value=setValues[name])
          cmdList.append(valueStr)
          cmdStr = "%s --set %s" % (cmdStr, valueStr)
        #endFor
      #endIf
      
      # Add the unnamed arguments, if any
      commandArgs = HelmCommandArgs.get(command)
      if (commandArgs):
        for argName in commandArgs:
          argValue = doc.get(argName)
          if (argValue != None):
            cmdList.append(argValue)
            cmdStr = "%s %s" % (cmdStr, argValue)
          #endIf
        #endFor
      #endIf

        #endFor
      #endIf
    
      doc['status'] = 'PROCESSED'
      commands.append({'cmdList': cmdList, 'cmdString': cmdStr})
    #endFor
    
    return commands
  #endDef
    
#endClass
