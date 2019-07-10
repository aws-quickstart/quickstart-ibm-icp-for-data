
"""
Created on Aug 6, 2018

@author: Peter Van Sickel - pvs@us.ibm.com
"""
from subprocess import call
import socket
import boto3
from yapl.utilities.Trace import Trace, Level
import yapl.utilities.Scrubber as Scrubber
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.Exceptions import InvalidParameterException
from yapl.exceptions.AWSExceptions import AWSStackResourceException
from yapl.exceptions.ICPExceptions import ICPInstallationException

TR = Trace(__name__)


"""
  The StackParameters are passed in to the constructor from the caller.
"""
StackParameters = {}
StackParameterNames = []


# NOTE: The key names for TemplateKeywordMapping must be alpha-numeric characters only.
#       The key names may be parameter names used in the CloudFormation template that 
#       deploys the ICP cluster resources.  Not all of the key names are CF parameter
#       names.
TemplateKeywordMappings = {
  'AdminPassword':                   'ADMIN_PASSWORD',
  'AdminUser':                       'ADMIN_USER',
  'CalicoTunnelMTU':                 'CALICO_TUNNEL_MTU',
  'CloudProvider':                   'CLOUD_PROVIDER',
  'ClusterCADomain':                 'CLUSTER_CA_DOMAIN',
  'ClusterCIDR':                     'CLUSTER_CIDR',
  'ClusterDomain':                   'CLUSTER_DOMAIN',
  'ClusterLBAddress':                'CLUSTER_LB_ADDRESS',
  'ClusterDNSName':                  'CLUSTER_DNS_NAME',
  'ClusterName':                     'CLUSTER_NAME',
  'ClusterVIP':                      'CLUSTER_VIP',
  'ClusterVIPIface':                  'CLUSTER_VIP_IFACE',
  'CustomMetricsAdapter':            'CUSTOM_METRICS_ADAPTER',
  'ExcludedMgmtServices':            'EXCLUDED_MGMT_SERVICES',
  'GlusterFS':                       'GLUSTERFS',
  'ImageSecurityEnforcement':        'IMAGE_SECURITY_ENFORCEMENT',
  'Istio':                           'ISTIO',
  'KubletNodeName':                  'KUBLET_NODENAME',
  'Metering':                        'METERING',
  'Minio':                           'MINIO',
  'Monitoring':                      'MONITORING',
  'ProxyLBAddress':                  'PROXY_LB_ADDRESS',
  'ProxyVIP':                        'PROXY_VIP',
  'ProxyVIPIface':                   'PROXY_VIP_IFACE',
  'ServiceCIDR':                     'SERVICE_CIDR',
  'ServiceCatalog':                  'SERVICE_CATALOG',
  'VulnerabilityAdvisor':            'VULNERABILITY_ADVISOR' 
}

ConfigurationParameterNames = TemplateKeywordMappings.keys()

"""
  On the Ubuntu images that have been tested the NIC name is ens5.  
  TODO: Enhance the script to get the NIC names from the master node and the proxy nodes.
"""
AWSDefaultParameterValues = {
  'CalicoTunnelMTU':          8981,
  'CloudProvider':            'aws',
  'CluserVIPIface':           'ens5',
  'CustomMetricsAdapter':     'disabled',
  'ExcludedMgmtServices':     ["istio", "vulnerability-advisor", "custom-metrics-adapter"],
  'GlusterFS':                'disabled',
  'ImageSecurityEnforcement': 'enabled',
  'Istio':                    'disabled',
  'KubletNodeName':           'fqdn',
  'Metering':                 'enabled',
  'Minio':                    'disabled',
  'Monitoring':               'enabled',
  'ProxyVIPIface':            'ens5',
  'ServiceCatalog':           'enabled',
  'VulnerabilityAdvisor':     'disabled'
}

# ELB names in the AWS stack
MasterNodeLoadBalancer = 'MasterNodeLoadBalancer'
ProxyNodeLoadBalancer = 'ProxyNodeLoadBalancer'

"""
  ICP 2.1 optional management services.
"""
OptionalManagementServices_21 = ["custom-metrics-adapter", "istio", "metering", "monitoring", "service-catalog", "vulnerability-advisor"]

"""
  TODO - Add additional optional management services supported by ICP 3.1 once they have been implemented in the deployment scripting.
"""
OptionalManagementServices = ["custom-metrics-adapter", "image-security-enforcement", "istio", "metering", "monitoring", "service-catalog", "vulnerability-advisor"]

"""
  ServiceNameParameterMap is used to map the service names as they would appear in config.yaml attribute names 
  to the corresponding parameter names that are used in creating the config.yaml file.  Another approach would 
  have been to use the services names directly in the parameter names dictionary.
  
  NOTE: GlusterFS and Minio are not supported by the deployment automation and are always disabled.
"""
ServiceNameParameterMap = { 
  "custom-metrics-adapter":     "CustomMetricsAdapter",
  "image-security-enforcement": "ImageSecurityEnforcement",
  "istio":                      "Istio",
  "metering":                   "Metering",
  "monitoring":                 "Monitoring",
  "service-catalog":            "ServiceCatalog",
  "vulnerability-advisor":      "VulnerabilityAdvisor"
}


class ConfigureICP(object):
  """
    Class that supports the manipulation of a config.yaml template file that
    gets used to drive the installation of IBM Cloud Private (ICP).
  """
  
  SensitiveParameters = {}

  def __init__(self, stackIds=None, configTemplatePath=None, **restArgs):
    """
      Constructor
      
      The stackIds input parameter is expected to be a list of AWS stack resource IDs.
      The first stack ID in the list is assumed to be the root stack.
    """
    object.__init__(self)
    
    self.cfnResource = boto3.resource('cloudformation')
    self.cfnClient = boto3.client('cloudformation')
    self.elbv2Client = boto3.client('elbv2')
    self.ec2 = boto3.resource('ec2')
    
    self.rootStackId = '' 
    self.configTemplatePath = ''
    self.configParameters = {}
    self.vips = {}
    self.appDomains = []
    self._init(stackIds=stackIds, configTemplatePath=configTemplatePath, **restArgs)
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
      likely they would be set once they are initialized.
    """
    if (attributeName in StackParameterNames):
      StackParameters[attributeName] = attributeValue
    else:
      object.__setattr__(self, attributeName, attributeValue)
    #endIf
  #endDef


  def getPrimaryAppDomain(self):
    """
      Return the first member of the list of application domains provided in ApplicationDomains
      in the input parameters to the root template.
      
      AppicationDomains must have at least one value.
    """
    if (not self.appDomains):
      self.appDomains = self.ApplicationDomains.split(',')
    #endIf
    
    return self.appDomains[0]
  #endDef
  
  
  def _init(self, stackIds=None, configTemplatePath=None, **restArgs):
    """
      Helper for the __init__() constructor.  
      
      All the heavy lifting for initialization of the class occurs in this method.
    """
    methodName = '_init'
    global StackParameters, StackParameterNames
    
    
    if (not stackIds):
      raise MissingArgumentException("The CloudFormation stack resource IDs must be provided.")
    #endIf
    
    self.rootStackId = stackIds[0]
    
    if (not configTemplatePath):
      raise MissingArgumentException("The path to the config.yaml template file must be provided.")
    #endIf
    
    self.configTemplatePath = configTemplatePath

    self.etcHostsPlaybookPath = restArgs.get('etcHostsPlaybookPath')
    
    self.SensitiveParameters = restArgs.get('sensitiveParameters')
    
    StackParameters = restArgs.get('stackParameters')
    if (not StackParameters):
      raise MissingArgumentException("The stack parameters must be provided.")
    #endIf
    
    StackParameterNames = StackParameters.keys()
    
    configParms = self.getConfigParameters(StackParameters)
    if (TR.isLoggable(Level.FINEST)):
      cleaned = Scrubber.dreplace(configParms, self.SensitiveParameters)
      TR.finest(methodName,"Scrubbed parameters defined in the stack:\n\t%s" % cleaned)
    #endIf
    
    self.configParameters = self.fillInDefaultValues(**configParms)

    self.masterELBAddress = self.getLoadBalancerIPAddress(stackIds,elbName="MasterNodeLoadBalancer")
    if (not self.masterELBAddress):
      raise ICPInstallationException("An ELB with a Name tag of MasterNodeLoadBalancer was not found.")
    #endIf

    # This next block supports different ways to set up the WhichClusterLBAddress.
    # It is a debugging ploy. I got tired of changing the script to try out different options.
    if (self.WhichClusterLBAddress == 'UseMasterELBAddress'):
      # NOTE: ICP 2.1.0.3 can't handle a DNS name in the cluster_lb_address config.yaml attribute.
      masterELB = self.masterELBAddress 
    elif (self.WhichClusterLBAddress == 'UseMasterELBName'):
      masterELB = self.getLoadBalancerDNSName(stackIds,elbName="MasterNodeLoadBalancer")
    elif (self.WhichClusterLBAddress == 'UseClusterName'):
      # In the root CloudFormation template, an alias entry is created in the Route53 DNS 
      # that maps the master ELB public DNS name to the cluster CN, i.e., the ClusterName.VPCDomain.
      # Setting the cluster_lb_address to the cluster_CA_domain avoids OAuth issues in mgmt console.
      masterELB = self.ClusterDNSName
    else:
      masterELB = self.ClusterDNSName
    #endIf
    
    self.configParameters['ClusterLBAddress'] = masterELB

    self.proxyELBAddress = self.getLoadBalancerIPAddress(stackIds,elbName="ProxyNodeLoadBalancer")
    if (not self.proxyELBAddress):
      raise ICPInstallationException("An ELB with a Name tag of ProxyNodeLoadBalancer was not found.")
    #endIf
    
    if (self.WhichProxyLBAddress == 'UseProxyELBAddress'):   
      # NOTE: ICP 2.1.0.3 can't handle a DNS name in the proxy_lb_address config.yaml attribute.
      proxyELB = self.proxyELBAddress
    elif (self.WhichProxyLBAddress == 'UseProxyELBName'):
      proxyELB = self.getLoadBalancerDNSName(stackIds,elbName="ProxyNodeLoadBalancer")  
    elif (self.WhichProxyLBAddress == 'UsePrimaryAppDomain'):
      # In the root CloudFormation template, an alias entry is created in the Route53 DNS 
      # that maps the proxy ELB public DNS name to the primary application domain.
      # The primary app domain is the first entry in the list of ApplicationDomains passed 
      # into the root stack.
      proxyELB = self.getPrimaryAppDomain()
    else:
      proxyELB = self.getPrimaryAppDomain()
    #endIf
      
    self.configParameters['ProxyLBAddress'] = proxyELB
    
    self.configParameters['ClusterCADomain'] = self.ClusterDNSName
    
    # VIPs are not supposed to be needed when load balancers are used.
    # WARNING: For an AWS deployment, VIPs have never worked. 
    # Using an EC2::NetworkInterface to get an extra IP doesn't work. 
    #self.vips = self._getVIPs(self.rootStackId)
    #self.configParameters['ClusterVIP'] = self.getVIPAddress("MasterVIP")
    #self.configParameters['ProxyVIP'] = self.getVIPAddress("ProxyVIP")
    
    self.configParameterNames = self.configParameters.keys()    

    if (TR.isLoggable(Level.FINEST)):
      cleaned = Scrubber.dreplace(self.configParameters,self.SensitiveParameters)
      TR.finest(methodName,"All configuration parameters, including defaults:\n\t%s" % cleaned)
    #endIf

  #endDef
  
  
  def _getVIPNameAndAddress(self, interfaceId):
    """
      Return a tuple that is the Name tag value and the private IP address of
      the AWS::EC2::NetworkInterface with the given interfaceId
      
      The given interfaceId is an physical resource ID for an AWS::EC2::NetworkInterface resource.
      
      This method is a helper for _getVIPs().
    """
    
    interface = self.ec2.NetworkInterface(interfaceId)
    privateIP = interface.private_ip_address
    tags = interface.tag_set
    
    name = ''
    for tag in tags:
      key = tag.get('Key')
      if (key == 'Name'):
        name = tag.get('Value')
        break
      #endIf
    #endFor
    
    if (not name):
      raise ICPInstallationException("NetworkInterface: %s is expected to have a Name tag." % interfaceId)
    #endIf
   
    return  (name, privateIP)
  #endDef
    
  
  def _getVIPs(self, stackId):
    """
      Return a dictionary where the key of each entry is the VIP name
      and the value associated with each key is the private IP address.
      
      The stack with the given stackId is expected to have two 
      EC2::NetworkInterface resources that have a private IP address 
      assigned to them.  One IP address is used for the master VIP 
      and the other is used for the proxy VIP.
      
      Each NetworkInterface has a Name tag that identifies which IP
      is to be used for the MasterVIP and which for the ProxyVIP.
      The specific IP that is used for a given VIP does not matter, but
      for the purpose of knowing which is being used for what, the 
      NetworkInterface resources are named.
    """

    vips = {}
    
    if (not stackId):
      raise MissingArgumentException("A stack ID (stackId) is required.")
    #endIf
    
    response = self.cfnClient.list_stack_resources(StackName=stackId)
    if (not response):
      raise AWSStackResourceException("Empty result for CloudFormation list_stack_resources for stack: %s" % stackId)
    #endIf
    
    stackResources = response.get('StackResourceSummaries')
    if (not stackResources):
      raise AWSStackResourceException("Empty StackResourceSummaries in response from CloudFormation list_stack_resources for stack: %s." % stackId)
    #endIf

    for resource in stackResources:
      resourceType = resource.get('ResourceType')
      if (resourceType == 'AWS::EC2::NetworkInterface'):
        interfaceId = resource.get('PhysicalResourceId')
        vipName,vipAddress = self._getVIPNameAndAddress(interfaceId)
        vips[vipName] = vipAddress        
      #endIf
    #endFor

    return vips
  #endDef
  
  
  def getVIPAddress(self, vipName):
    """
      Return the VIP for the given vipName.
      
      It is assumed that the rootStackId instance variable has been initialized 
      and that the network interfaces are defined as a resource of the root stack.
      
      The getVIPAddress() method is a convenience wrapper around getting the private IP
      address for the VIP with the given name.
    """
    
    if (not self.vips):
      self.vips = self._getVIPs(self.rootStackId)
    #endIf
    
    vip = self.vips.get(vipName)
    return vip  
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

  
  def getConfigParameters(self, parameters):
    """
      Return a dictionary with configuration parameter name-value pairs extracted
      from the given parameters dictionary.
      
      Only parameters with names in the ConfigurationParameterNames list
      are included in the result set.
    
    """
    methodName = "getConfigParameters"
    
    if (not parameters):
      raise MissingArgumentException("The dictionary of parameters from which to get the configuration parameters must be provided.")
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"ConfigurationParameterNames: %s" % ConfigurationParameterNames)
    #endIf
    
    result = {}
    
    for parmName in parameters.keys():
      if (parmName in ConfigurationParameterNames):
        result[parmName] = parameters[parmName]
      #endIf
    #endFor
    
    return result
  #endDef
  
  
  def fillInDefaultValues(self, **restArgs):
    """
      Return a dictionary that is a combination of values in restArgs and 
      default parameter values in AWSDefaultParameterValues.
    """
    
    result = {}
    defaultValues = AWSDefaultParameterValues
    
    for parmName in ConfigurationParameterNames:
      parmValue = restArgs.get(parmName,defaultValues.get(parmName))
      if (parmValue):
        result[parmName] = parmValue
      #endIf
    #endFor

    return result
  #endDef
  
  
  def getClusterCN(self):
    """
      Return the ClusterDNSName
      
      The CommonName is used in the PKI certificate that is used by the management console.
    """
    
    #CN = "%s.%s" % (self.ClusterName,self.VPCDomain)
    CN = self.ClusterDNSName
    return CN
  #endDef
  
  
  def listELBResoures(self,stackId):
    """
      Return a list of ELB resource instance IDs from the given stack.
      
      An empty list is returned if there are no ELB instances in the given stack.
    """
    
    if (not stackId):
      raise MissingArgumentException("A stack ID (stackId) is required.")
    #endIf

    response = self.cfnClient.list_stack_resources(StackName=stackId)
    if (not response):
      raise AWSStackResourceException("Empty result for CloudFormation list_stack_resources for stack: %s" % stackId)
    #endIf
    
    stackResources = response.get('StackResourceSummaries')
    if (not stackResources):
      raise AWSStackResourceException("Empty StackResourceSummaries in response from CloudFormation list_stack_resources for stack: %s." % stackId)
    #endIf

    elbIIDs = []
    for resource in stackResources:
      resourceType = resource.get('ResourceType')
      if (resourceType == 'AWS::ElasticLoadBalancingV2::LoadBalancer'):
        elbInstanceId = resource.get('PhysicalResourceId')
        elbIIDs.append(elbInstanceId)        
      #endIf
    #endFor

    return elbIIDs
  #endDef
    
  
  def getELBResourceIdForName(self,stackId,elbName=None):
    """
      Return the Elastic Load Balancer ARN with the given name as the value of its Name tag.
      
      If no ELB is found with the given name in its Name tag then the empty string is returned.
    """
    if (not stackId):
      raise MissingArgumentException("A stack ID (stackId) is required.")
    #endIf

    if (not elbName):
      raise MissingArgumentException("An Elastic Load Balancer Name (elbName) must be provided.")
    #endIf
    
    elbResourceId = ""
    
    elbIIds = self.listELBResoures(stackId)
    
    if (elbIIds):
      for elbIId in elbIIds:
        response = self.elbv2Client.describe_tags(ResourceArns=[elbIId])
        if (not response):
          raise AWSStackResourceException("Empty response for ELBv2 Client describe_tags() for Elastic Load Balancer with ARN: %s" % elbIId)
        #endIf
      
        tagDescriptions = response.get('TagDescriptions')
        if (len(tagDescriptions) != 1):
          raise AWSStackResourceException("Unexpected number of TagDescriptions in describe_tags() response from ELB with ARN: %s" % elbIId)
        #endIf
        
        tagDescription = tagDescriptions[0]
        tags = tagDescription.get('Tags')
        if (not tags):
          raise AWSStackResourceException("All Elastic Load Balancers must have at least a Name tag.  No tags found for ELB with ARN: %s" % elbIId)
        #endIf
        
        for tag in tags:
          if (tag.get('Key') == 'Name'):
            if (tag.get('Value') == elbName):
              elbResourceId = tagDescription.get('ResourceArn')
              break
            #endIf
          #endIf
        #endFor
        
        if (elbResourceId): break
      #endFor
    #endIf
    
    return elbResourceId
  #endDef


  def isRoutable(self, address):
    """
      Return True if the given address is publicly routable.
      
      The given address is assumed to be an IPv4 address. 
    """
    result = True
    if (address.startswith("10.") or address.startswith("172.16.") or address.startswith("192.168.")): result = False
    return result
  #endDef
  

  def _getIPAddress(self,dnsName):
    """
      Return the first public IP address for the given DNS name.
            
      Helper method for getLoadBalancerIPAddress()
    """
    methodName = "_getIPAddress"
    
    ipAddress = ""
          
    hostname,aliases,ipaddresses = socket.gethostbyname_ex(dnsName)
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName, "Host name returned by socket.gethostbyname_ex: %s" % hostname)
    #endIf
    
    if (aliases and TR.isLoggable(Level.FINER)):
      TR.finer(methodName,"%s aliases: %s" % (dnsName,aliases))
    #endIf
    
    if (ipaddresses and TR.isLoggable(Level.FINER)):
      TR.finer(methodName,"%s IP addresses: %s" % (dnsName,ipaddresses))
    #endIf
    
    for address in ipaddresses:
      if (self.isRoutable(address)):
        # The first publicly routable IP address found is returned.
        if (TR.isLoggable(Level.FINER)):
          TR.finer(methodName,"Using ELB public IP address: %s" % ipAddress)
        #endIf
        ipAddress = address
        break
      #endIf
    #endFor
    
    return ipAddress
  #endDef
  

  def getLoadBalancerIPAddress(self,stackIds,elbName=None):
    """
      Return the public IP address for the Elastic Load Balancer V2 with the given name 
      as the value of its Name tag.
      
      The stackIds parameter holds the list of all the stacks in the CFN deployment.  
      It is assumed there is only 1 ELB in all of those stacks with the given name.
      (The public IP address of the first one found with the given name gets returned.)
      
      The boto3 API for ELBs is rather baroque.
      
      The tags are gotten using the describe_tags() method.  We need to look at the tags
      in order to find the ELB with Name tag value for the given name (elbName).  The 
      response from the describe_tags() call also includes the ARN (reource Id) for 
      the ELB with the set of tags.
      
      Once we have the ELB ARN, we can get its public IP address with a call 
      to describe_load_balancers() followed by getting the IP address attribute from
      the load balancer instance.
      
      A load balancer may be associated with more than one Availability Zone (AZ).
      A load balancer may have more than one IP address.
      
      See the boto3 documentation on describe_load_balancers()
      
      TODO: Investigate how this method should deal with multiple AZs and multiple
            IP addresses, assuming there is a use-case for such.
            
      NOTE: Testing has shown that the value of LoadBalancerAddresses may be a list of 
      1 empty dictionary.  Hence we use the Python socket.gethostbyname_ex() method to
      get the IP address list associated with the DNS name for the ELB.
    """
    methodName = "getLoadBalancerIPAddress"
    
    if (not stackIds):
      raise MissingArgumentException("A list of stack IDs (stackIds) is required.")
    #endIf
    
    if (not elbName):
      raise MissingArgumentException("The ELB name must be provided.")
    #endIf

    ipAddress = ""
    
    for stackId in stackIds:
      elbIId = self.getELBResourceIdForName(stackId, elbName=elbName)
      
      if (elbIId):
        response = self.elbv2Client.describe_load_balancers(LoadBalancerArns=[elbIId])
        if (not response):
          raise AWSStackResourceException("Empty response for ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        loadBalancers = response.get('LoadBalancers')
        if (not loadBalancers):
          raise AWSStackResourceException("No LoadBalancers in response for ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        if (len(loadBalancers) != 1):
          raise AWSStackResourceException("Unexpected number of LoadBalancers from ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        loadBalancer = loadBalancers[0]

        dnsName = loadBalancer.get('DNSName')
        if (not dnsName):
          raise AWSStackResourceException("Empty DNSName attribute for ELB with ARN: %s" % elbIId)
        #endIf
        
        if (TR.isLoggable(Level.FINER)):
          TR.finer(methodName,"Getting IP address for ELB: %s with DNS name: %s" % (elbName,dnsName))
        #endIf
            
        ipAddress = self._getIPAddress(dnsName)
        if (not ipAddress):
          raise AWSStackResourceException("No public IP address found for ELB: %s" % elbName)
        #endIf
        break
      #endIf
    #endFor
    
    return ipAddress
  #endDef
  
  
  def getLoadBalancerDNSName(self,stackIds,elbName=None):
    """
      Return the DNSName for the Elastic Load Balancer V2 with the given name as the value
      of its Name tag.
      
      The stackIds parameter holds the list of all the stacks in the CFN deployment.  
      It is assumed there is only 1 ELB in all of those stacks with the given name.
      (The DNSName of the first one found with the given name gets returned.)
      
      The boto3 API for ELBs is rather baroque.
      
      The tags are gotten using the describe_tags() method.  We need to look at the tags
      in order to find the ELB with Name tag value for the given name (elbName).  The 
      response from the describe_tags() call also includes the ARN (reource Id) for 
      the ELB with the set of tags.
      
      Once we have the ELB ARN, we can get its DNSName with a call to describe_load_balancers()
      followed by getting the IP address attribute from the load balancer instance.
      
    """
    
    if (not stackIds):
      raise MissingArgumentException("A list of stack IDs (stackIds) is required.")
    #endIf
    
    if (not elbName):
      raise MissingArgumentException("The ELB name must be provided.")
    #endIf

    dnsName = ""
    
    for stackId in stackIds:
      elbIId = self.getELBResourceIdForName(stackId, elbName=elbName)
      
      if (elbIId):
        response = self.elbv2Client.describe_load_balancers(LoadBalancerArns=[elbIId])
        if (not response):
          raise AWSStackResourceException("Empty response for ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        loadBalancers = response.get('LoadBalancers')
        if (not loadBalancers):
          raise AWSStackResourceException("No LoadBalancers in response for ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        if (len(loadBalancers) != 1):
          raise AWSStackResourceException("Unexpected number of LoadBalancers from ELBv2 Client describe_load_balancers() call for ELB with ARN: %s" % elbIId)
        #endIf
    
        loadBalancer = loadBalancers[0]
    
        dnsName = loadBalancer.get('DNSName')
        if (not dnsName):
          raise AWSStackResourceException("Empty DNSName attribute for ELB with ARN: %s" % elbIId)
        #endIf
        break
      #endIf
    #endFor
    
    return dnsName
  #endDef
  
  
  def _checkForParm(self,line,parameterNames):
    """
      Return a tuple (parmName,macroName) if the given line has a substitution macro using 
      a keyword (macroName) for one of the parameter names given in parameterNames  
      Otherwise, return None.  
      
      Returned tuple is of the form (parameter_name,macro_name)
      Helper method for createConfigFile()
    """
    result = (None,None)
    for parmName in parameterNames:
      macroName = TemplateKeywordMappings.get(parmName)
      if (not macroName):
        raise InvalidParameterException("The parameter name: %s was not found in TemplateKeywordMappings hash map." % parmName)
      #endIf
      macro = "${%s}" % macroName
      if (line.find(macro) >= 0):
        result = (parmName,macroName)
        break
      #endIf
    #endFor
    return result
  #endDef
  
  
  def _transformExcludedMgmtServices(self,excludedServices):
    """
      Return a list of strings that are the names of the services to be excluded.
      
      The incoming excludedServices parameter may be a list of strings or the string
      representation of a list using commas to delimit the items in the list.
      (The value of ExcludedMgmtServices in the AWS CF template is a CommaDelimitedList 
      which is just such a string.)
      
      The items in the incoming list are converted to all lowercase characters and trimmed.
      
      If the incoming value in excludedServices is the empty string, then an empty list
      is returned.
      
      NOTE: This method is used to support the exclusion of management services in the 
      ICP v2.1 config.yaml file.  It is not used for excluding management services in 
      versions of ICP 3.1.0 and later.
    """
    result = []
    if (excludedServices):
      if (type(excludedServices) != type([])):
        # assume excludedServices is a string
        excludedServices = [x.strip() for x in excludedServices.split(',')]
      #endIf
      
      excludedServices = [x.lower() for x in excludedServices]
      
      for x in excludedServices:
        if (x not in OptionalManagementServices_21):
          raise ICPInstallationException("Service: %s is not an optional management service.  It must be one of: %s" % (x,OptionalManagementServices_21))
        #endIf
      #endFor
      
      result = excludedServices
    #endIf
    return result
  #endDef


  def _configureMgmtServices(self,configParameters,optionalServices,excludedServices):
    """
      Walk through the optionalServices list and set all that are not in the excludedServivces
      list to "enabled" in the configParameters dictionary.
      
      The incoming excludedServices parameter is assumed to have been "regularized" by the 
      _transformExcludeMgmtServices() method prior to the invocation of this method.
      
      The names in the optionalServices list are mapped to names that match the corresponding 
      parameter names used in the configParameters dictionary.
             
      NOTE: This method is used to support the inclusion/exclusion of management services in the 
      config.yaml file for ICP v3.1.0 or later.
    """
    methodName = "_configureMgmtServices"
    
    for service in optionalServices:
      serviceParameterName = ServiceNameParameterMap.get(service)
      if (not serviceParameterName):
        raise ICPInstallationException("Missing service name parameter in ServiceNameParameterMap for service: %s" % service)
      #endIf
        
      if (excludedServices and service in excludedServices):
        # Set the service parameter to be disabled in the configParmaeters
        configParameters[serviceParameterName] = 'disabled'
      else:
        configParameters[serviceParameterName] = 'enabled'
      #endIf
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Management Service: %s: %s" % (serviceParameterName,configParameters[serviceParameterName]))
      #endIf
    #endFor
  #endDef

  
  def createConfigFile(self, configFilePath, icpVersion):
    """
      Select the proper method to create the configuration file based on the 
      ICP version.  The differences in the format and content of the config.yaml
      from one version of ICP to the next are sufficient to warrant a specialized
      method for the creation of the configuration file.  This may settle out
      as the product matures.
      
    """
    
    if (icpVersion.startswith('2.1.')):
      self.createConfigFile_21(configFilePath)
    elif (icpVersion.startswith('3.1.')):
      self.createConfigFile_31(configFilePath)
    else:
      raise ICPInstallationException("Unexpected version of ICP: %s" % icpVersion)
    #endIf
    
    if (self.MasterNodeCount > 1):
      self.configureEtcHosts()
    #endIf
    
  #endDef
  
  
  def createConfigFile_21(self, configFilePath):
    """
      Create an ICP v2.1.* config.yaml file.
      
      Using the configuration file template, fill in all the variable strings in the template
      using the parameters provided to the instance.
      
      Comment lines in the template file are written immediately to the configuration file.
      
      NOTE: It is assumed that a line in the configuration template file has at most
      one parameter defined in it.  A parameter is delimited by ${} with the parameter
      name in the {}.
      
      NOTE: It is assumed a given parameter only appears once in the configuration file
      template. Once a parameter has been found and replaced in a given line in the template
      file, there is no need to check other lines for that same parameter.
    """
    methodName = "createConfigFile_21"
    
    # Make a copy of configParameterNames that can be modified in this method.
    parameterNames = list(self.configParameterNames)
    
    try:
      with open(self.configTemplatePath,'r') as templateFile, open(configFilePath,'w') as configFile:
        for line in templateFile:
          # Need to strip the at least the new line characters(s)
          line = line.rstrip()
          if (line.startswith('#')):
            configFile.write("%s\n" % line)
          else:
            parmName,macroName = self._checkForParm(line,parameterNames)
            if (not parmName):
              configFile.write("%s\n" % line)
            else:
              parmValue = self.configParameters[parmName]
              # special processing for excluded mgmt services value
              if (parmName == 'ExcludedMgmtServices'):
                parmValue = self._transformExcludedMgmtServices(parmValue)
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
              # No need to keep checking for parmName, once it has been found in a line in the template.
              parameterNames.remove(parmName)
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating configuration file: %s from template file: %s" % (configFilePath,self.tempatePath), e)
      raise
    #endTry    
  #endDef
  
  
  def createConfigFile_31(self, configFilePath):
    """
      Create an ICP v3.1.* config.yaml file.
      
      Using the configuration file template, fill in all the variable strings in the template
      using the parameters provided to the instance.
      
      Comment lines in the template file are written immediately to the configuration file.
      
      NOTE: It is assumed that a line in the configuration template file has at most
      one parameter defined in it.  A parameter is delimited by ${} with the parameter
      name in the {}.
      
      NOTE: It is assumed a given parameter only appears once in the configuration file
      template. Once a parameter has been found and replaced in a given line in the template
      file, there is no need to check other lines for that same parameter.
    """
    methodName = "createConfigFile_31"
    
    # First, the excluded services needs to be "regularized" to a python list of management services
    excludedServices = self._transformExcludedMgmtServices(self.ExcludedMgmtServices)
    # Then, set up the optional management service parameter value to enabled or disabled
    self._configureMgmtServices(self.configParameters,OptionalManagementServices,excludedServices)

    # Make a copy of configParameterNames that can be modified in this method.
    parameterNames = list(self.configParameterNames)
    
    try:
      with open(self.configTemplatePath,'r') as templateFile, open(configFilePath,'w') as configFile:
        for line in templateFile:
          # Need to strip at least the newline character(s)
          line = line.rstrip()
          if (line.startswith('#')):
            configFile.write("%s\n" % line)
          else:
            parmName,macroName = self._checkForParm(line,parameterNames)
            if (not parmName):
              configFile.write("%s\n" % line)
            else:
              parmValue = self.configParameters[parmName]
              macro = "${%s}" % macroName
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"LINE: %s\n\tReplacing: %s with: %s" % (line,macro,parmValue))
              #endIf
              newline = line.replace(macro,"%s" % parmValue)
              if (TR.isLoggable(Level.FINEST)):
                TR.finest(methodName,"NEW LINE: %s" % newline)
              #endIf
              configFile.write("%s\n" % newline)
              # No need to keep checking for parmName, once it has been found in a line in the template.
              parameterNames.remove(parmName)
            #endIf
          #endIf
        #endFor
      #endWith 
    except IOError as e:
      TR.error(methodName,"IOError creating configuration file: %s from template file: %s" % (configFilePath,self.tempatePath), e)
      raise
    #endTry
  #endDef


  def runAnsiblePlaybook(self, playbook=None, extraVars=None, inventory="/etc/ansible/hosts"):
    """
      Invoke a shell script to run an Ansible playbook with the given arguments.
      
      extraVars can be a list of argument values or a single string with space separated argument values.
        list example: [ "target_nodes=icp", "host_addres=9.876.54.32", "host_name=mycluster.example.com" ]
        string example: "target_nodes=icp host_addres=9.876.54.32 host_name=mycluster.example.com" 
      
    """
    methodName = "runAnsiblePlaybook"
    
    if (not playbook):
      raise MissingArgumentException("The playbook path must be provided.")
    #endIf
    
    try:
      if (extraVars):
        if (type(extraVars) != type([])):
          # Assume extraVars is a string with space separated values
          extraVars = extraVars.split()
        #endIf
        
        cmd = ["ansible-playbook", playbook, "--inventory", inventory]
        for var in extraVars:
          cmd.extend(["-e", "%s" % var])
        #endFor
        TR.info(methodName, "Executing: cmd: %s" % cmd)
        retcode = call(cmd)
      else:
        TR.info(methodName, 'Executing: ansible-playbook %s, --inventory %s.' % (playbook,inventory))
        retcode = call(["ansible-playbook", playbook, "--inventory", inventory ] )
      #endIf        
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


  def configureEtcHosts(self):
    """
      Add an entry to /etc/hosts for all cluster nodes, mapping cluster name to to the master ELB public IP address.
      
      The boot node needs an entry in its /etc/hosts that maps a master node ELB address to the cluster name.
      
      NOTE: The cluster CN is the cluster FQDN.
    """
    
    extraVars = ["target_nodes=all", "host_address=%s" % self.masterELBAddress, "host_name=%s" % self.ClusterDNSName]
    self.runAnsiblePlaybook(playbook=self.etcHostsPlaybookPath,extraVars=extraVars)
  #endDef
  
#endClass