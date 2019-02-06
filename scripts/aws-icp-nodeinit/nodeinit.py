#!/usr/bin/python

"""
Created on 24 JUN 2018

@author: Peter Van Sickel pvs@us.ibm.com

Description:
  Node initialization script for ICP AWS Quickstart.  
  The ICP cluster nodes don't do much, but they do need to do a bit of work
  to get the cell bootstrapped.  The boot node does most of the heavy lifting.
  The boot node is not a member of the cluster.

History:
  24 JUN 2018 - pvs - Initial creation.

"""

import sys, os.path
from subprocess import call
import boto3
from botocore.exceptions import ClientError
import socket
import shutil
import time
import docker
import requests
import yaml
from yapl.utilities.Trace import Trace, Level
import yapl.utilities.Utilities as Utilities
from yapl.exceptions.Exceptions import ExitException
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.ICPExceptions import ICPInstallationException
from yapl.exceptions.AWSExceptions import AWSStackResourceException

GetParameterSleepTime = 60 # seconds
GetParameterMaxTryCount = 100
HelpFile = "nodeinit.txt"

TR = Trace(__name__)

"""
  The StackParameters are imported from the CloudFormation stack in the _init() 
  method below.
"""
StackParameters = {}
StackParameterNames = []

class EFSVolume:
  """
    Simple class to manage an EFS volume.
  """
  
  def __init__(self,efsServer,mountPoint):
    """
      Constructor
    """
    self.efsServer = efsServer
    self.mountPoint = mountPoint
  #endDef
  
#endClass


class NodeInit(object):
  """
    NodeInit class for AWS ICP Quickstart responsible for steps on the cluster nodes
    that are part of the IBM Cloud Private cluster installation/deployment on AWS.
  """

  ArgsSignature = {
                    '--help':       'string',
                    '--region':     'string',
                    '--stack-name': 'string',
                    '--stackid':    'string',
                    '--role':       'string',
                    '--logfile':    'string',
                    '--loglevel':   'string',
                    '--trace':      'string'
                   }


  def __init__(self):
    """
      Constructor
      
      NOTE: Some instance variable initialization happens in self._init() which is 
      invoked early in main() at some point after _getStackParameters().
    """
    object.__init__(self)

    self.home = os.path.expanduser("~")
    self.logsHome = os.path.join(self.home,"logs")
    self.sshHome = "%s/.ssh" % self.home
    self.fqdn = socket.getfqdn()
    self.rc = 0
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


  def _init(self, stackId):
    """
      Additional initialization of the NodeInit instance based on stack parameters.
      
      Invoke getStackParameters() gets all the CloudFormation stack parameters imported
      into the StackParmaters dictionary to make them available for use with the NodeInit 
      instance as instance variables via __getattr__().
    """
    methodName = "_init"
    global StackParameters, StackParameterNames

    # Use belt and suspenders to nail down the region.
    boto3.setup_default_session(region_name=self.region)
    self.ssm = boto3.client('ssm', region_name=self.region)
    self.s3  = boto3.client('s3', region_name=self.region)
    self.cfnClient = boto3.client('cloudformation', region_name=self.region)
    self.cfnResource = boto3.resource('cloudformation')    
    
    StackParameters = self._getStackParameters(stackId)
    StackParameterNames = StackParameters.keys()
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"StackParameterNames: %s" % StackParameterNames)
    #endIf
    
    # On the cluster nodes the default timeout is sufficient.
    self.dockerClient = docker.from_env()
            
  #endDef


  def _getStackParameters(self, stackId):
    """
      Return a dictionary with stack parameter name-value pairs for
      stack parameters relevant to the ICP Configuration from the  
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
  
  
  

  def _getArg(self,synonyms,args,default=None):
    """
      Return the value from the args dictionary that may be specified with any of the
      argument names in the list of synonyms.

      The synonyms argument may be a Jython list of strings or it may be a string representation
      of a list of names with a comma or space separating each name.

      The args is a dictionary with the keyword value pairs that are the arguments
      that may have one of the names in the synonyms list.

      If the args dictionary does not include the option that may be named by any
      of the given synonyms then the given default value is returned.

      NOTE: This method has to be careful to make explicit checks for value being None
      rather than something that is just logically false.  If value gets assigned 0 from
      the get on the args (command line args) dictionary, that appears as false in a
      condition expression.  However 0 may be a legitimate value for an input parameter
      in the args dictionary.  We need to break out of the loop that is checking synonyms
      as well as avoid assigning the default value if 0 is the value provided in the
      args dictionary.
    """
    value = None
    if (type(synonyms) != type([])):
      synonyms = Utilities.splitString(synonyms)
    #endIf

    for name in synonyms:
      value = args.get(name)
      if (value != None):
        break
      #endIf
    #endFor

    if (value == None and default != None):
      value = default
    #endIf

    return value
  #endDef


  def _usage(self):
    """
      Emit usage info to stdout.
      The _usage() method is invoked by the --help option.
    """
    methodName = '_usage'
    if (os.path.exists(HelpFile)):
      Utilities.showFile(HelpFile)
    else:
      TR.info(methodName,"There is no usage information for '%s'" % __name__)
    #endIf
  #endDef


  def _configureTraceAndLogging(self,traceArgs):
    """
      Return a tuple with the trace spec and logFile if trace is set based on given traceArgs.

      traceArgs is a dictionary with the trace configuration specified.
         loglevel|trace <tracespec>
         logfile|logFile <pathname>

      If trace is specified in the trace arguments then set up the trace.
      If a log file is specified, then set up the log file as well.
      If trace is specified and no log file is specified, then the log file is
      set to "trace.log" in the current working directory.
    """
    logFile = self._getArg(['logFile','logfile'], traceArgs)
    if (logFile):
      TR.appendTraceLog(logFile)
    #endIf

    trace = self._getArg(['trace', 'loglevel'],traceArgs)

    if (trace):
      if (not logFile):
        TR.appendTraceLog('trace.log')
      #endDef

      TR.configureTrace(trace)
    #endIf
    return (trace,logFile)
  #endDef  
        
  
  def addAuthorizedKey(self, authorizedKeyEntry):
    """
      Add the given authorizedKeyEntry to  the ~/.ssh/authorized_keys file.
      
      The authorizedKeyEntry includes the SSH private key and the user and IP address
      of the boot node, e.g., root@10.0.0.152
    """
    if (not os.path.exists(self.sshHome)):
      os.makedirs(self.sshHome)
    #endIf
    
    authKeysPath = os.path.join(self.sshHome, 'authorized_keys')
    
    with open(authKeysPath, "a+") as authorized_keys:
      authorized_keys.write("%s\n" % authorizedKeyEntry)
    #endWith
  #endDef
  
    
  def getStackOutput(self, stackId, outputKey):
    """
      For the given stack ID return the value of the given output key.
    """
    methodName = "getStackOutput"
    
    if (not stackId):
      raise MissingArgumentException("A stack resource ID must be provided.")
    #endIf
    
    if (not outputKey):
      raise MissingArgumentException("An output key must be provided.")
    #endIf
    
    response = self.cfnClient.describe_stacks(StackName=stackId)
    if (not response):
      raise AWSStackResourceException("Empty result for CloudFormation describe_stacks for stack: %s" % stackId)
    #endIf
    
    stacks = response.get('Stacks')
    if (len(stacks) != 1):
      raise AWSStackResourceException("Unexpected number of stacks: %d, from describe_stacks for stack: %s" %(len(stacks),stackId))
    #endIf
    
    myStack = stacks[0]
    outputs = myStack.get('Outputs')
    if (not outputs):
      raise AWSStackResourceException("Expecting output with key: %s, defined for stack: %s, but no outputs defined." % (outputKey,stackId))
    #endIf

    result = None    
    for output in outputs:
      key = output.get('OutputKey')
      if (key == outputKey):
        result = output.get('OutputValue')
        if (TR.isLoggable(Level.FINEST)):
          TR.finest(methodName,"Got output for key: %s with value: %s" %(outputKey,result))
        #endIf
        break
      #endIf
    #endFor
    
    # Output value types are strings or other simple types.
    # The actual value of an output will never be None. 
    if (result == None):
      TR.warning(methodName, "For stack: %s, no output found for key: %s" % (stackId,outputKey))
    #endIf
    
    return result
  #endDef
  
  
  def getSSMParameterValue(self,parameterKey,expectedValue=None):
    """
      Return the value from the given SSM parameter key.
      
      If an expectedValue is provided, then the wait loop for the SSM get_parameter()
      will continue until the expected value is seen or the try count is exceeded.
      
      NOTE: It is possible that the parameter is not  present in the SSM parameter
      cache when this method is invoked.   When that happens a ParameterNotFound 
      exception is raised by ssm.get_parameter().  Depending on the trace level,
      that  exception is reported in the log, but ignored.
    """
    methodName = "getSSMParameterValue"
    
    parameterValue = None

    tryCount = 1
    gotit = False
    while (not gotit and tryCount <= GetParameterMaxTryCount):
      if (expectedValue == None):
        TR.info(methodName,"Try: %d for getting parameter: %s" % (tryCount,parameterKey))
      else:
        TR.info(methodName,"Try: %d for getting parameter: %s with expected value: %s" % (tryCount,parameterKey,expectedValue))
      #endIf
      try: 
        response = self.ssm.get_parameter(Name=parameterKey)
        
        if (not response):
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName, "Failed to get a response for SSM get_parameter(): %s" % parameterKey)
          #endIf
        else:
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName,"Response: %s" % response)
          #endIf
        
          parameter = response.get('Parameter')
          if (not parameter):
            raise Exception("SSM get_parameter() response returned an empty Parameter.")
          #endIf
          
          parameterValue = parameter.get('Value')
          if (expectedValue == None):
            gotit = True
            break
          else:
            if (parameterValue == expectedValue):
              gotit = True
              break
            else:
              if (TR.isLoggable(Level.FINER)):
                TR.finer(methodName,"For key: %s ignoring value: %s waiting on value: %s" % (parameterKey,parameterValue,expectedValue))
              #endIf
            #endIf
          #endIf
        #endIf
      except ClientError as e:
        etext = "%s" % e
        if (etext.find('ParameterNotFound') >= 0):
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName,"Ignoring ParameterNotFound ClientError on ssm.get_parameter() invocation")
          #endIf
        else:
          raise ICPInstallationException("Unexpected ClientError on ssm.get_parameter() invocation: %s" % etext)
        #endIf
      #endTry
      time.sleep(GetParameterSleepTime)
      tryCount += 1
    #endWhile
    
    if (not gotit):
      if (expectedValue == None):
        raise ICPInstallationException("Failed to get parameter: %s " % parameterKey)
      else:
        raise ICPInstallationException("Failed to get parameter: %s with expected value: %s" % (parameterKey,expectedValue))
      #endIf
    #endIf
      
    return parameterValue
  #endDef
 
    
  def getBootNodePublicKey(self):
    """
      Return the authorized key entry for the ~/.ssh/authorized_keys file.
      The returned string is intended to include the RSA public key as well as the root user
      and IP address of the boot node.  The returned string can be added directly to the
      authorized_keys file.
      
      NOTE: It is possible that the a given cluster node may be checking for the authorized
      key from the boot node, before the boot node has published it in its parameter.  When
      that happens a ParameterNotFound exception is raised by ssm.get_parameter().  That 
      exception is reported in the log, but ignored.
    """
    methodName = "getBootNodePublicKey"
    
    authorizedKeyEntry = ""
    parameterKey = "/%s/boot-public-key" % self.stackName
    tryCount = 1
    response = None
    
    while not response and tryCount <= 100:
      time.sleep(GetParameterSleepTime)
      TR.info(methodName,"Try: %d for getting parameter: %s" % (tryCount,parameterKey))
      try: 
        response = self.ssm.get_parameter(Name=parameterKey)
      except ClientError as e:
        etext = "%s" % e
        if (etext.find('ParameterNotFound') >= 0):
          if (TR.isLoggable(Level.FINEST)):
            TR.finest(methodName,"Ignoring ParameterNotFound ClientError on ssm.get_parameter() invocation")
          #endIf
        else:
          raise ICPInstallationException("Unexpected ClientError on ssm.get_parameter() invocation: %s" % etext)
        #endIf
      #endTry
      tryCount += 1
    #endWhile
    
    if (response and TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Response: %s" % response)
    #endIf
    
    if (not response):
      TR.warning(methodName, "Failed to get a response for get_parameter: %s" % parameterKey)
    else:
      parameter = response.get('Parameter')
      if (not parameter):
        raise Exception("get_parameter response returned an empty Parameter.")
      #endIf
      authorizedKeyEntry = parameter.get('Value')
    #endIf
    
    return authorizedKeyEntry
  #endDef
 
 
  def getS3Object(self, bucket=None, s3Path=None, destPath=None):
    """
      Return destPath which is the local file path provided as the destination of the download.
      
      A pre-signed URL is created and used to download the object from the given S3 bucket
      with the given S3 key (s3Path) to the given local file system destination (destPath).
      
      The destination path is assumed to be a full path to the target destination for 
      the object. 
      
      If the directory of the destPath does not exist it is created.
      It is assumed the objects to be gotten are large binary objects.
      
      For details on how to download a large file with the requests package see:
      https://stackoverflow.com/questions/16694907/how-to-download-large-file-in-python-with-requests-py
    """
    methodName = "getS3Object"
    
    if (not bucket):
      raise MissingArgumentException("An S3 bucket name (bucket) must be provided.")
    #endIf
    
    if (not s3Path):
      raise MissingArgumentException("An S3 object key (s3Path) must be provided.")
    #endIf
    
    if (not destPath):
      raise MissingArgumentException("A file destination path (destPath) must be provided.")
    #endIf
    
    TR.info(methodName, "STARTED download of object: %s from bucket: %s, to: %s" % (s3Path,bucket,destPath))
    
    s3url = self.s3.generate_presigned_url(ClientMethod='get_object',Params={'Bucket': bucket, 'Key': s3Path})
    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"Getting S3 object with pre-signed URL: %s" % s3url)
    #endIf
    
    destDir = os.path.dirname(destPath)
    if (not os.path.exists(destDir)):
      os.makedirs(destDir)
      TR.info(methodName,"Created object destination directory: %s" % destDir)
    #endIf
    
    r = requests.get(s3url, stream=True)
    with open(destPath, 'wb') as destFile:
      shutil.copyfileobj(r.raw, destFile)
    #endWith

    TR.info(methodName, "COMPLETED download from bucket: %s, object: %s, to: %s" % (bucket,s3Path,destPath))
    
    return destPath
  #endDef
  
 
  def loadInstallMap(self, version=None, region=None):
    """
      Return a dictionary that holds all the installation image information needed to 
      retrieve the installation images from S3. 
      
      Which install images to use is driven by the ICP version.
      Which S3 bucket to use is driven by the AWS region of the deployment.
      
      The source of the information is icp-install-artifact-map.yaml packaged with the
      boostrap script package.  The yaml file holds the specifics regarding which bucket
      to use and the S3 path for the ICP and Docker images as well as the Docker image
      name and the inception commands to use for the installation.          
    """
    methodName = "loadInstallMap"
    
    if (not version):
      raise MissingArgumentException("The ICP version must be provided.")
    #endIf
    
    if (not region):
      raise MissingArgumentException("The AWS region must be provided.")
    #endIf
        
    installDocPath = os.path.join(self.home,"maps","icp-install-artifact-map.yaml")
    
    with open(installDocPath,'r') as installDocFile:
      installDoc = yaml.load(installDocFile)
    #endWith
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Install doc: %s" % installDoc)
    #endIf
    
    installMap = installDoc.get(version)
    if (not installMap):
      raise ICPInstallationException("No ICP or Docker installation images defined for ICP version: %s" % version)
    #endIf
    
    # The version is needed to get to the proper folder in the region bucket.
    installMap['version'] = version  
    installMap['s3bucket'] = self.ICPArchiveBucketName
    
    return installMap
    
  #endDef
  
  
  def getInstallImages(self, installMap):
    """
      Create a presigned URL and use it to download the Docker image from the S3
      bucket where the image is stored.  Each version of ICP is tested with a specific
      version of Docker, so it is best to use the Docker that is released with ICP.
      
      The cluster nodes only need to get the Docker image, where the boot node gets
      the ICP install image as well.
      
      Docker binary gets downloaded to: /root/docker/icp-install-docker.bin
        
      Using a pre-signed URL is needed when the deployer does not have access to the installation
      image bucket.
    """
    methodName = "getInstallImages"
    
    dockerLocalPath = "/root/docker/icp-install-docker.bin"
    dockerS3Path = "%s/%s" % (installMap['version'],installMap['docker-install-binary'])
    bucket = installMap['s3bucket']
    TR.info(methodName,"Getting object: %s from bucket: %s using a pre-signed URL." % (dockerS3Path,bucket))
    self.getS3Object(bucket=bucket, s3Path=dockerS3Path, destPath=dockerLocalPath)
  #endDef
  
  
  def _getDockerImage(self,rootName):
    """
      Return a docker image instance for the given rootName if it is available in 
      the local registry.
      
      Helper for installKubectl() and any other method that needs to get an image
      instance from the local docker registry.
    """
    result = None
    
    imageList = self.dockerClient.images.list()

    for image in imageList:
      imageNameTag = image.tags[0]
      if (imageNameTag.find(rootName) >= 0):
        result = image
        break
      #endIf
    #endFor
    return result
  #endDef
  
  
  def installKubectl(self):
    """
      Copy kubectl out of the kubernetes image to /usr/local/bin
      Convenient for troubleshooting.  
      
      If the kubernetes image is not available then this method is a no-op.
    """
    methodName = "installKubectl"
    
    TR.info(methodName,"STARTED install of kubectl to local host /usr/local/bin.")
    kubeImage = self._getDockerImage("kubernetes")
    if (not kubeImage):
      TR.info(methodName,"Kubernetes image is not available in the local docker registry. Kubectl can not be installed.")
    else:
      TR.info(methodName,"Kubernetes image is available in the local docker registry.  Proceeding with the installation of kubectl.")
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Kubernetes image tags: %s" % kubeImage.tags)
      #endIf
      kubeImageName = kubeImage.tags[0]
      self.dockerClient.containers.run(kubeImageName,
                                       network_mode='host',
                                       volumes={"/usr/local/bin": {'bind': '/data', 'mode': 'rw'}}, 
                                       command="cp /kubectl /data"
                                       )
    #endIf
    TR.info(methodName,"COMPLETED install of kubectl to local host /usr/local/bin.")
  #endDef
  
  
  def putSSMParameterValue(self,parameterKey,parameterValue,description=""):
    """
      Put the given parameterValue to the given parameterKey
      
      Wrapper for dealing with CloudFormation SSM parameters.
    """
    methodName = "putSSMParameterValue"
    
    TR.info(methodName,"Putting value: %s to SSM parameter: %s" % (parameterValue,parameterKey))
    self.ssm.put_parameter(Name=parameterKey,
                           Description=description,
                           Value=parameterValue,
                           Type='String',
                           Overwrite=True)
    TR.info(methodName,"Value: %s put to: %s." % (parameterValue,parameterKey))
    
  #endDef

  
  def publishReadiness(self, stackName, fqdn):
    """
      Put a parameter in /stackName/fqdn indicating readiness for ICP installation to proceed.
    """
    methodName = "publishReadiness"
    
    if (not stackName):
      raise MissingArgumentException("The stack name (stackName) must be provided and cannot be empty.")
    #endIf
    
    if (not fqdn):
      raise MissingArgumentException("The FQDN for this node must be provided and cannot be empty.")
    #endIf
    
    parameterKey = "/%s/%s" % (stackName,fqdn)
    
    TR.info(methodName,"Putting READY to SSM parameter: %s" % parameterKey)
    self.ssm.put_parameter(Name=parameterKey,
                           Description="Cluster node: %s is READY" % fqdn,
                           Value="READY",
                           Type='String',
                           Overwrite=True)
    TR.info(methodName,"Node: %s is READY has been published." % fqdn)

  #endDef
  
  
  def loadICPImages(self):
    """
      Load the IBM Cloud Private images from the installation tar archive.
      
      Loading the ICP installation images on each node prior to kicking off the 
      inception install is an expediency that speeds up the installation process 
      dramatically.
      
      The AWS CloudFormation template downlaods the ICP installation tar ball from
      an S3 bucket to /tmp/icp-install-archive.tgz of each cluster node.  It turns 
      out that download is very fast: typically 3 to 4 minutes.
    """
    methodName = "loadICPImages"
        
    TR.info(methodName,"STARTED docker load of ICP installation images.")
    
    retcode = call("tar -zxvf /tmp/icp-install-archive.tgz -O | docker load | tee /root/logs/load-icp-images.log", shell=True)
    if (retcode != 0):
      raise ICPInstallationException("Error calling: 'tar -zxvf /tmp/icp-install-archive.tgz -O | docker load' - Return code: %s" % retcode)
    #endIf
    
    TR.info(methodName,"COMPLETED Docker load of ICP installation images.")
    
  #endDef
  
  
  def mountEFSVolumes(self, volumes):
    """
      Mount the EFS storage volumes for the audit log and the Docker registry.
      
      volumes is either a singleton instance of EFSVolume or a list of instances
      of EFSVolume.  EFSVolume has everything needed to mount the volume on a
      given mount point.
      
      NOTE: It is assumed that nfs-utils (RHEL) or nfs-common (Ubuntu) has been
      installed on the nodes were EFS mounts are implemented.

      Depending on what EFS example you look at the options to the mount command vary.
      The options used in this method are from this AWS documentation:
      https://docs.aws.amazon.com/efs/latest/ug/wt1-test.html
      Step 3.3 has the mount command template and the options are:
      nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport
      
      We explicitly add the following default mount options:
      rw,suid,dev,exec,auto,nouser
    """
    methodName = "mountEFSVolumes"
    
    if (not volumes):
      raise MissingArgumentException("One or more EFS volumes must be provided.")
    #endIf
    
    if (type(volumes) != type([])):
      volumes = [volumes]
    #endIf

    # See method doc above for AWS source for mount options used in the loop body below.
    options = "rw,suid,dev,exec,auto,nouser,nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport"
    
    for volume in volumes:
      if (not os.path.exists(volume.mountPoint)):
        os.makedirs(volume.mountPoint)
        TR.info(methodName,"Created directory for EFS mount point: %s" % volume.mountPoint)
      elif (not os.path.isdir(volume.mountPoint)):
        raise Exception("EFS mount point path: %s exists but is not a directory." % volume.mountPoint)
      else:
        TR.info(methodName,"EFS mount point: %s already exists." % volume.mountPoint)
      #endIf
      retcode = call("mount -t nfs4 -o %s %s:/ %s" % (options,volume.efsServer,volume.mountPoint), shell=True)
      if (retcode != 0):
        raise Exception("Error return code: %s mounting to EFS server: %s with mount point: %s" % (retcode,volume.efsServer,volume.mountPoint))
      #endIf
      TR.info(methodName,"%s mounted on EFS server: %s:/ with options: %s" % (volume.mountPoint,volume.efsServer,options))
    #endFor
  #endDef
  
  
  def exportLogs(self, bucketName, stackName, logsDirectoryPath):
    """
      Export the deployment logs to the given S3 bucket for the given stack.
      
      Each log will be exported using a path with the stackName at the root and the 
      log file name as the next element of the path.
      
      NOTE: Prefer not to use trace in this method as the bootstrap log file has 
      already had the "END" message emitted to it.
    """
    methodName = "exportLogs"
    
    if (not os.path.exists(logsDirectoryPath)):
      if (TR.isLoggable(Level.FINE)):
        TR.fine(methodName, "Logs directory: %s does not exist." % logsDirectoryPath)
      #endIf
    else:
      logFileNames = os.listdir(logsDirectoryPath)
      if (not logFileNames):
        if (TR.isLoggable(Level.FINE)):
          TR.fine(methodName,"No log files in %s" % logsDirectoryPath)
        #endIf
      else:
        for fileName in logFileNames:
          s3Key = "%s/%s/%s/%s" %(stackName,self.role,self.fqdn,fileName)
          bodyPath = os.path.join(logsDirectoryPath,fileName)
          if (TR.isLoggable(Level.FINE)):
            TR.fine(methodName,"Exporting log: %s to S3: %s:%s" % (bodyPath,bucketName,s3Key))
          #endIf
          self.s3.put_object(Bucket=bucketName, Key=s3Key, Body=bodyPath)
        #endFor
      #endIf
    #endIf
  #endDef


  def main(self,argv):
    """
      Main does command line argument processing, sets up trace and then kicks off the methods to
      do the work.
    """
    methodName = "main"

    self.rc = 0
    try:
      ####### Start command line processing
      cmdLineArgs = Utilities.getInputArgs(self.ArgsSignature,argv[1:])

      # if trace is set from command line the trace variable holds the trace spec.
      trace, logFile = self._configureTraceAndLogging(cmdLineArgs)

      if (cmdLineArgs.get("help")):
        self._usage()
        raise ExitException("After emitting help, jump to the end of main.")
      #endIf

      beginTime = Utilities.currentTimeMillis()
      TR.info(methodName,"NINIT0101I BEGIN Node initialization AWS ICP Quickstart version @{VERSION}.")

      if (trace):
        TR.info(methodName,"NINIT0102I Tracing with specification: '%s' to log file: '%s'" % (trace,logFile))
      #endIf
      
      region = cmdLineArgs.get('region')
      if (not region):
        raise MissingArgumentException("The AWS region (--region) must be provided.")
      #endIf
      self.region = region

      # The stackId is the "nested" stackId  It is used to get input parameter values.
      stackId = cmdLineArgs.get('stackid')
      if (not stackId):
        raise MissingArgumentException("The stack ID (--stackid) must be provided.")
      #endIf

      self.stackId = stackId
      TR.info(methodName,"Stack ID: %s" % stackId)

      # NOTE: The stackName is the root stack name as that is the name used in 
      # the SSM parameter keys by the boot node stack and the nested stacks.
      # For communication purposes all stacks must use the same root stack name.
      stackName = cmdLineArgs.get('stack-name')
      if (not stackName):
        raise MissingArgumentException("The stack name (--stack-name) must be provided.")
      #endIf
      
      self.stackName = stackName
      TR.info(methodName,"Stack name: %s" % stackName)
      
      role = cmdLineArgs.get('role')
      if (not role):
        raise MissingArgumentException("The role of this node (--role) must be provided.")
      #endIf
      
      self.role = role
      TR.info(methodName,"Node role: %s" % role)
      
      # Additional initialization of the instance.
      self._init(stackId)

      # Get the appropriate docker image
      self.installMap = self.loadInstallMap(version=self.ICPVersion, region=self.region)
      self.getInstallImages(self.installMap)
          
      # The sleep() is a hack to give bootnode time to do get its act together.
      # PVS: I've run into rare cases where it appears that the the cluster nodes
      # pick up a bad public key.  I think it may be due to accidentally reusing
      # an ssm parameter.  Don't have time to troubleshoot, now.  I'm thinking 
      # if the boot node gets to it first, it will overwrite anything old that 
      # may be there.
      time.sleep(30)
      
      authorizedKeyEntry = self.getBootNodePublicKey()
      self.addAuthorizedKey(authorizedKeyEntry)

      # NOTE: All CFN outputs, parameters are strings even when the Type is Number.
      # Hence, the conversion of MasterNodeCount to an int.
      if (self.role == 'master' and int(self.MasterNodeCount) > 1):
        efsServer = self.EFSDNSName # An input to the master stack
        efsVolumes = [EFSVolume(efsServer,mountPoint) for mountPoint in ['/var/lib/registry','/var/lib/icp/audit','/var/log/audit']]
        self.mountEFSVolumes(efsVolumes)
      #endIf
            
      self.publishReadiness(self.stackName,self.fqdn)

      # Wait until boot node completes the Docker installation
      self.getSSMParameterValue("/%s/docker-installation" % self.stackName,expectedValue="COMPLETED")
      
      # NOTE: It looks like kubectl gets installed on the master node as part of the ICP install, at least as of ICP 3.1.0.
      
      self.publishReadiness(self.stackName,self.fqdn)
          

    except ExitException:
      pass # ExitException is used as a "goto" end of program after emitting help info

    except Exception, e:
      TR.error(methodName,"Exception: %s" % e, e)
      self.rc = 1
    finally:
      
      try:
        # Copy the deployment logs in logsHome to the S3 bucket for logs.
        self.exportLogs(self.ICPDeploymentLogsBucketName,self.stackName,self.logsHome)
      except Exception, e:
        TR.error(methodName,"Exception: %s" % e, e)
        self.rc = 1
      #endTry

      endTime = Utilities.currentTimeMillis()
      elapsedTime = (endTime - beginTime)/1000
      etm, ets = divmod(elapsedTime,60)
      eth, etm = divmod(etm,60) 
      
      if (self.rc == 0):
        TR.info(methodName,"NINIT0103I END Node initialization AWS ICP Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
      else:
        TR.info(methodName,"NINIT0104I FAILED END Node initialization AWS ICP Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
      #endIf
      
    #endTry

    if (TR.traceFile):
      TR.closeTraceLog()
    #endIf

    sys.exit(self.rc)
  #endDef

#endClass

if __name__ == '__main__':
  mainInstance = NodeInit()
  mainInstance.main(sys.argv)
#endIf
