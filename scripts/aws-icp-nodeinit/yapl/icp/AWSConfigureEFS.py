
"""
Created on Oct 8, 2018

@author: Peter Van Sickel pvs@us.ibm.com
"""

import os
from subprocess import call
import boto3
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.Exceptions import InvalidParameterException


TR = Trace(__name__)

"""
  The StackParameters are imported from the root CloudFormation stack in the _init() 
  method below.
"""
StackParameters = {}
StackParameterNames = []

"""
  Map of EFS configuration parameter names to macro names used in the EFS template.
"""
EFSTemplateKeywordMap = { 
                         'TargetNodes':  'TARGET_NODES',
                         'MountSource':  'MOUNT_SOURCE',
                         'MountPoint':   'MOUNT_POINT',
                         'MountOptions': 'MOUNT_OPTIONS'
                        }

EFSParameterNames = EFSTemplateKeywordMap.keys()

EFSDefaultParameterValues = {
                              'TargetNodes': 'worker',
                              'MountOptions': 'rw,suid,dev,exec,auto,nouser,nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport',
                            }

"""
  Map of stack parameter names to EFS parameter names
"""
EFSVariableParameterMap = {
                           'ApplicationStorageMountPoint': 'MountPoint',
                           'EFSDNSName':                   'MountSource'
                          }

EFSVariableParameterNames = EFSVariableParameterMap.keys()

"""
  The EFSSpecialValues is a hook to treat the MOUNT_SOURCE value with a different format string than 
  is typical.  The str.format() method is used and the {} is a positional argument for format().
"""
EFSSpecialValues = {
                     'MOUNT_SOURCE': "{}:/",
                   }

ProvisionerTemplateKeywordMap = { 
                                  'EFSFileSystemId': 'EFS_FILE_SYSTEM_ID',
                                  'EFSDNSName': 'EFS_DNS_NAME',
                                  'AWSRegion': 'AWS_REGION',
                                  'ClusterDNSName': 'MY_CLUSTER'
                                }

ProvisionerParameterNames = ProvisionerTemplateKeywordMap.keys()

RBACTemplateKeywordMap = {
                            'Namespace': 'NAMESPACE'
                         }

RBACParameterNames = RBACTemplateKeywordMap.keys()


class ConfigureEFS(object):
  """
    Configure ICP worker nodes to use EFS dynamic provisioner
  """


  def __init__(self, region=None, stackId=None, **restArgs):
    """
      Constructor
      
      The region input is the AWS region where the EFS provisioner is running.
      
      The stackId input parameter is expected to be a AWS stack resource ID.
      The stackId is used to get the stack parameters among which is:
         EFSDNSName
         ApplicationStorageMountPoint
         EFSFileSystemId
         ClusterDNSName
      
      The restArgs keyword arguments include the following required parameters:
        playbookPath         - the path to the playbook to use to configure EFS
        varTemplatePath      - the path to the EFS configuration variable template
        manifestTemplatePath - the path to the EFS provisioner manifest YAML
        rbacTemplatePath     - the path to the EFS provisioner RBAC YAML
        serviceAccountPath   - the path to the EFS service account YAML
    """
    object.__init__(self)
    
    if (not region):
      raise MissingArgumentException("The AWS region name must be provided.")
    #endIf
    self.AWSRegion = region
    
    if (not stackId):
      raise MissingArgumentException("The CloudFormation boot stack ID (stackId) must be provided.")
    #endIf
    
    self.stackId = stackId
    self.cfnResource = boto3.resource('cloudformation')
    self.home = os.path.expanduser("~")
    self._init(stackId, **restArgs)
  #endDef


  def __getattr__(self,attributeName):
    """
      Support for attributes that are defined in the StackParameterNames list
      and with values in the StackParameters dictionary.  
    """
    attributeValue = None
    if (attributeName in StackParameterNames):
      attributeValue = StackParameters.get(attributeName)
    else:
      raise AttributeError("%s is not a StackParameterName" % attributeName)
    #endIf
  
    return attributeValue
  #endDef


  def __setattr__(self,attributeName,attributeValue):
    """
      Support for attributes that are defined in the StackParameterNames list
      and with values in the StackParameters dictionary.
      
      NOTE: The StackParameters are intended to be read-only.  It's not 
      likely they would be set in the Bootstrap instance once they are 
      initialized in _getStackParameters().
    """
    if (attributeName in StackParameterNames):
      StackParameters[attributeName] = attributeValue
    else:
      object.__setattr__(self, attributeName, attributeValue)
    #endIf
  #endDef


  def _init(self, stackId, **restArgs):
    """
      Instance initialization constructor helper.
      
      The stackIds input parameter is expected to be a list of AWS stack resource IDs.
      The first stack ID in the list is assumed to be the root stack.
      
      The restArgs are keyword arguments that include the following:
        playbookPath       - the path to the playbook to use
        varTemplatePath    - the path to the EFS configuration variable template
    """
    global StackParameters, StackParameterNames
    
    playbookPath = restArgs.get('playbookPath')
    if (not playbookPath):
      raise MissingArgumentException("A ploybook path (playbookPath) must be provided.")
    #endIf

    self.playbookPath = playbookPath
        
    varTemplatePath = restArgs.get('varTemplatePath')
    if (not varTemplatePath):
      raise MissingArgumentException("An EFS configuration variable template file path (varTemplatePath) must be provided.")
    #endIf

    self.varTemplatePath = varTemplatePath
    
    self.varFilePath = os.path.join(self.home,"efs-config-vars.yaml")
    
    manifestTemplatePath = restArgs.get('manifestTemplatePath')
    if (not manifestTemplatePath):
      raise MissingArgumentException("The file path to the YAML defining the EFS provisioner (manifestTemplatePath) must be provided.")
    #endIf
    
    self.manifestTemplatePath = manifestTemplatePath
    
    rbacTemplatePath = restArgs.get('rbacTemplatePath')
    if (not rbacTemplatePath):
      raise MissingArgumentException("The file path to the YAML defining the EFS provisioner RBAC (rbacTemplatePath) must be provided.")
    #endIf
    
    self.rbacTemplatePath = rbacTemplatePath
    
    serviceAccountPath = restArgs.get('serviceAccountPath')
    if (not serviceAccountPath):
      raise MissingArgumentException("The file path to YAML defining the EFS service account must be provided.")
    #endIf
    
    self.serviceAccountPath = serviceAccountPath
    
    StackParameters = self.getStackParameters(stackId)
    StackParameterNames = StackParameters.keys()
    
    efsParms = self.getEFSParameters()
    self.efsParameters = self.fillInDefaultValues(parameterNames=EFSParameterNames,defaultValues=EFSDefaultParameterValues,**efsParms)
    self.efsParameterNames = self.efsParameters.keys()
    
    self.efsProvPath = os.path.join(self.home,"efs-provisioner.yaml")
    self.provisionerParameters = self.getProvisionerParameters()
    
    self.efsRBACPath = os.path.join(self.home,"efs-rbac.yaml")
    self.rbacParameters = self.getRBACParameters()
  #endDef


  def getStackParameters(self, stackId):
    """
      Return a dictionary with stack parameter name-value pairs from the  
      CloudFormation stack with the given stackId.
    """
    result = {}
    
    stack = self.cfnResource.Stack(stackId)
    stackParameters = stack.parameters
    for parm in stackParameters:
      parmName = parm['ParameterKey']
      parmValue = parm['ParameterValue']
      result[parmName] = parmValue
    #endFor
    
    return result
  #endDef


  def getEFSParameters(self):
    """
      Return a dictionary with the EFS related parameter values input from the boot stack.
      
      The keys in the result dictionary are mapped to the actual variable name value used
      in the variable template file.
    """
    result = {}
    
    for name in EFSVariableParameterNames:
      varName = EFSVariableParameterMap.get(name)
      result[varName] = StackParameters.get(name)
    #endFor
    return result
  #endDef


  def getProvisionerParameters(self):
    """
      Return a dictionary with the EFS provisioner parameter values 
      input from the boot stack.
      
      AWSRegion is defined in an instance variable. It is not defined for the boot stack.
    """
    result = {}
    for name in ProvisionerParameterNames:
      if (name == 'AWSRegion'):
        result['AWSRegion'] = self.AWSRegion
      else:
        result[name] = StackParameters.get(name)
      #endIf
    #endFor
    
    return result
  #endDef  
  
  
  def getRBACParameters(self):
    """
      Return a dictionary with the EFS RBAC name-value pairs. 
    """
    result = {}
    
    result['Namespace'] = 'default'
    
    return result
  #endDef
  
  
  def fillInDefaultValues(self, parameterNames=None, defaultValues=None, **restArgs):
    """
      Return a dictionary with values for each parameter in parameterNames that is
      the value in restArgs or the default value in defaultValues. Ff the parameter 
      is not defined in restArgs the default value is used.
    """
    
    result = {}
    
    if (not parameterNames):
      raise MissingArgumentException("A parameter names list must be provided.")
    #endIf
    
    if (not defaultValues):
      raise MissingArgumentException("A dictionary of default values must be provided.")
    #endIf
    
    for parmName in parameterNames:
      parmValue = restArgs.get(parmName,defaultValues.get(parmName))
      if (parmValue):
        result[parmName] = parmValue
      #endIf
    #endFor

    return result
  #endDef
  
  
  def checkForParm(self,line,parameterNames,keywordMap):
    """
      Return a tuple (parmName,macroName) if the given line has a substitution macro  
      using a keyword from the given keyword mapping for one of the parameter names 
      in the given in parameterNames. 
      Otherwise, return None.  
      
      Returned tuple is of the form (parameter_name,macro_name)
      Helper method for createConfigFile()
    """
    result = (None,None)
    for parmName in parameterNames:
      macroName = keywordMap.get(parmName)
      if (not macroName):
        raise InvalidParameterException("The parameter name: %s was not found in the given keyword mappings hash map: %s" % (parmName,keywordMap))
      #endIf
      macro = "${%s}" % macroName
      if (line.find(macro) >= 0):
        result = (parmName,macroName)
        break
      #endIf
    #endFor
    return result
  #endDef
  
  
  def createConfigFile(self, configFilePath=None, templateFilePath=None, **restArgs):
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
        multipleAppearences: List of parameters that appear more than once in the
                             template file.  Defaults to the empty list.
                             
        specialValues: Dictionary used for macro name that requires a special format  
                       string to be used when doing the macro substitution.
                       Defaults to an empty dictionary.
            
      Comment lines in the template file are written immediately to the config file.
      
      Parameters that appear in more than one line in the template file need to be
      in the given mulitpleAppearances list.
      
      NOTE: It is assumed that a line in the configuration template file has at most
      one parameter defined in it. 
      
      A macro in the template file is delimited by ${} with the parameter name in the {}.
      
    """
    methodName = "createConfigFile"
    
    if (not configFilePath):
      raise MissingArgumentException("The configuration file path must be provided.")
    #endIf
    
    if (not templateFilePath):
      raise MissingArgumentException("The template file path must be provided.")
    #endIf
  
    parameters = restArgs.get('parameters')
    if (not parameters):
      raise MissingArgumentException("Parameters must be provided.")
    #endIf
    
    keywordMap = restArgs.get('keywordMap')
    if (not keywordMap):
      raise MissingArgumentException("Keyword mappings must be provided.")
    #endIf
    
    multipleAppearances = restArgs.get('multipleAppearances',[])
    
    specialValues = restArgs.get('specialValues',{})
    specialValueNames = specialValues.keys()
    
    parameterNames = parameters.keys()
    
    try:
      with open(templateFilePath,'r') as templateFile, open(configFilePath,'w') as configFile:
        for line in templateFile:
          # Need to strip at least the newline character(s)
          line = line.rstrip()
          if (line.startswith('#')):
            configFile.write("%s\n" % line)
          else:
            parmName,macroName = self.checkForParm(line,parameterNames,keywordMap)
            if (not parmName):
              configFile.write("%s\n" % line)
            else:
              parmValue = parameters[parmName]
              if (specialValueNames and macroName in specialValueNames):
                specialFormat = specialValues.get(macroName)
                parmValue = specialFormat.format(parmValue)
              #endIf
              macro = "${%s}" % macroName
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"LINE: %s\n\tReplacing: %s with: %s" % (line,macro,parmValue))
              #endIf
              newline = line.replace(macro,"%s" % parmValue)
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"NEW LINE: %s" % newline)
              #endIf
              configFile.write("%s\n" % newline)
              
              if (macroName not in multipleAppearances):
                # Only remove parmName from parameterNames when macroName  
                # does not appear more than once in the template file.
                parameterNames.remove(parmName)
              #endIf
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating configuration variable file: %s from template file: %s" % (configFilePath,templateFilePath), e)
      raise
    #endTry
  #endDef

  
  def createVarFile(self, varFilePath, templateFilePath):
    """
      Create an Ansible variable file to be used for configuring EFS (NFS) on
      each of the target nodes.
      
      Using the template file, fill in all the variable strings in the template
      using the parameters provided to the stack instance.
      
      The MOUNT_SOURCE gets special treatment.  When it is processed its value
      is initially the DNS name of the EFS server as created in the CloudFormation
      stack. The full mount source needs to include the source mount point which
      for EFS is always the root of the file system.  Hence in the body of the 
      loop that processes the variables the MOUNT_SOURCE value is modified to 
      include the source mount point.
      
      Comment lines in the template file are written immediately to the var file.
      
      NOTE: It is assumed that a line in the configuration template file has at most
      one parameter defined in it.  A parameter is delimited by ${} with the parameter
      name in the {}.
      
      NOTE: It is assumed a given parameter only appears once in the template file. 
      Once a parameter has been found and replaced in a given line in the template
      file, there is no need to check other lines for that same parameter.
    """
    methodName = "createVarFile"
    
    
    # Make a copy of parameter names that can be modified in this method.
    parameterNames = list(self.efsParameterNames)
    
    try:
      with open(templateFilePath,'r') as templateFile, open(varFilePath,'w') as varFile:
        for line in templateFile:
          # Need to strip at least the newline character(s)
          line = line.rstrip()
          if (line.startswith('#')):
            varFile.write("%s\n" % line)
          else:
            parmName,macroName = self.checkForParm(line,parameterNames,EFSTemplateKeywordMap)
            if (not parmName):
              varFile.write("%s\n" % line)
            else:
              parmValue = self.efsParameters[parmName]
              if (macroName == 'MOUNT_SOURCE'):
                parmValue = "%s:/" % parmValue
              #endIf
              macro = "${%s}" % macroName
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"LINE: %s\n\tReplacing: %s with: %s" % (line,macro,parmValue))
              #endIf
              newline = line.replace(macro,"%s" % parmValue)
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"NEW LINE: %s" % newline)
              #endIf
              varFile.write("%s\n" % newline)
              # No need to keep checking for parmName, once it has been found in a line in the template.
              parameterNames.remove(parmName)
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating configuration variable file: %s from template file: %s" % (varFilePath,templateFilePath), e)
      raise
    #endTry
  #endDef
  
  
  def runAnsiblePlaybook(self, playbook=None, extraVars="efs-config-vars.yaml", inventory="/etc/ansible/hosts"):
    """
      Invoke a shell script to run an Ansible playbook with the given arguments.
      
      NOTE: Work-around because I can't get the Ansible Python libraries figured out on Unbuntu.
    """
    methodName = "runAnsiblePlaybook"
    
    if (not playbook):
      raise MissingArgumentException("The playbook path must be provided.")
    #endIf
    
    try:
      TR.info(methodName,"Executing: ansible-playbook %s, --extra-vars @%s --inventory %s." % (playbook,extraVars,inventory))
      retcode = call(["ansible-playbook", playbook, "--extra-vars", "@%s" % extraVars, "--inventory", inventory ] )
      if (retcode != 0):
        raise Exception("Error calling ansible-playbook. Return code: %s" % retcode)
      else:
        TR.info(methodName,"ansible-playbook: %s completed." % playbook)
      #endIf
    except Exception as e:
      TR.error(methodName,"Error calling ansible-playbook: %s" % e, e)
      raise
    #endTry    
  #endDef


  def configureEFSProvisioner(self):
    """
      Configure an EFS dynamic storage provisioner.
      
      The kubectl command is used do the configuration.  It is assumed that
      kubectl has been configured to run with a permanent config context, 
      i.e., master node has been configured, no user and password is needed 
      and all the other context has been set.
      
      TODO: Investigate using the Python kubernetes module.
    """
    methodName = "configureEFSProvisioner"
    
    self.createConfigFile(configFilePath=self.efsProvPath,
                          templateFilePath=self.manifestTemplatePath,
                          parameters=self.provisionerParameters,
                          keywordMap=ProvisionerTemplateKeywordMap,
                          multipleAppearances=['MY_CLUSTER'])
    
    self.createConfigFile(configFilePath=self.efsRBACPath,
                          templateFilePath=self.rbacTemplatePath,
                          parameters=self.rbacParameters,
                          keywordMap=RBACTemplateKeywordMap,
                          multipleAppearances=['NAMESPACE'])
    

    # Create the EFS Provisioner RBAC
    TR.info(methodName,"Invoking: kubectl create -f %s" % self.efsRBACPath)
    
    retcode = call(["kubectl", "create", "-f", self.efsRBACPath])
    if (retcode != 0):
      raise Exception("Error calling kubectl. Return code: %s" % retcode)
    #endIf
    
    # Create the EFS provisioner service account
    TR.info(methodName,"Invoking: kubectl create -f %s" % self.serviceAccountPath)

    retcode = call(["kubectl", "create", "-f", self.serviceAccountPath])
    if (retcode != 0):
      raise Exception("Error calling kubectl. Return code: %s" % retcode)
    #endIf
    
    TR.info(methodName,"Invoking: kubectl apply -f %s" % self.efsProvPath)
    retcode = call(["kubectl", "apply", "-f", self.efsProvPath])
    if (retcode != 0):
      raise Exception("Error calling kubectl. Return code: %s" % retcode)
    #endIf
        
  #endDef
  
  
  def configureEFS(self):
    """
      Run the playbook to configure EFS on the target nodes.
      Configure an EFS dynamic storage provisioner (storageclass)
    """
    #self.createVarFile(self.varFilePath,self.varTemplatePath)
    self.createConfigFile(configFilePath=self.varFilePath,
                          templateFilePath=self.varTemplatePath,
                          parameters=self.efsParameters,
                          keywordMap=EFSTemplateKeywordMap,
                          specialValues=EFSSpecialValues
                          )
    self.runAnsiblePlaybook(playbook=self.playbookPath, extraVars=self.varFilePath)
    self.configureEFSProvisioner()
  #endDef
#endClass