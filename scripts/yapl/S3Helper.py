
import os
import boto3
from botocore.exceptions import ClientError

from yapl.Trace import Trace,Level
from yapl.Exceptions import MissingArgumentException
from yapl.Exceptions import InvalidArgumentException
from yapl.Exceptions import AccessDeniedException

TR = Trace(__name__)

S3ClientMethodRequiredArgs = {
    'download_file': ["Bucket", "Key", "Filename"]
  }
  


class S3Helper(object):
  """
    Various methods that ease the use of the boto3 Python library for working with S3.
  """
    
  def __init__(self, region=""):
    """
      region - AWS region name
      
    """
    object.__init__(self)
    
    self.s3Resource = boto3.resource('s3')
    self.region=region
    if (self.region):
      self.s3Client = boto3.client('s3', region_name=self.region)
    else:
      self.s3Client = boto3.client('s3')
    #endIf
    
  #endDef


  def _getRequiredArgs(self, method, **kwargs):
    """
      Return a list of required arguments for the given method 
    """
    requiredArgs = []
    argNames = S3ClientMethodRequiredArgs.get(method)
    if (argNames):
      for argName in argNames:
        argValue = kwargs.get(argName)
        if (argValue == None):
          raise MissingArgumentException("The S3 client method: '%s' requires a '%s' argument." % (method,argName))
        #endIf
        requiredArgs.append(argValue)
      #endFor
    #endIF
    
    return requiredArgs
    
  #endDef
  
  
  def bucketExists(self, bucketName):
    """
      Return True if the bucket exists and access is permitted.
      If bucket does not exist return False
      If bucket exists but access is forbidden, raise an exception.
      
      Picked this up from:
      https://stackoverflow.com/questions/26871884/how-can-i-easily-determine-if-a-boto-3-s3-bucket-resource-exists
    """
    methodName = "bucketExists"
    
    result = False
    try:
      self.s3Client.head_bucket(Bucket=bucketName)
      
      result = True
    except ClientError as e:
      # If a client error is thrown, then check that it was a 404 error.
      error_code = e.response['Error']['Code']
      if (TR.isLoggable(Level.FINEST)):
        TR.finest(methodName,"Error code: %s" % error_code)
      #endIf
      error_code = int(error_code)
      if (error_code == 404):
        result = False
      else:
        if (error_code == 403):
          raise AccessDeniedException("Access denied to S3 bucket named: %s" % bucketName)
        else: 
          raise e
        #endIf
      #endIf
    #endTry
    
    return result
  #endDef
  
  
  def createBucket(self,bucketName,region=None):
    """
      Return an instance of S3 bucket either for a bucket that already
      exists or for a newly created bucket in the given region.
      
      NOTE: Region is required, either on the method call or to the S3Helper instance. 
      
    """
    methodName = "createBucket"
    
    bucket = None
    if (self.bucketExists(bucketName)):
      bucket = self.s3Resource.Bucket(bucketName)
    else:
      if (region):
        response = self.s3Client.create_bucket(Bucket=bucketName,
                                               CreateBucketConfiguration={'LocationConstraint': region})
      elif (self.region):
        response = self.s3Client.create_bucket(Bucket=bucketName,
                                               CreateBucketConfiguration={'LocationConstraint': self.region})
      else:
        raise MissingArgumentException("The AWS region name for the bucket must be provided either to the S3Helper instance or in the createBucket() arguments.")
      #endIf
        
      if (TR.isLoggable(Level.FINE)):
        TR.fine(methodName,"Bucket: %s created in region: %s" % (bucketName,response.get('Location')))
      #endIf 
      bucket = self.s3Resource.Bucket(bucketName) 
    #endIf
    
    return bucket
  #endDef
  
  
  def put_object(self,**kwargs):
    """
      Very thin wrapper around S3 client put_object()
    """
    self.s3Client.put_object(**kwargs)
  #endDef


  def download_file(self, **kwargs):
    """
      Support for downloading a file from an S3 bucket and to a place in the local file system.
      
      S3 download_file required arguments:
        Bucket   - S3 bucket name
        Key      - S3 object key
        Filename - full path to the target file
      
      WARNING: (PVS 04 FEB 2019) 
        S3 client download_file() keyword arguments not supported (at this time)
        kwargs: ExtraArgs, Callback, Config.  See S3 client doc for download_file().
        
      Additional kwargs
        mode    - file system mode bits for the copied object
        
      NOTES: 
       1. The S3 client download_file() method only allows documented keyword arguments.
          It throws an exception if it finds extraneous keyword arguments.
       2. The Filename argument needs to include the file name.
          (The path can be absolute or relative to the current working directory.)
       3. The directory structure in the Filename argument must exist.
    """

    requiredArgs = self._getRequiredArgs('download_file',**kwargs)
    
    Filename = kwargs.get('Filename')
    dirName = os.path.dirname(Filename)
    if (not os.path.exists(dirName)):
      os.makedirs(dirName)
    #endIf
    
    # TBD: If needed by some use-case, add support for kwargs here
    
    self.s3Client.download_file(*requiredArgs)
    
    mode = kwargs.get('mode')
    if (mode):
      os.chmod(Filename,mode)
    #endIf
    
  #endDef
  
  
  def invokeCommands(self, cmdDocs, start, **kwargs):
    """
      Process command docs to invoke each command in sequence that is of kind s3.  

      Processing of cmdDocs stops as soon as a doc kind that is not s3 is encountered.

      All cmdDocs that are processed are marked with a status attribute with the value PROCESSED.
             
      cmdDocs - a list of 1 or more YAML documents loaded from yaml.load_all()
      by the caller.
      
      start - index where to start processing in the cmdDocs list.
      
      NOTE: The method for each command is responsible for pulling out the arguments for the 
      underlying S3 method.  The S3 client methods only accept the arguments in the signature.
      Extraneous keyword arguments cause an exception to be raised.
    """
    if (not cmdDocs):
      raise MissingArgumentException("A non-empty list of command documents (cmdDocs) must be provided.")
    #endIf

    for i in range(start,len(cmdDocs)):
      doc = cmdDocs[i]
      
      kind = doc.get('kind')
      if (not kind or kind != 's3'): break; # done
      
      command = doc.get('command')
      if (not command):
        raise InvalidArgumentException("A helm command document: %s, must have a command attribute." % doc)
      #endIf
      
      getattr(self,command)(**doc)
      
      doc['status'] = 'PROCESSED'
    #endFor
    
  #endDef
  
  
  
#endClass