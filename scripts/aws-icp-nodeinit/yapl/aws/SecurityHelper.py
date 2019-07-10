"""
Created on Dec 21, 2018

@author: Peter Van Sickel - pvs@us.ibm.com
"""

import os, fnmatch
import boto3
import yaml
import ipaddr

from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.AWSExceptions import AWSStackResourceException
from yapl.exceptions.Exceptions import InvalidParameterException
from yapl.exceptions.Exceptions import InvalidArgumentException
from yapl.exceptions.Exceptions import InvalidConfigurationFile


TR = Trace(__name__)


class CFN_SecurityGroup(object):
  """
    Class instance that wraps the CloudFormation representation of a security group.
  """
  
  def __init__(self, cfnsg):
    """
      Constructor
      
      Make the top level CFN attributes, instance variables.
      
      WARNING: This implementation is not necessarily complete. It has only been tested
      for what was needed for MVP1 of the ICP QuickStart. (PVS 28 DEC 2018)
    """
    object.__init__(self)
    
    self.group_name = cfnsg.get('group_name')
    self.Type = cfnsg.get('Type')
    self.Properties = cfnsg.get('Properties')
  #endIf
  
  
  def getProperty(self, name):
    """
      Return the property value for the property with the given name.
    """
    result = None
    if (self.Properties):
      result = self.Properties.get(name)
    #endIf
    return result
  #endDef
  
  
  def getIngressPermissions(self):
    """
      Return a list of ingress permissions with the structure expected 
      for a boto3 EC2 SecurityGroup ip_permissions attribute, i.e., 
      a list of dictionaries where each dictionary has the following 
      key value pairs:
        FromPort (integer)
        IpProtocol (string)
        IpRanges (list) 
        ToPort (integer)
        
      The other possible attributes are not supported.
      See the boto3 doc for more details: 
      https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.SecurityGroup.ip_permissions
    """
    methodName = "getIngressPermissions"
    
    result = []
    ingressRules = self.getProperty('SecurityGroupIngress')
    if (not ingressRules):
      if (TR.isLoggable(Level.FINER)):
        TR.finer(methodName,"No SecurityGroupIngress property defined for SecurityGroup: %s" % self.group_name)
      #endIf
    else:
      for rule in ingressRules:
        newRule = {}
        newRule['FromPort'] = int(rule.get('FromPort'))
        newRule['ToPort'] = int(rule.get('ToPort'))
        newRule['IpProtocol'] = rule.get('IpProtocol')
        newRule['IpRanges'] = [{'CidrIp': rule.get('CidrIp'), 'Description': rule.get('Description')}]
        result.append(newRule)
      #endFor
    #endIf
    return result
  #endDef
  
#endClass


class EC2_SecurityGroup(object):
  """
    Identical structure to boto3 EC2.SecurityGroup
    
    Working with security group instances that have structure identical to boto3 
    EC2.SecurityGroup simplifies the script methods where things like comparisons 
    or other security group processing is done.
    
  """
  
  def __init__(self, cfnsg):
    """
      Constructor
      
      Convert the CFN_SecurityGroup representation into an instance of an 
      EC2_SecurityGroup which has structure more-or-less identical to the  
      boto3 EC2.SecurityGroup.
    """
    object.__init__(self)
    self.group_name = cfnsg.group_name
    self.vpc_id = cfnsg.getProperty('VpcId')
    self.description = cfnsg.getProperty('GroupDescription')
    self.ip_permissions = cfnsg.getIngressPermissions()
    
  #endDef
  
  
#endClass


class SecurityHelper(object):
  """
    Class to provide help dealing with security configuration in AWS deployments.
    
    Update ingress rules in a SecurityGroup.
    
    For sample boto3 code dealing with security groups see:
    https://boto3.amazonaws.com/v1/documentation/api/latest/guide/ec2-example-security-group.html
    
    WARNING: SecurityHelper is only developed for dealing with limited use cases where SecurityGroup
    ingress rules are modified based on macro substitutions of the CidrIp of the rule.
  """

  IntrinsicVariables = {}
  IntrinsicVariableNames = []
  
  SimpleProperties = ['VpcId', 'GroupDescription']
  RuleProperties = ['SecurityGroupIngress']
  RuleIntrinsicVariableNames = ['BootNodePrivateIPv4Address','BootNodePublicIPv4Address','NATGatewayPublicIPv4Address']

  def __init__(self, stackId=None, intrinsicVariables=None, configPath=None):
    """
      stackId - the resource ID of the CloudFormation stack to be used for processing security groups.
                Typically, all security groups are defined in a particular CloudFormation stack used 
                to define security profiles, roles and security groups.
                 
      intrinsicVariables - dictionary of key-value pairs that are predefined for the given deployment
                           and may be used for substitution macros in the security configuration file(s).
     
      Optional parameters:
        configPath - file system path to a security configuration YAML file or directory of YAML files
    """
    object.__init__(self)
        
    if (not stackId):
      raise MissingArgumentException("A stack ID must be provided.")
    #endIf
    
    self.stackId = stackId
    
    if (not intrinsicVariables):
      raise MissingArgumentException("A collection of intrinsic variables must be provided.")
    #endIf

    self.IntrinsicVariables = intrinsicVariables.copy()
    self.IntrinsicVariableNames = self.IntrinsicVariables.keys()
    
    self.configPath = configPath
    
    self.cfnClient = boto3.client('cloudformation')
    self.ec2Resource = boto3.resource('ec2')
    self.ec2Client = boto3.client('ec2')
    
  #endDef

  
  def __getattr__(self,attributeName):
    """
      Support for attributes that are defined in the IntrinsicVariableNames list
      and with values in the IntrinsicVariables dictionary.  
    """
    attributeValue = None
    if (attributeName in self.IntrinsicVariableNames):
      attributeValue = self.IntrinsicVariables.get(attributeName)
    else:
      raise AttributeError("%s is not an IntrinsiceVariableName" % attributeName)
    #endIf
  
    return attributeValue
  #endDef


  def __setattr__(self,attributeName,attributeValue):
    """
      Support for attributes that are defined in the IntrinsicVariableNames list
      and with values in the IntrinsicVariables dictionary.
      
      NOTE: The IntrinsicVariables are intended to be read-only.  This method is
      here for completeness.
    """
    if (attributeName in self.IntrinsicVariableNames):
      self.IntrinsicVariables[attributeName] = attributeValue
    else:
      object.__setattr__(self, attributeName, attributeValue)
    #endIf
  #endDef

  
  def getSecurityGroup(self, stackId, cfnName):
    """
      Return an instance of a boto3 SecurityGroup for the security  
      group with the given CloudFormation name in the given stack (stackId).
      The check for cfnName is uses a string find() method to determine if
      the cfnName is part of the full security group name.
      
      There can be only one security group in a given CloudFormation template
      with a given name so using a find() on the full CloudFormation name will
      yield the specific security group of interest.
      
      If no security group exists in the given stack that contains the given 
      cfnName as part of its name, then None is returned.
      
      NOTE: The actual security group names get modified with template name and
      the template unique string as well as the CloudFormation name and a unique
      string: Some examples: 
         pvsICPTestStack-2018-1230-03-IAMResources-MF2EID48LG86-ExternalSSHSecurityGroup-KILD6SMTXBLU
         pvsICPTestStack-2018-1230-03-IAMResources-MF2EID48LG86-ICPMasterSecurityGroup-1TO0G441JP4LT
    """
    methodName = "getSecurityGroup"

    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Looking for security group with CloudFormation name: %s in stack: %s" % (cfnName,stackId))
    #endIf
        
    result = None
    
    securityGroupIds = self.getSecurityGroups(stackId)
    if (not securityGroupIds):
      TR.info(methodName,"There are no security groups in stack: %s" % stackId)
    else:   
      for sgid in securityGroupIds:
        sg = self.ec2Resource.SecurityGroup(sgid)
        if (TR.isLoggable(Level.FINEST)):
          TR.finest(methodName,"Checking security group with full name: %s" % sg.group_name)
        #endIf
        if (sg.group_name.find(cfnName) >= 0):
          result = sg
          break
        #endIf
      #endFor
      if (not result):
        TR.info(methodName,"No security group with CloudFormation name: %s in stack: %s" % (cfnName,stackId))
      #endIf
    #endIf
    return result
  #endDef
  
    
  def getSecurityGroups(self, stackId):
    """
      Return a list of SecurityGroup instance IDs 
    """
    methodName = "getSecurityGroups"
    
    result = []
    
    if (not stackId):
      raise MissingArgumentException("A stack ID (stackId) is required.")
    #endIf
    
    response = self.cfnClient.list_stack_resources(StackName=stackId)
    if (not response):
      raise AWSStackResourceException("Empty response for CloudFormation list_stack_resources for stack: %s" % stackId)
    #endIf
    
    stackResources = response.get('StackResourceSummaries')
    
    
    if (not stackResources):
      TR.warning(methodName,"No resources defined in stack: %s" % stackId)
    else:
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"%d resources defined in stack: %s " % (len(stackResources),stackId))
      #endIf
      for resource in stackResources:
        resourceType = resource.get('ResourceType')
        if (resourceType == 'AWS::EC2::SecurityGroup'):
          instanceId = resource.get('PhysicalResourceId')
          result.append(instanceId)       
        #endIf
      #endFor
    #endIf

    return result
  #endDef


  def stringMacroCheck(self,string,parameterNames,keywordMap={}):
    """
      Return a dictionary with one or more key-value pairs from the keywordMap that 
      have a macro substitution present in string.
      
      If keywordMap is empty then no translation is needed from parameter names to
      macro keyword is done, i.e, the macro name is the parameter name.
      
      If parameterNames is empty (or None), then nothing to do and an empty result is returned.  
        
      Otherwise, return an empty dictionary. 
    """
    result = {}
    if (parameterNames):
      for parmName in parameterNames:
        if (keywordMap):
          macroName = keywordMap.get(parmName)
          if (not macroName):
            raise InvalidParameterException("The parameter name: %s was not found in the given keyword mappings hash map: %s" % (parmName,keywordMap))
          #endIf
        else:
          macroName = parmName
        #endIf
        macro = "${%s}" % macroName
        if (string.find(macro) >= 0):
          result[parmName] = macroName
        #endIf
      #endFor
    #endIf
    return result
  #endDef
  
  
  def expandString(self,value,parameters):
    """
      Return either the same value (no macros in the given value),
      or a new value with all macros embedded in the given value expanded  
      to take on the value as defined for each macro in the parameters dictionary.
    """
    methodName = "expandString"
    
    parameterNames = parameters.keys()
    substitutions = self.stringMacroCheck(value,parameterNames)
    if (substitutions):
      parmNames = substitutions.keys()
      for parmName in parmNames:
        macroName = substitutions[parmName]
        parmValue = parameters[parmName]
        macro = "${%s}" % macroName
        if (TR.isLoggable(Level.FINEST)):
          TR.finest(methodName,"For value: '%s', replacing: %s with: %s" % (value,macro,parmValue))
        #endIf
        value = value.replace(macro,"%s" % parmValue)
      #endFor
    #endIf
    return value
  #endDef
  
  
  def expandList(self,target,macro,valueList):
    """
      Return a list of values created from the given target by expanding the given macro
      once for each value in the given value list.
    """
    
    result = []
    for value in valueList:
      result.append(target.replace(macro,value))
    #endFor
    
    return result  
  #endDef
  
  
  def ruleMacroCheck(self,rule,parameters):
    """
      Return a list of one or more substitutions to make based on the macro 
      in the CidrIp of the given rule.
      
      The CidrIp can have only one macro. 
      
      The macro is delimited by ${}.  
      The macro names are assumed to be one on the names in self.RuleIntrinsicVariableNames.
      (This method is not interested in every intrinsic variable.)
      
      If a parameter has multiple values, then a rule is created for each value.
      (See expandList() for details on creating a new rule for each parameter value.)
    """
    
    result = None

    cidrIp = rule.get('CidrIp')
    
    for name in self.RuleIntrinsicVariableNames:
      macro = "${%s}" % name
      if (cidrIp.find(macro) >= 0):
        parmValue = parameters.get(name)
        if (type(parmValue) == type([])):
          result = self.expandList(cidrIp,macro,parmValue)
        else:
          result = [cidrIp.replace(macro,parmValue)]
        #endIf
        break
      #endIf
    #endFor
    
    return result
  #endDef
  
  
  def expandRule(self,rule,parameters):
    """
      Return a list of one or more expanded ingress/egress rules. 
      
      A rule looks like:
        Description: <description_string>
        IpProtocol: <protocol_sting>
        FromPort: <port_number>
        ToPort: <port_number>
        CidrIp: <network_cidr_string>  
        
      Macros are only expected in the CidrIp.
      A macro may be single valued or multiple valued (a list of IPs).
      When a macro is multiple valued, multiple rules are created, one for each IP.
         
    """    
    substitutions = self.ruleMacroCheck(rule,parameters)
    if (not substitutions):
      # shouldn't actually happen, but for completeness
      result = [rule]
    else:
      result = []
      for cidrIp in substitutions:
        expandedRule = rule.copy()
        expandedRule['CidrIp'] = cidrIp
        result.append(expandedRule)
      #endFor
    #endIf    
    
    return result
  #endDef
  
  
  def expandRules(self,rules,parameters):
    """
      Return a list of expanded ingress/egress rules.
    """
    newRules = []
    for rule in rules:
      expandedRules = self.expandRule(rule,parameters)
      newRules.extend(expandedRules)
    #endFor
    return newRules
  #endDef
  
  
  def expandResource(self,resource, parameters):
    """
      Return the resource with all values with macros expanded.
      
      A resource has a Type and Properties.  The Type is always static.
      A property may have a simple value e.g., a string or number.
      A property may have a complex value, e.g., a list or dictionary.
      The type of the property is determined based on predefined lists
      of property names:
        SimpleProperties - names of properties with a string value
        RuleProperties   - names of properties with list of ingress/egress rules
    """
    
    properties = resource.get('Properties')
    propertyNames = properties.keys()
    
    for name in propertyNames:
      propertyValue = properties.get(name)
      if name in self.SimpleProperties:
        propertyValue = self.expandString(propertyValue,parameters)
        properties[name] = propertyValue
      elif (name in self.RuleProperties):
        newRules = self.expandRules(properties[name],parameters)
        properties[name] = newRules
      else:
        raise Exception("Unexpected type of property value for property: %s" % name)
      #endIf
    #endFor
    
    return resource
                         
  #endDef
  
  
  def createConfigFile(self, configFilePath=None, templateFilePath=None, parameters=None):
    """
      Using the template file, fill in all the variable strings in the template
      using the given parameters.
      
      The template file is consumed as a yaml document and processed with some 
      special rules:
        If the value of a macro is a singleton, then a straight substitution is executed.
        If the value of a macro is a list with more than one element, then the construct
        where that contains that macro is replicated for each value to be substituted.
      
      Optional restArgs:
        parameters: Dictionary with the actual values of the parameters
                    The parameter values will be substituted for the corresponding
                    macro in the template file to create the configuration file.
        
        keywordMap: The mapping of parameter names to macro names (keywords) in the
                    template file.  If no keywordMap is provided it is assumed the 
                    macro names in the template file are the names of the parameters
                    in the given parameters dictionary.
                          
      A macro in the template file is delimited by ${} with the macro name in the {}.
      
    """
    methodName = "createConfigFile"
    
    if (not configFilePath):
      raise MissingArgumentException("The configuration file path must be provided.")
    #endIf
    
    if (not templateFilePath):
      raise MissingArgumentException("The template file path must be provided.")
    #endIf
  
    if (not parameters):
      raise MissingArgumentException("Substitution parameters must be provided.")
    #endIf
       
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Parameters: %s" % parameters)
    #endIf
    
    with open(templateFilePath, 'r') as template:
      root = yaml.load(template)
    #endWith
  
    resources = root.get('Resources')
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Resources: %s" % resources)
    #endIf
    
    resourceNames = resources.keys()
    for name in resourceNames:
      resource = resources.get(name)
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Expanding resource named: %s" % name)
      #endIf
      
      self.expandResource(resource,parameters)
      
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Expanded resource: %s" % resource)
      #endIf
    #endFor
      
    with open(configFilePath,'w') as configFile:
      yaml.dump(root,stream=configFile,default_flow_style=False)
    #endWith
  
  #endDef
  

  def old_createConfigFile(self, configFilePath=None, templateFilePath=None, **restArgs):
    """      
      Using the template file, fill in all the variable strings in the template
      using the given parameters.
      
      Optional restArgs:
        parameters: Dictionary with the actual values of the parameters
                    The parameter values will be substituted for the corresponding
                    macro in the template file to create the configuration file.
        
        keywordMap: The mapping of parameter names to macro names (keywords) in the
                    template file.  If no keywordMap is provided it is assumed the 
                    macro names in the template file are the names of the parameters
                    in the given parameters dictionary.
                    
      Comment lines in the template file are written immediately to the config file.
      
      A macro in the template file is delimited by ${} with the macro name in the {}.
      
    """
    methodName = "createConfigFile"
    
    if (not configFilePath):
      raise MissingArgumentException("The configuration file path must be provided.")
    #endIf
    
    if (not templateFilePath):
      raise MissingArgumentException("The template file path must be provided.")
    #endIf
  
    parameters = restArgs.get('parameters')
    if (parameters):   
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Parameters: %s" % parameters)
      #endIf
      parameterNames = parameters.keys()
    else:
      parameterNames = []
    #endIf
    
    keywordMap = restArgs.get('keywordMap',{})
    if (keywordMap):
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Keyword Map: %s" % keywordMap)
      #endIf
    #endIf
    
    if (keywordMap and not parameterNames):
      parameterNames = keywordMap.keys()
    #endIf
    
    try:
      with open(templateFilePath,'r') as templateFile, open(configFilePath,'w') as configFile:
        for line in templateFile:
          # Need to strip at least the newline character(s)
          line = line.rstrip()
          if (line.startswith('#')):
            configFile.write("%s\n" % line)
          else:
            if (TR.isLoggable(Level.FINEST)):
              TR.finest(methodName,"Checking line for macros: %s" % line)
            #endIf
            
            substitutions = self.stringMacroCheck(line,parameterNames,keywordMap)
            
            if (not substitutions):
              configFile.write("%s\n" % line)
            else:
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"Substitutions: %s" % substitutions)
              #endIf
            
              parmNames = substitutions.keys()
              
              for parmName in parmNames:
                macroName = substitutions[parmName]
                parmValue = parameters[parmName]
                macro = "${%s}" % macroName
                if (TR.isLoggable(Level.FINEST)):
                  TR.finest(methodName,"LINE: %s\n\tReplacing: %s with: %s" % (line,macro,parmValue))
                #endIf
                line = line.replace(macro,"%s" % parmValue)
              #endFor

              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"NEW LINE: %s" % line)
              #endIf
              
              configFile.write("%s\n" % line)
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating security configuration file: %s from template file: %s" % (configFilePath,templateFilePath), e)
      raise
    #endTry
  #endDef


  def includeYaml(self, kind, include=[], exclude=[]):
    """
      Return True if the given kind is in the include list and not in the exclude list.
      
      If both include and exclude are empty then True is returned.
      
      If include has members and exclude is empty then True is returned only if kind is in the include list.
      If include is empty and exclude has members, then True is returned as long as kind is not a member of exclude.
      
      If both include and exclude have members, then True is returned only if kind is in the include list and 
      not in the exclude list.
    """
    
    if (not include and not exclude): return True
    if (include and not exclude): return kind in include
    if (not include and exclude): return kind not in exclude
    if (include and exclude): return kind in include and kind not in exclude
  #endIf
  
  
  def getYaml(self, dirPath, include=[], exclude=[]):
    """
      Return a list of full paths to all the .yaml files in the given dirPath directory. 
      
      dirPath - Path to the directory of yaml files to be considered.  (only .yaml files are considered)
      
      include - a list of names of the kind of yaml file to be included in the result set.
      exclude - a list of names of the kind of yaml file to be excluded from the result set.
      
      If include and exclude are both empty, then the result set includes all .yaml files in 
      the given dirPath directory.
      
      If either include or exclude have members, then if a yaml file does not have a kind 
      attribute, it is not included in the result set.
      
      See includeYaml() for a description of the include and exclude lists to be used as filters for
      the kind of yaml files to include in the returned list.
      
      For different approaches to listing files in a directory see:
      See https://stackabuse.com/python-list-files-in-a-directory/
      
      NOTE: The yaml.load_all() method returns a generator.  In the code below that
      gets converted to a list for convenience.
    """
    methodName="getYaml"
    
    files = os.listdir(dirPath)
    
    pattern = "*.yaml"
    yamlFiles = [os.path.join(dirPath,f) for f in files if fnmatch.fnmatch(f,pattern)]

    if (include or exclude):
            
      if (include and TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Yaml files to be included: %s" % include)
      #endIf
    
      if (exclude and TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Yaml files to be excluded: %s" % exclude)
      #endIf
    
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Yaml files to consider: %s" % yamlFiles)
      #endIf
      
      includedFiles = []
      for f in yamlFiles:
        with open(f, 'r') as yamlFile:
          docs = list(yaml.load_all(yamlFile))
        #endWith
        
        # we only care about the first doc in the file
        doc = docs[0]
        
        kind = doc.get('kind')
        if (kind and self.includeYaml(kind,include,exclude)):
          includedFiles.append(f)
        #endIf
      #endFor
            
      yamlFiles = includedFiles
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Included yaml files: %s" % yamlFiles)
    #endIf
    
    return yamlFiles
  #endDef
  
  
  def _IPv4RangeCovered(self,xIpRanges,yIpRange):
    """
      Return True if the given yIpRange is covered by the xIpRanges.
      Otherwise, return False.
      
      Finally, the ipaddr Python library does the heavy lifting. :-)
      See: https://stackoverflow.com/questions/17206679/check-if-two-cidr-addresses-intersect
    """
    result = False
    
    yCidrIp = yIpRange.get('CidrIp')
    yNetwork = ipaddr.IPNetwork(yCidrIp)
    for xIpRange in xIpRanges:
      xCidrIp = xIpRange.get('CidrIp')
      xNetwork = ipaddr.IPNetwork(xCidrIp)
      if (xNetwork.overlaps(yNetwork)):
        result = True
        break
      #endIf
    #endFor
    
    return result
  #endDef
  
  
  def _allIPv4RangesCovered(self, xIpRanges, yIpRanges):
    """
      Return True if all of the yIpRanges are covered by the xIpRanges
      
      IpRanges is a list of dictionaries that look like: {CidrIp: (string), Description: (string)}
      
      The Description is ignored.
    """
    result = True
    for yIpRange in yIpRanges:
      if (not self._IPv4RangeCovered(xIpRanges,yIpRange)): 
        result = False
        break
      #endIf
    #endFor
    
    return result
  #endDef
  
  
  def _thisRuleCovers(self, ruleX, ruleY):
    """
      Return True if ruleY is covered by ruleX
      
      ruleX and ruleY are in the boto3 form that is ip_permissions or ip_permissions_egress
      
      WARNING: Only support for IPv4 rules is currently implemented.
      
      Attributes compared for identical values:
        FromPort (integer)
        IpProtocol (string)
        IpRanges (list) 
        ToPort (integer)
    """
    methodName = "_thisRuleCovers"
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Checking ruleX: %s\n\t Covers ruleY: %s" % (ruleX,ruleY))
    #endIf
    
    if (ruleX.get('IpProtocol') != ruleY.get('IpProtocol')): return False
    
    if (ruleX.get('FromPort') != ruleY.get('FromPort')): return False
    
    if (ruleX.get('ToPort') != ruleY.get('ToPort')): return False
    
    if (not self._allIPv4RangesCovered(ruleX.get('IpRanges'), ruleY.get('IpRanges'))): return False
    
    return True
    
  #endDef
  
  
  
  def _ruleCovered(self, existingRules, ruleY):
    """
      Return true if the list of existing ingress/egress rules covers the given 
      ingress/egress rule (ruleY). Otherwise, return false.

    """
    methodName = "_ruleCovered"
    
    result = False
    
    for ruleX in existingRules:
      if self._thisRuleCovers(ruleX,ruleY):
        if (TR.isLoggable(Level.FINER)):
          TR.finer(methodName,"Rule: %s is covered by existing rule: %s" % (ruleY,ruleX))
        #endIf
        result = True
        break
      #endIf
    #endFor
    return result
  #endIf
  
  
  def _getIngressUpdates(self,existing_sg,sg):
    """
      Return a list of rules that can be used to update security group ingress rules.
    """
    methodName = "_getIngressUpdates"
    new_ip_permissions = []
    existing_ip_permissions = existing_sg.ip_permissions
    for rule in sg.ip_permissions:
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Checking existing rules for coverage of rule: %s" % rule)
      #endIf
      if (not self._ruleCovered(existing_ip_permissions,rule)):
        new_ip_permissions.append(rule)
      #endIf
    #endFor
    return new_ip_permissions
  #endDef


  def _getEgressUpdates(self, existing_sg, sg):
    """
      NOT IMPLEMENTED YET
    """
    return []
  #endDef
  
  
  def _updateSecurityGroup(self, existing_sg, sg):
    """
      Update the existing boto3 SecurityGroup (existing_sg) instance with the updates 
      intrinsic to the security group updates object (sg).
      
      Helper for _processSecurityGroup().
    """
    methodName = "_updateSecurityGroup"
    
    new_ip_permissions = self._getIngressUpdates(existing_sg, sg)
    if (new_ip_permissions):
      data = self.ec2Client.authorize_security_group_ingress(GroupId=existing_sg.group_id, IpPermissions=new_ip_permissions)
      TR.info(methodName,"Updated SecurityGroup: %s with new ingress permissions: %s" % (existing_sg.group_name,data))
    #endIf
    
    new_ip_permissions_egress = self._getEgressUpdates(existing_sg, sg)
    if (new_ip_permissions_egress):
      pass
    #endIf
    
  #endDef
  
  
  def _createSecurityGroup(self, securityGroup):
    """
      Create a new security group instance based on the given securityGroup object 
      defined in a yaml file.

      Helper for _processSecurityGroup().
    """
    raise Exception("Not implemented yet.")
  #endDef


  def _processSecurityGroup(self, sg):
    """
      Process an object of type: EC2_SecurityGroup
      
      If there is a security group defined with the same name as the given security
      group, then the given security group is checked for any new ingress or egress 
      rules to be added to the existing security group.
      
      If there is no security group already defined with the name of the given 
      security group then a new security group is created as defined by the given
      security group.
    """
    methodName = "_processSecurityGroup"

    if (not sg):
      raise MissingArgumentException("A security group object (securityGroup) must be provided.")
    #endIf

    if TR.isLoggable(Level.FINER):
      TR.finer(methodName,"Processing security group: %s" % sg.group_name)
    #endIf    
    
    # existing_sg is an instance of the boto3 EC2.SecurityGroup
    existing_sg = self.getSecurityGroup(self.stackId, sg.group_name)
    if (not existing_sg):
      self._createSecurityGroup(sg)
    else:
      self._updateSecurityGroup(existing_sg,sg)
    #endIF
  #endDef
  

  def _configureSecurity(self, configFile):
    """
      Translate the security configuration defined in the given configuration yaml file to the 
      corresponding CloudFormation security configuration.
      
      Helper for configeSecurity() - processes one security configuration file.
      
      Currently, only the AWS::EC2::SecurityGroup resource type is supported.
    """
    methodName = "_configureSecurity"
    
    TR.info(methodName,"Processing security configuration file: %s" % configFile)
    
    with open(configFile, 'r') as f:
      doc = yaml.load(f)
    #endWith
    
    resources = doc.get('Resources')
    if (not resources):
      raise InvalidConfigurationFile("The file: %s, does not have a top level Resources attribute." % configFile)
    #endIf
    
    resourceNames = resources.keys()
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Processing resources: %s" % resourceNames)
    #endIf
    securityGroups = []
    for name in resourceNames:
      r = resources[name]
      if (r.get('Type') and r.get('Type') == 'AWS::EC2::SecurityGroup'):
        # We need to add in the name attribute
        r['group_name'] = name
        securityGroups.append(r)
      #endIf
    #endFor
    
    if (not securityGroups):
      TR.warning(methodName,"No resources of Type AWS::EC2::SecurityGroup found in file: %s" % configFile)
    else:
      for sg in securityGroups:
        cfnsg = CFN_SecurityGroup(sg)
        ec2sg = EC2_SecurityGroup(cfnsg)
        if (TR.isLoggable(Level.FINEST)):
          TR.finest(methodName,"Processing EC2 SecurityGroup: %s" % ec2sg.group_name)
        #endIf
        self._processSecurityGroup(ec2sg)
      #endFor
    #endIf
  #endDef
  

  def configureSecurity(self, configPath=None):
    """
      Process one or more security configuration files, either given in the configPath 
      or associated with the instance at the time it was created.
    """
    
    if (not configPath):
      configPath = self.configPath
    else:
      self.configPath = configPath
    #endIf
    
    if (not configPath):
      raise MissingArgumentException("The security configuration file or directory path must be provided either at instance creation or on the method call.")
    #endIf
    
    if (os.path.isdir(configPath)):
      templateFiles = self.getYaml(configPath)
      if (not templateFiles):
        raise InvalidArgumentException("No .yaml files found in directory path: %s" % configPath)
      #endIf
    else:
      if (not os.path.isfile(configPath)):
        raise InvalidArgumentException("The given path is not a file: %s" % configPath)
      #endIf
      templateFiles = [configPath]
    #endIf
    
    stagingDir = os.path.join(os.getcwd(),'staging')
    # Configuration files get created in the staging directory.
    if (not os.path.exists(stagingDir)):
      os.mkdir(stagingDir)
    #endIf
    
    for template in templateFiles:
      baseName = os.path.basename(template)
      rootName,ext = os.path.splitext(baseName)
      configFilePath = os.path.join(stagingDir,"%s-config%s" % (rootName,ext))
      
      self.createConfigFile(configFilePath=configFilePath,
                            templateFilePath=template,
                            parameters=self.IntrinsicVariables
                            )
      
      self._configureSecurity(configFilePath)
    #endFor
  #endDef
  
#endClass