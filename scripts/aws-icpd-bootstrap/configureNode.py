#! /usr/bin/python

import sys, subprocess, os
import boto3
from yapl.utilities.Trace import Trace, Level
from yapl.icp.AWSConfigureEFS import ConfigureEFS
TR = Trace(__name__)
class ConfigureNode(object):
  def __init__(self):
    """
    Constructor

    NOTE: Some instance variable initialization happens in self._init() which is 
    invoked early in main() at some point after _getStackParameters().
    """
    object.__init__(self)
    self.home = os.path.expanduser("~")
    self.logsHome = os.path.join(self.home,"logs")
    self.sshHome = os.path.join(self.home,".ssh")
  #endDef 


  def updateSSMparameter(self,status):
    methodName = "updateSSMparameter"
    parameterKey = "/%s/configureNodeStatus" % self.stackName
    TR.info(methodName,"Setting %s to %s" % (parameterKey,status))
    self.ssm.put_parameter(Name=parameterKey,
                               Description="Root public key and private IP address for ICP boot node to be added to autorized_keys of all ICP cluster nodes.",
                               Value=status,
                               Type='String',
                               Overwrite=True)
    TR.info(methodName,"%s key value published."%parameterKey)
  #endDef
  #       
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
              self.bootStackId = fields[1].lstrip('\"')
              self.bootStackId = self.bootStackId.rstrip('\"')
            elif(fields[0]=="ROLE"):
              self.role = fields[1]    
        #endFor
        TR.info(methodName,"StackName: %s, BootStackId: %s, region: %s, role: %s"%(self.stackName,self.bootStackId,self.region,self.role))
      except Exception, e:
       TR.error(methodName,"Exception: %s" % e, e)    
  #endDef     

  def configureEFS(self):
    """
        Configure an EFS volume and configure all worker nodes to be able to use 
        the EFS storage provisioner.
      """
    methodName = "configureEFS"
      
    TR.info(methodName,"STARTED configuration of EFS on  %s"%(self.new_node))
      
    # Configure EFS storage on all of the worker nodes.
    playbookPath = os.path.join(self.home,"playbooks","configure-efs-mount.yaml")
    varTemplatePath = os.path.join(self.home,"playbooks","efs-var-template.yaml")
    manifestTemplatePath = os.path.join(self.home,"config","efs","manifest-template.yaml")
    rbacTemplatePath = os.path.join(self.home,"config","efs","rbac-template.yaml")
    serviceAccountPath = os.path.join(self.home,"config","efs","service-account.yaml")
    configEFS = ConfigureEFS(region=self.region,
                              stackId=self.bootStackId,
                              playbookPath=playbookPath,
                              varTemplatePath=varTemplatePath,
                              manifestTemplatePath=manifestTemplatePath,
                              rbacTemplatePath=rbacTemplatePath,
                              serviceAccountPath=serviceAccountPath)
 
    varFilePath = os.path.join(self.home,"efs-config-vars.yaml")

    TR.info(methodName,"Run ansible playbook to configure EFS")
    configEFS.runAnsiblePlaybook(playbook=playbookPath, extraVars=varFilePath,inventory=self.hostFile)
      
  #endDef

  def sshKeyScan(self):
    """
      Do an SSH keyscan to pick up the ecdsa/rsa fingerprint for each host in the cluster. 
      
      The boot node needs all the ecdsa/rsa fingerprints from all cluster nodes and itself.
    """
    methodName = "sshKeyScan"
    
    knownHostsPath = os.path.join(self.sshHome, "known_hosts")
#    keyscanStdErr = os.path.join(os.path.expanduser("~"),"logs","keyscan.log")
    
    try:
      with open(knownHostsPath,"a+") as knownHostsFile:
        TR.info(methodName,"STARTED ssh-keyscan for hosts in ssh-keyscan-hosts file: %s." % knownHostsPath)
        retcode = subprocess.call(["ssh-keyscan", "-4", "-t", "rsa", self.new_node ], stdout=knownHostsFile )
        if (retcode != 0):
          raise Exception("Error calling ssh-keyscan. Return code: %s" % retcode)
        else:
          TR.info(methodName,"COMPLETED SSH keyscan.")
        #endIf
      #endWith
    except Exception as e:
      TR.error(methodName,"Exception: %s" % e, e) 
    #endTry
    
  #endDef

  def main(self,argv):
    methodName = "main"
    try:
      trace = "*=all"
      logFile = "/root/logs/configureNode.log"
      if (logFile):
        TR.appendTraceLog(logFile)   
      if (trace):
        TR.info(methodName,"NINIT0102I Tracing with specification: '%s' to log file: '%s'" % (trace,logFile))
      #endIf 
      self.readStackProps()
      boto3.setup_default_session(region_name=self.region)
      self.ssm = boto3.client('ssm', region_name=self.region)
      self.updateSSMparameter("True")
      nodeType = argv[3]
      version = argv[2]
      self.new_node = argv[1]
      TR.info(methodName,"node value %s, version %s, nodeType %s" %(self.new_node,version,nodeType))
      self.hostFile = "/root/hosts_"+nodeType
      with open(self.hostFile, "a+") as updateHostFile:
        updateHostFile.write("[%s]\n" %nodeType)
        updateHostFile.write("%s\n" % self.new_node)
        updateHostFile.write("\n")  
      #endwith  
      ICPDIR = "/opt/icp/"+version+"/cluster"
      logFilePath = "/root/logs/add_node"+self.new_node+".log"
      self.sshKeyScan()
      with open(logFilePath,"a+") as icpdInstallLogFile:
      
        os.chdir(ICPDIR)  
      #docker run -e LICENSE=accept --net=host -v "$(pwd)":/installer/cluster ibmcom/icp-inception-amd64:3.1.2-ee worker -l $1
      #docker run -e LICENSE=accept --net=host -v /opt/icp/3.1.2/cluster :/installer/cluster ibmcom/icp-inception-amd64:3.1.2-ee worker -l 10.10.10.90
        docker_cmd = "docker run -e LICENSE=accept --net=host -v "+ICPDIR+":/installer/cluster ibmcom/icp-inception-amd64:"+version+"-ee "+nodeType+"  -l "+self.new_node
        retcode = subprocess.call(docker_cmd, shell=True, stdout=icpdInstallLogFile)
        if (retcode != 0):
            raise Exception("Error calling docker run to add node to ICP cluster. Return code: %s" % retcode)
        else:
            TR.info(methodName,"COMPLETED docker run to add node to ICP cluster.")

      #endwith
      if(nodeType=='worker'):
        TR.info(methodName,"Initate Configuring EFS")
        self.configureEFS()
        TR.info(methodName,"Configuring EFS Completed")
      #endIf  
      TR.info(methodName,"delete %s" %self.hostFile)
      os.remove(self.hostFile)
      self.updateSSMparameter("False")
    except Exception as e:
      TR.error(methodName,"Exception with message %s" %e.message)
      TR.info(methodName,"delete %s" %self.hostFile)
      os.remove(self.hostFile)
      self.updateSSMparameter("False")
  #endDef


if __name__ == "__main__":
  mainInstance = ConfigureNode()
  mainInstance.main(sys.argv)
#endIf