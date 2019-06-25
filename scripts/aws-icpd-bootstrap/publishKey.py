#!/usr/bin/python


import sys, os.path
from subprocess import call
import boto3
from botocore.exceptions import ClientError
from yapl.utilities.Trace import Trace, Level
import socket
import shutil
import time
import docker
import requests
import yaml

TR = Trace(__name__)

class PublishKey(object):
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

    def __init(self):    
        boto3.setup_default_session(region_name=self.region)
        self.ssm = boto3.client('ssm', region_name=self.region)
    #endDef


    def publishSSHPublicKey(self, stackName, authorizedKeyEntry):
        """
        Publish the boot node SSH public key string to an SSM parameter with name <StackName>/boot-public-key
        """
        methodName = "publishSSHPublicKey"

        parameterKey = "/%s/boot-public-key" % stackName

        TR.info(methodName,"Putting SSH public key to SSM parameter: %s" % parameterKey)
        self.ssm.put_parameter(Name=parameterKey,
                               Description="Root public key and private IP address for ICP boot node to be added to autorized_keys of all ICP cluster nodes.",
                               Value=authorizedKeyEntry,
                               Type='String',
                               Overwrite=True)
        TR.info(methodName,"Public key published.")

    def readStackProps(self):
      try:
        methodName = "readStackProps"  
        stackPropsPath = os.path.join(self.home,"mystack.props")
        file = open(stackPropsPath)
        file.readline
        for line in file:
            fields = line.strip().split("=")
            if(fields[0]=="REGION"):
              self.region= fields[1]
            elif(fields[0]=="STACK_NAME"):
              self.stackName = fields[1]
            elif(fields[0]=="STACK_ID"):
              self.bootStackId = fields[1]
            elif(fields[0]=="ROLE"):
              self.role = fields[1]    
        #endFor
        TR.info(methodName,"StackName: %s, BootStackId: %s, region: %s, role: %s"%(self.stackName,self.bootStackId,self.region,self.role))
      except Exception, e:
       TR.error(methodName,"Exception: %s" % e, e)    
    #endDef     
    
    def readSSHKey(self):
      try:
        methodName = "readSSHKey"    
        sshPath = os.path.join(self.home,".ssh/id_rsa.pub")
        file = open(sshPath)
        self.authorizedKeyEntry= file.readline()
      except Exception, e:
        TR.error(methodName,"Exception: %s" % e, e)
    #endDef

    def main(self,argv):
     try:
        methodName = "main"
        trace = "*=all"
        logFile = "/root/logs/publishKey.log"
        if (logFile):
          TR.appendTraceLog(logFile)   
        if (trace):
          TR.info(methodName,"NINIT0102I Tracing with specification: '%s' to log file: '%s'" % (trace,logFile))
        #endIf 
        self.readStackProps()
        self.readSSHKey()
        self.__init()
        self.publishSSHPublicKey(self.stackName,self.authorizedKeyEntry)
     except Exception, e:
         TR.error(methodName,"Exception: %s" % e, e)

         sys.exit(self.rc)
    #endDef

#endClass

if __name__ == '__main__':
 mainInstance = PublishKey()
 mainInstance.main(sys.argv)
#endIf