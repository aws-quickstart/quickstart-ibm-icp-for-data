"""
Created on Oct 18, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

NOTES:
  This class is based on a shell script created by Sanjay Joshi.
  
  The constructor needs the IP address or host name of a master node in the ICP cluster.
  
  It is assumed that passwordless SSH has been configured for ssh/scp access to the
  members of the cluster from the boot node.  If the boot node is a master node then
  scp is not needed.
  
  TODO: Investigate the Python kubernetes support.  It looks pretty good, but I don't
  have time to play with it.  See: https://github.com/kubernetes-client/python
  
  TODO: The use of Paramiko and the SSHClient is on hold.  Seemed to run into problem
  with Paramiko compatibility with pycryptodome.  Didn't have time to investigate.
"""

import os
import shutil
from subprocess import call
from paramiko import SSHClient
from scp import SCPClient

from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.Exceptions import FileTransferException



TR = Trace(__name__)

class ConfigureKubectl(object):
  """
    Class that supports the configuration of kubectl with a permanent login context.
  """

  def __init__(self, user='root', clusterName=None, masterNode=None):
    """
      Constructor
    """
    
    object.__init__(self)
    
    self.user = user
    self.masterNode = masterNode
    self.home = os.path.expanduser('~')
    self.kube = os.path.join(self.home,".kube")
    
    if (not clusterName):
      raise MissingArgumentException("The cluster name must be provided.")
    #endIf
    
    self.clusterName = clusterName
    
    # The paramiko code doesn't work due to some sort of compatibility issue
    # with the pycryptodome module.
    #if (masterNode):
    #  self.configureSSH()
    #endIf
  #endDef


  def configureSSH(self):
    """
      Configure ssh for use by scp.
    """
    self.ssh = SSHClient()
    self.ssh.load_system_host_keys()
  #endDef
  
  
  def scpGetFile(self,fromPath=None, toPath=None):
    """
      Use scp to copy a file from the master node to the local file system
      
      This implementation uses a call out to bash to do the scp.
    """
    methodName = "scpGetFile"
    
    if (not self.masterNode):
      raise FileTransferException("The master host IP address or host name must be defined when the instance is created.")
    #endIf
    
    if (not fromPath):
      raise MissingArgumentException("The source path (fromPath) on the remote file system must be provided.")
    #endIf
    
    if (not toPath):
      raise MissingArgumentException("The destination path (toPath) on the local file system must be provided.")
    #endIf
      
    if (TR.isLoggable(Level.FINER)):
      TR.finer(methodName,"From host: %s, copying: %s to %s" % (self.masterNode,fromPath,toPath))
    #endIf
    
    retcode = call(["scp", "%s:%s" % (self.masterNode,fromPath), toPath])
    if (retcode != 0):
      raise Exception("Error calling scp. Return code: %s" % retcode)
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Copy completed")
    #endIf
  #endDef
  
  
  def scpGetFile_broken(self,fromPath=None, toPath=None):
    """
      Use scp to copy a file from the master node to the local file system
      
      WARNING: This never worked due to some issue with parameko and pycryptodome
               I didn't have time to sort it out.  I think parmeko needs to use
               Pycrypto, but Pycrypto is no longer maintained and has security holes.
    """
    methodName = "scpGetFile"
    
    if (not self.masterNode):
      raise FileTransferException("The master host IP address or host name must be defined when the instance is created.")
    #endIf
    
    if (not fromPath):
      raise MissingArgumentException("The source path (fromPath) on the remote file system must be provided.")
    #endIf
    
    if (not toPath):
      raise MissingArgumentException("The destination path (toPath) on the local file system must be provided.")
    #endIf
      
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Creating an ssh connection to: %s" % self.masterNode)
    #endIf
    self.ssh.connect(self.masterNode)
    
    scp = SCPClient(self.ssh.get_transport())
    
    if (TR.isLoggable(Level.FINER)):
      TR.finer(methodName,"From host: %s, copying: %s to %s" % (self.masterNode,fromPath,toPath))
    #endIf
    
    scp.get(fromPath,local_path=toPath)
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Copy completed")
    #endIf
  #endDef
  
  
  def configureKube(self):
    
    """
      Top level method for the configuration of kubectl with a permanent login context.
    """
    methodName = "configure"
    
    if (not os.path.exists(self.kube)):
      os.mkdir(self.kube)
    #endIf
    
    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"Copying the kubectl config file to %s" % self.kube)
    #endIf
      
    kubeConfigPath = os.path.join(self.kube,"config")
    
    if (not os.path.isfile("/var/lib/kubelet/kubectl-config")):
      # copy it from the master node
      self.scpGetFile(fromPath="/var/lib/kubelet/kubectl-config", toPath=kubeConfigPath)
    else:
      # running on a master node
      shutil.copyfile("/var/lib/kubelet/kubectl-config", kubeConfigPath)
    #endIf

    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"Copying the kubectl PKI certificate file to %s" % self.kube)
    #endIf
         
    kubeCertPath = os.path.join(self.kube,"kubecfg.crt")
    
    if (not os.path.isfile("/etc/cfc/conf/kubecfg.crt")):
      self.scpGetFile(fromPath="/etc/cfc/conf/kubecfg.crt", toPath=kubeCertPath)
    else:
      shutil.copyfile("/etc/cfc/conf/kubecfg.crt", kubeCertPath)
    #endIf

    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"Copying the kubectl PKI key file to %s" % self.kube)
    #endIf
             
    kubeKeyPath = os.path.join(self.kube,"kubecfg.key")
    
    if (not os.path.isfile("/etc/cfc/conf/kubecfg.key")):
      self.scpGetFile(fromPath="/etc/cfc/conf/kubecfg.key",toPath=kubeKeyPath)
    else:
      shutil.copyfile("/etc/cfc/conf/kubecfg.key", kubeKeyPath)
    #endIf

    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"Running the kubectl commands to configure the context.")
    #endIf

    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,'Invoking: kubectl config set-cluster cfc-cluster --server="https://%s:8001" --insecure-skip-tls-verify=true' % self.clusterName)
    #endIf
    
    retcode = call(["kubectl", "config", "set-cluster", "cfc-cluster", 
                    "--server=https://%s:8001" % self.clusterName,
                    "--insecure-skip-tls-verify=true" ])
    if (retcode != 0):
      raise Exception("Error calling kubectl config set-cluster command. Return code: %s" % retcode)
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Invoking: kubectl config set-context kubectl --cluster=cfc-cluster")
    #endIf
    
    retcode = call(["kubectl", "config", "set-context", "kubectl", "--cluster=cfc-cluster"])
    if (retcode != 0):
      raise Exception("Error calling kubectl config set-context command. Return code: %s" % retcode)
    #endIF
    
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Invoking: kubectl config set-credentials user --client-certificate=%s --client-key=%s" % (kubeCertPath,kubeKeyPath))
    #endIf
    
    retcode = call(["kubectl", "config", "set-credentials", "user", 
                    "--client-certificate=%s" % kubeCertPath, 
                    "--client-key=%s" % kubeKeyPath])
    if (retcode != 0):
      raise Exception("Error calling kubectl config set-credentials command. Return code: %s" % retcode)
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Invoking: kubectl config set-context kubectl --user=user")
    #endIf
    
    retcode = call(["kubectl", "config", "set-context", "kubectl", "--user=user"])
    if (retcode != 0):
      raise Exception("Error calling kubectl config set-context command. Return code: %s" % retcode)
    #endIf
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Invoking: kubectl config use-context kubectl")
    #endIf
    
    retcode = call(["kubectl", "config", "use-context", "kubectl"])
    if (retcode != 0):
      raise Exception("Error calling kubectl config use-context command. Return code: %s" % retcode)
    #endIf

  #endDef
#endClass        