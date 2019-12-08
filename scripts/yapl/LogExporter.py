
import os
from yapl.S3Helper import S3Helper
from yapl.Trace import Trace,Level
from yapl.Exceptions import MissingArgumentException

TR = Trace(__name__)


class LogExporter(object):
  """
    Helper for exporting log files to S3.
  """

  def __init__(self,region=None, bucket=None, keyPrefix='logs',  fqdn=None):
    """
      Constructor
      
      region - the AWS region name
      bucket - the S3 bucket name.  The bucket gets created if it does not exist.
      keyPrefix - the S3 key prefix to be used for each log export to S3, 
        e.g., logs/<stackname> where <stackname> is the name of the CloudFormation
              stack associated with the root template for a given deployment.
              The root stack name is unique.
              Using logs as the beginning of the prefix keeps all logs in a 
              separate "folder" of the bucket.
      fqdn - fully qualified domain name of the node exporting the logs
             The FQDN provides uniqueness as there may be more than one node 
             with a given role.
    """
    object.__init__(self)
    
    if (not region):
      raise MissingArgumentException("The AWS region name must be provided.")
    #endIf
    self.region = region
    
    if (not bucket):
      raise MissingArgumentException("The S3 bucket name for the exported logs must be provided.")
    #endIf
    self.bucket = bucket
    
    self.keyPrefix = keyPrefix
    
    if (not fqdn):
      raise MissingArgumentException("The FQDN of the node exporting the logs must be provided.")
    #endIf
    self.fqdn = fqdn
    
    self.s3Helper = S3Helper(region=region)
    
    if (not self.s3Helper.bucketExists(bucket)):
      self.s3Helper.createBucket(bucket,region=region)
    #endIf

  #endDef
  
  
  def exportLogs(self, logsDirectoryPath):
    """
      Export the deployment logs to the S3 bucket of this LogExporter.
      
      Each log will be exported using a path with the keyPrefix at the root 
      followed by the role and FQDN and ending with the log file name as the 
      last element of the S3 object key.
      
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
          bodyPath = os.path.join(logsDirectoryPath,fileName)
          if (os.path.isfile(bodyPath)):
            s3Key = "%s/%s/%s" % (self.keyPrefix,self.fqdn,fileName)
            
            if (TR.isLoggable(Level.FINE)):
              TR.fine(methodName,"Exporting log: %s to S3: %s:%s" % (bodyPath,self.bucket,s3Key))
            #endIf
            with open(bodyPath, 'r') as bodyFile:
              self.s3Helper.put_object(Bucket=self.bucket,Key=s3Key,Body=bodyFile)
            #endWith
          #endIf
        #endFor
      #endIf
    #endIf
  #endDef
  
#endClass