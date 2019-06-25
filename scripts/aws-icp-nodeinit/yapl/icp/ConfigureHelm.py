
"""
Created on Oct 23, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

NOTES:
  The ICP Knowledge Center has instructions for setting up the Helm CLI
  in the section "Setting up the Helm CLI".  For ICP 3.1.0 the URL for 
  that section is: 
  https://www.ibm.com/support/knowledgecenter/SSBS6K_3.1.0/app_center/create_helm_cli.html
  
  This class emulates those instructions.
  
  It is assumed ICP is installed.  The boot node has the cert and key files used for the 
  Helm cert and key.
  
  We also had as a guide the setup-helm.sh script written by Sanjay Joshi.
  
"""

import requests
import stat
import os
from subprocess import check_output, CalledProcessError
import shutil
import tarfile

from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException


TR = Trace(__name__)


class ConfigureHelm(object):
  """
    Class to configure Helm command line for IBM Cloud Private
    
    The clusterDNSName is the fully qualified domain name used to identify the cluster.
    It is assumed that there is an entry in /etc/hosts that resolves the clusterDNSName.
    Or there is an entry in some DNS that resolves the clusterDNSName.
    
    The clusterDNSName is the FQDN used to access the ICP master node(s).
    
  """


  def __init__(self, **restArgs):
    """
      Constructor
      
      Required arguments:
        ClusterDNSName    - the DNS name used for the CN of the cluster cert and used to access the ICP admin console
        HelmKeyPath       - the path to the user key file, e.g., ~/.kube/kubecfg.key or <icp_home>/cluster/cfc-certs/helm/admin.key
        HelmCertPath      - the path to the user cert file, e.g., ~/.kube/kubecfg.cert or <icp_home>/cluster/cfc-certs/helm/admin.crt
        ClusterCertPath   - the path to the file that holds the CA cert.  The cluster CA cert is usually used for this.
    """
    object.__init__(self)
    
    self.ClusterDNSName = restArgs.get('ClusterDNSName')
    if (not self.ClusterDNSName):
      raise MissingArgumentException("The cluster DNS name to be used to access the ICP master must be provided.")
    #endIf

    self.HelmKeyPath = restArgs.get('HelmKeyPath')
    if (not self.HelmKeyPath):
      raise MissingArgumentException("The file path to the Helm user key must be provided.")
    #endIf
    
    self.HelmCertPath = restArgs.get('HelmCertPath')
    if (not self.HelmCertPath):
      raise MissingArgumentException("The file path to the Helm user certificate must be provided.")
    #endIf

    self.ClusterCertPath = restArgs.get('ClusterCertPath')
    if (not self.ClusterCertPath):
      raise MissingArgumentException("The file path to the cluster certificate must be provided.")
    #endIf
    
    HelmHome = restArgs.get('HelmHome')
    if (not HelmHome):
      HelmHome = os.path.join(os.path.expanduser('~'),".helm")
    #endIf
    self.HelmHome = HelmHome
    
    self.UserKeyPath = os.path.join(self.HelmHome,"key.pem")
    self.UserCertPath = os.path.join(self.HelmHome,"cert.pem")
    self.CACertPath = os.path.join(self.HelmHome,"ca.pem")
  #endDef
  
  
  def installHelm(self):
    """
      After the cluster is up and running, install Helm.
            
      ASSUMPTIONS:
        1. ICP is installed and running
        2. An entry in /etc/hosts exists to resolve the clusterDNSName to an IP address
        3. Verifying the SSL connection to the master is irrelevant.  The master may
           be using a self-signed certificate.        
    """
    methodName = 'installHelm'
     
    tgzPath = "/tmp/helm-linux-amd64.tar.gz"
    url = "https://%s:8443/api/cli/helm-linux-amd64.tar.gz" % self.ClusterDNSName
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Downloading Helm tgz file from: %s to: %s" % (url,tgzPath))
    #endIf
    r = requests.get(url, verify=False, stream=True)
    with open(tgzPath, 'wb') as tgzFile:
      shutil.copyfileobj(r.raw, tgzFile)
    #endWith
 
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Extracting the Helm tgz archive: %s" % tgzPath)
    #endIf
    helmTarFile = tarfile.open(name=tgzPath,mode='r')
    helmTarFile.extractall(path="/tmp")
    helmTarFile.close()
    
    helmSrcPath = "/tmp/linux-amd64/helm"
    helmDestPath = "/usr/local/bin/helm" 
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Moving helm executable from: %s to: %s" % (helmSrcPath,helmDestPath))
    #endIf
    
    shutil.move(helmSrcPath, helmDestPath)
    
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"Modifying helm executable mode bits to 755")
    #endIf
    os.chmod(helmDestPath, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
  
  #endDef
  

  def configureHelm(self):
    """
      Configure helm after helm executable has been installed.
      
      Helm is assumed to be installed and in the PATH.

      IMPORTANT: It is critical to set up HELM_HOME within the context of the Python process.
      The HELM_HOME setting done by the helm init command is either not visible in the context
      of the Python process or it is incorrect. If HELM_HOME is not set correctly the repo add
      commands fail.

    """
    methodName = 'configureHelm'
    
    try:
      TR.info(methodName, "Invoking: helm init --client-only")
      output = check_output(["helm", "init", "--client-only"])
      if (output): TR.info(methodName,"helm init output:\n%s" % output.rstrip())
    except CalledProcessError as e:
      if (e.output): TR.info(methodName,"ERROR: helm init output:\n%s" % e.output.rstrip())
      TR.error(methodName,"Exception calling helm init: %s" % e, e)
      raise e
    #endTry

    # Set HELM_HOME to the full path and visible to the Python process context.
    os.environ['HELM_HOME'] = self.HelmHome
    if (TR.isLoggable(Level.FINEST)):
      TR.finest(methodName,"HELM_HOME=%s" % os.environ.get('HELM_HOME'))
    #endIf

    # Copy the CA, user key and user cert to the default location in HELM_HOME.  
    shutil.copyfile(self.HelmKeyPath,self.UserKeyPath)
    shutil.copyfile(self.HelmCertPath,self.UserCertPath)
    shutil.copyfile(self.ClusterCertPath,self.CACertPath)
    
    try:
      TR.info(methodName, "Invoking: helm repo add ibm-charts https://raw.githubusercontent.com/IBM/charts/master/repo/stable/")
      output = check_output(["helm", "repo", "add", "ibm-charts", "https://raw.githubusercontent.com/IBM/charts/master/repo/stable/"])
      if (output):
        TR.info(methodName,"helm repo add ibm-charts output:\n%s" % output.rstrip())
      #endIf
    except CalledProcessError as e:
      if (e.output): TR.info(methodName,"ERROR: repo add ibm-charts output:\n%s" % e.output.rstrip())
      TR.error(methodName,"Exception calling repo add ibm-charts: %s" % e, e)
    #endTry

    
    try:
      TR.info(methodName, "Invoking: helm repo add ibmcase-spring https://raw.githubusercontent.com/ibm-cloud-architecture/refarch-cloudnative-spring/master/docs/charts/")
      output = check_output(["helm", "repo", "add", "ibmcase-spring", "https://raw.githubusercontent.com/ibm-cloud-architecture/refarch-cloudnative-spring/master/docs/charts/"])
      if (output):
        TR.info(methodName,"helm repo add ibmcase-spring output:\n%s" % output.rstrip())
      #endIf
    except CalledProcessError as e:
      if (e.output): TR.info(methodName,"ERROR: repo add ibmcase-spring output:\n%s" % e.output.rstrip())
      TR.error(methodName,"Exception calling repo add ibmcase-spring: %s" % e, e)
    #endTry


    # TBD: Need to pass in the env vars, so the next check_output() has a valid HELM_HOME
    # Without HELM_HOME and the key, cert, ca .pem files, an X.509 error occurs due to self-signed cert. 
    # TBD: Further investigation needed.  For unknown reasons the next to add the mgmt-charts requires the 
    # --ca-file, --key-file and --cert-file arguments on the command line.  It should pick that up from 
    # the HELM_HOME .pem files.
    #helmEnv = os.environ.copy()
    
    try:
      TR.info(methodName, "Invoking: helm repo add --ca-file {cacert} --cert-file {helmcert} --key-file {helmkey} mgmt-charts https://{cluster}:8443/mgmt-repo/charts".format(cacert=self.ClusterCertPath,helmcert=self.HelmCertPath,helmkey=self.HelmKeyPath,cluster=self.ClusterDNSName))
      output = check_output(["helm", "repo", "add", "--ca-file", self.ClusterCertPath, "--cert-file", self.HelmCertPath, "--key-file", self.HelmKeyPath, "mgmt-charts", "https://%s:8443/mgmt-repo/charts" % self.ClusterDNSName])
      # Use default ca, key, cert - DOES NOT WORK
      #TR.info(methodName, "Invoking: helm repo add mgmt-charts https://{cluster}:8443/mgmt-repo/charts".format(cluster=self.ClusterDNSName))
      #output = check_output(["helm", "repo", "add", "mgmt-charts", "https://%s:8443/mgmt-repo/charts" % self.ClusterDNSName], env=helmEnv)
      if (output): TR.info(methodName,"helm repo add mgmt-charts output:\n%s" % output.rstrip())
    except CalledProcessError as e:
      if (e.output): TR.info(methodName,"ERROR: repo add mgmt-charts output:\n%s" % e.output.rstrip())
      TR.error(methodName,"Exception calling repo add mgmt-charts: %s" % e, e)
    #endTry

  #endDef
  
  def installAndConfigureHelm(self):
    """
      Install and configure Helm
    """
    self.installHelm()
    self.configureHelm()
  #endDef
  
#endClass