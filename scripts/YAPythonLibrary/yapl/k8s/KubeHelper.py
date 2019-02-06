"""
Created on Nov 7, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

DESCRIPTION:
  Module to assist with programmatically executing helm commands in Python.
  
NOTES:
  The implementation originated as a generalized way to run kubectl commands to
  support the installation of applications deployed to an ICP cluster deployed 
  to the AWS cloud.
  
  The implementation has only been tested in a very limited scope.
  
  It is assumed kubectl has been installed and configured to run with a permanent
  token configuration.

"""
import os, fnmatch
from subprocess import call
import yaml
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import InvalidArgumentException
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.Exceptions import InvalidParameterException
from yapl.exceptions.Exceptions import InvalidConfigurationException
from yapl.exceptions.Exceptions import InvalidConfigurationFile

TR = Trace(__name__)

class KubeHelper(object):
  """
    Class to support the execution of kubectl commands targeted at an ICP cluster.
    
    It is assumed kubectl has been installed and configured to not require authentication.
    
    The commands get run using the subprocess.call() method.
    
  """

  def __init__(self, configPath, **restArgs):
    """
      Constructor
      
        configPath - the path to a directory of .yaml files that define 
        variables and kubectl commands.

      See _init() helper method for details on restArgs.
        
    """
    object.__init__(self)
    
    if (not configPath):
      raise InvalidArgumentException("The configPath cannot be empty or None.")
    #endIf
      
    self.configPath = configPath
    self._init(**restArgs)

  #endDef
  
  def _init(self, **restArgs):
    """
      Initialization helper for the constructor.

      restArgs:      
        restArgs is expected to hold the values for the intrinsic variables.
      
        restArgs may also have values for custom variables that override the 
        custom variable values in the variables.yaml
            
    """
    methodName = '_init'

    self.home = os.path.expanduser('~')
      
    # configuration may have no variables (static configuration)
    self.variableValues = {}
    self.variableMap = {}
    
    variablesFiles = self.getYaml(self.configPath, 'variables')
    if (not variablesFiles):
      if (TR.isLoggable(Level.FINE)):
        TR.fine(methodName,"No yaml found for kind variables.  This configuration has no variables.")
      #endIf
    else:
      if (len(variablesFiles) > 1):
        raise InvalidConfigurationException("Expecting a single variables definition yaml in configuration: %s" % self.configPath)
      #endIf
      
      variablesPath = variablesFiles[0]
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Variables are defined in: %s" % variablesPath)
      #endIf
         
      with open(variablesPath, 'r') as variablesFile:
        variables = yaml.load(variablesFile)
      #endWith
      
      self.intrinsicVariables = variables.get('IntrinsicVariables')
      
      variableMap = variables.get('VariableKeywordMap')
      if (not variableMap):
        raise InvalidConfigurationFile("The file: %s, is expected to have a VariableKeywordMap attribute." % variablesPath )
      #endIf
      
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Variable Keyword Map: %s" % variableMap)
      #endIf
      
      self.variableMap = variableMap
      self.variableNames = variableMap.keys()
      
      variableValues = variables.get('VariableValues')
      
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Custom Variable Values: %s" % variableValues)
      #endIf
      
      self.variableValues = self.mergeArgValues(self.variableNames, variableValues, **restArgs)
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"All Variable Values: %s" % self.variableValues)
      #endIf
      
      self.checkVariables(self.intrinsicVariables,self.variableValues)
    #endIf      
  #endDef
  
  
  def checkVariables(self, names, variableValues):
    """
      Raise an exception if the given names do not have a value in the given 
      variableValues dictionary.
      
      This is primarily intended as a check that the intrinsic variables all got
      assigned a value.
    """
    
    missingValues = []
    for name in names:
      if (variableValues.get(name) == None):
        missingValues.append(name)
      #endIf
    #endFor
    
    if (missingValues):
      raise InvalidConfigurationException("The following variables have no value: %s" % missingValues)
    #endIf

  #endDef
  
  
  def  mergeArgValues(self, variableNames, variableValues, **restArgs):
    """
      Return a reference to the variableValues dictionary with merged values for 
      the variableNames from restArgs
      
      For each name in the variableNames list check the restArgs to see if there
      is a value to use to add a name-value pair to the variableValues dictionary
      or to update an existing variable value in the variableValues dictionary.
      
      The intrinsic variables in particular should be assigned values from restArgs
      and added to the variableValues dictionary.
    """
    methodName = 'mergeArgValues'
    
    for name in variableNames:
      value = restArgs.get(name)
      if (value != None):
        if (variableValues.get(name) != None):
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName,"Replacing value of %s: %s with: %s" % (name,variableValues[name],value))
          #endIf
          variableValues[name] = value
        else:
          # typically this would be adding a value for an intrinsic variable
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName,"Adding variable value: %s: %s" % (name,value))
          #endIf
          variableValues[name] = value
      #endIf
    #endFor
        
    return variableValues
  #endDef


  def checkForMacros(self,line,parameterNames,keywordMap):
    """
      Return a dictionary with one or more key-value pairs from the keywordMap that 
      have a macro substitution present in the given line.  
      Otherwise, return an empty dictionary.  
      
      Helper method for createConfigFile()
    """
    result = {}
    for parmName in parameterNames:
      macroName = keywordMap.get(parmName)
      if (not macroName):
        raise InvalidParameterException("The parameter name: %s was not found in the given keyword mappings hash map: %s" % (parmName,keywordMap))
      #endIf
      macro = "${%s}" % macroName
      if (line.find(macro) >= 0):
        result[parmName] = macroName
      #endIf
    #endFor
    return result
  #endDef
  

  def createCommandFile(self, commandFilePath=None, templateFilePath=None, **restArgs):
    """      
      Using the template file, fill in all the variable strings in the template
      using the given parameters.
      
      Required restArgs:
        parameters: Dictionary with the actual values of the parameters
                    The parameter values will be substituted for the corresponding
                    macro in the template file to create the configuration file.
        
        keywordMap: The mapping of parameter names to macro names (keywords) in the
                    template file.
                    
      Optional restArgs:
        specialValues: Dictionary used for macro name that requires a special format  
                       string to be used when doing the macro substitution.
                       Defaults to an empty dictionary.
            
      Comment lines in the template file are written immediately to the config file.
      
      A macro in the template file is delimited by ${} with the macro name in the {}.
      
    """
    methodName = "createCommandFile"
    
    if (not commandFilePath):
      raise MissingArgumentException("The command file path must be provided.")
    #endIf
    
    if (not templateFilePath):
      raise MissingArgumentException("The template file path must be provided.")
    #endIf
  
    parameters = restArgs.get('parameters')
    if (not parameters):
      raise MissingArgumentException("Parameters must be provided.")
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Parameters: %s" % parameters)
    #endIf
    
    keywordMap = restArgs.get('keywordMap')
    if (not keywordMap):
      raise MissingArgumentException("Keyword mappings must be provided.")
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Keyword Map: %s" % keywordMap)
    #endIf
    
    specialValues = restArgs.get('specialValues',{})
    specialValueNames = specialValues.keys()
    
    parameterNames = parameters.keys()
    
    try:
      with open(templateFilePath,'r') as templateFile, open(commandFilePath,'w') as commandFile:
        for line in templateFile:
          # Need to strip at least the newline character(s)
          line = line.rstrip()
          if (line.startswith('#')):
            commandFile.write("%s\n" % line)
          else:
            if (TR.isLoggable(Level.FINEST)):
              TR.finest(methodName,"Checking line for macros: %s" % line)
            #endIf
            
            substitutions = self.checkForMacros(line,parameterNames,keywordMap)
            
            if (not substitutions):
              commandFile.write("%s\n" % line)
            else:
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"Substitutions: %s" % substitutions)
              #endIf
            
              parmNames = substitutions.keys()
              
              for parmName in parmNames:
                macroName = substitutions[parmName]
                parmValue = parameters[parmName]
                if (specialValueNames and macroName in specialValueNames):
                  specialFormat = specialValues.get(macroName)
                  parmValue = specialFormat.format(parmValue)
                #endIf
                macro = "${%s}" % macroName
                if (TR.isLoggable(Level.FINEST)):
                  TR.finest(methodName,"LINE: %s\n\tReplacing: %s with: %s" % (line,macro,parmValue))
                #endIf
                line = line.replace(macro,"%s" % parmValue)
              #endFor

              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"NEW LINE: %s" % line)
              #endIf
              
              commandFile.write("%s\n" % line)
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating command file: %s from template file: %s" % (commandFilePath,templateFilePath), e)
      raise
    #endTry
  #endDef

  
  def createYamlFile(self, filePath, x):
    """
      Dump a yaml representation of the given object (x) to the given filePath. 
    """
    
    if (not filePath):
      raise MissingArgumentException("The file path (filePath) cannot be empty or None.")
    #endIf
    
    if (not x):
      raise MissingArgumentException("The object (x) to be dumped to the file cannot be empty or None.")
    #endIf
    
    destDirPath = os.path.dirname(filePath)
    
    if (not os.path.exists(destDirPath)):
      os.makedirs(destDirPath)
    #endIf
    
    with open(filePath, 'w') as yamlFile:
      yaml.dump(x,yamlFile,default_flow_style=False)
    #endWith
    
    return filePath
  #endDef
  
  
  def processFileOption(self,destDirPath,optionValue,obj):
    """
      Processing for the -f option of a kubectl command.
      
      Helper to createCommands()
    """
    if (not optionValue.endswith(".yaml")):
      fileName = "%s.yaml" % optionValue
    else:
      fileName = optionValue
    #endIf
    
    filePath = os.path.join(destDirPath,fileName)
    self.createYamlFile(filePath,obj)
    return filePath
  #endDef
  
  
  def createCommands(self,configPath):
    """
      Return list of command dictionaries where each command dictionary has the command
      in the form of a list and a string.  Either the list or the string can be used 
      with subprocess.call().  The command string is useful emitting trace.
      
      Each command dictionary looks like:
      { cmdList: [ ... ], cmdString: "..." }
      
      A list of command dictionaries is returned as there may be more than one helm command
      defined in the configPath directory.  The ordering of the commands in the list is
      the order of the helm template files in the configPath directory.
      
      Each command is defined by the .yaml command template and the substitution of actual  
      values for the macro expressions in the templates.
    """
    
    commands = []
    
    stagingDir = os.path.join(os.getcwd(),'staging')
    if (not os.path.exists(stagingDir)):
      os.makedirs(stagingDir)
    #endIf
    
    cmdTemplates = self.getYaml(configPath,'kubectl')
    for template in cmdTemplates:
      baseName = os.path.basename(template)
      rootName,ext = os.path.splitext(baseName)
      cmdFilePath = os.path.join(stagingDir,"%s-command%s" % (rootName,ext))
      
      self.createCommandFile(commandFilePath=cmdFilePath,
                            templateFilePath=template,
                            parameters=self.variableValues,
                            keywordMap=self.variableMap)
      
      cmdStr = "kubectl"
      cmdList = [ 'kubectl' ]
      
      with open(cmdFilePath, 'r') as cmdFile:
        docs = list(yaml.load_all(cmdFile))
      #endWith
      
      cmdDoc  = docs[0]
      
      command = cmdDoc.get('command')
      if (not command):
        raise InvalidConfigurationFile("The first yaml document in %s, must have a command attribute." % cmdFilePath)
      #endIf
      
      cmdList.append(command)
      cmdStr = "%s %s" % (cmdStr,command)
      
      flags = cmdDoc.get('flags')
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
            
      options = cmdDoc.get('options')
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
          if (optionName == 'f'):
            # Check that there is a second document in the command file
            # The second document is the yaml that gets dumped to a file for the -f option
            if (len(docs) < 2):
              raise InvalidConfigurationFile("Expecting a second document to be used with the -f option in command file: %s ." % cmdFilePath)
            #endIf
            value = self.processFileOption(stagingDir,value,docs[1])
          #endIf
          # TBD: special processing for other options goes here
          cmdList.append(value)
          cmdStr = "%s %s" % (cmdStr,value)
        #endFor
      #endIf
      
      commands.append({'cmdList': cmdList, 'cmdString': cmdStr})
    #endFor
    return commands
  #endDef
  
  
  def invokeCommands(self):
    """
      Process the configuration files and invoke the commands.
    """
    methodName = 'invokeCommands'
    
    TR.entering(methodName)
    
    try:
      commands = self.createCommands(self.configPath)
      for command in commands:
        if (TR.isLoggable(Level.FINEST)):
          TR.finest(methodName,"Command: %s" % command)
        #endIf
        cmdStr = command.get('cmdString')
        cmdList = command.get('cmdList')
        TR.info(methodName, "Invoking: %s" % cmdStr)
        retcode = call(cmdList)
        if (retcode != 0):
          raise Exception("Invoking: '%s' Return code: %s" % (cmdStr,retcode))
        #endIf
      #endFor
    except Exception as e:
      TR.error(methodName,"ERROR: %s" % e, e)
      raise
    #endTry    
    
    TR.exiting(methodName)
  #endDef
  
  
  def getYaml(self, configPath, kind):
    """
      Return a list of full paths to all the .yaml files in the given configPath directory 
      with the given kind attribute value in the first document of each .yaml file
      in the directory.
      
      configPath - Path to the directory of yaml files to be considered.  (only .yaml files are considered)
      kind - the name of the kind of yaml file desired to be included, e.g., helm, kubectl, variables.
      
      For different approaches to listing files in a directory see:
      See https://stackabuse.com/python-list-files-in-a-directory/
      
      NOTE: The yaml.load_all() method returns a generator.  In the code below that
      gets converted to a list for convenience.
    """
    methodName="getYaml"
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Looking for .yaml files of kind: %s in: %s" % (kind,configPath))
    #endIf
    
    files = os.listdir(configPath)
    
    pattern = "*.yaml"
    yamlFiles = [os.path.join(configPath,f) for f in files if fnmatch.fnmatch(f,pattern)]
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Yaml files to consider: %s" % yamlFiles)
    #endIf
    
    kindFiles = []
    for f in yamlFiles:
      with open(f, 'r') as yamlFile:
        docs = list(yaml.load_all(yamlFile))
      #endWith
      
      # we only care about the first doc in the file
      doc = docs[0]
      
      docKind = doc.get('kind')
      if (docKind and docKind == kind):
        kindFiles.append(f)
      #endIf
    #endFor
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Yaml files of kind: %s: %s" % (kind,kindFiles))
    #endIf
    
    return kindFiles
  #endDef
  
#endClass