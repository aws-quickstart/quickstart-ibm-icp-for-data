#!/usr/bin/python
import sys, os, time, stat
from subprocess import call, check_call, CalledProcessError, Popen, check_output, PIPE
import boto3
import socket
import yaml
from yapl.aws.LogExporter import LogExporter
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.ICPExceptions import ICPInstallationException
from yapl.exceptions.Exceptions import ExitException
from yapl.utilities import Utilities
from bootstrap import Bootstrap
TR = Trace(__name__)


class ICPDBootstrap(object):
  ArgsSignature = {
                    '--help': 'string',
                    '--region': 'string',
                    '--stack-name': 'string',
                    '--stackid': 'string',
                    '--role': 'string',
                    '--logfile': 'string',
                    '--loglevel': 'string',
                    '--trace': 'string'
                   }
  
  def __init__(self):
    """
      Constructor
    """
    object.__init__(self)
    self.home = os.path.expanduser("~")
    self.logsHome = os.path.join(self.home,"logs")

  def makeDir(self, path):
    if not os.path.exists(path):
      os.makedirs(path)
    #endif 
  #enddef


  def setupBootNode(self, icpdInstallLogFile):
    methodName = "setupBootNode"
    # copy .docker contents to bootnode from masternode
    
    dockerpath = "/root/.docker"
    configFile = '/.docker/config.json'
    remoteHost = "root@"+self.bootstrap.getMasterIPAddresses()[0]
    scpCmd ="scp -o StrictHostKeyChecking=no "+remoteHost+":"
    config_scp = scpCmd+"~"+configFile+" ."

    TR.info(methodName,"Copy %s file from  %s using scp command %s" %(configFile, remoteHost,config_scp))     
    self.makeDir(dockerpath)
    os.chdir(dockerpath)
    call(config_scp,shell=True, stdout=icpdInstallLogFile)

    #copy certs from masternode to bootnode

    etcDockerPath ='/etc/docker/'
    certsPath = etcDockerPath+'certs.d/'
    registry = self.bootstrap.ClusterDNSName+':8500'
    registryPath = certsPath+registry
    rootCert= registryPath+'/root-ca.crt'
    caCert =  registryPath+'/ca.crt' 
    ca_scp = scpCmd+caCert+" ."
    root_scp = scpCmd+rootCert+" ."

    TR.info(methodName,"Copy %s and %s file from %s" %(rootCert, caCert, remoteHost)) 
    TR.info(methodName,"RootCert scp command:  %s" %(root_scp))
    TR.info(methodName,"CACert scp command:  %s" %(ca_scp))
    
    self.makeDir(registryPath)
    os.chdir(registryPath)
    call(ca_scp,shell=True, stdout=icpdInstallLogFile)
    call(root_scp,shell=True, stdout=icpdInstallLogFile)

  #endDef

  def installICPD(self):
    """
      Install ICPD by executing the script
      
      Script will copy required pre-requiste and extract the installer and run the deploy scripts
      
      It is assumed all the pre-installation configuration steps have been completed.
    """
    methodName = "installICPD"
    TR.info(methodName,"IBM Cloud Private for Data installation started.")
    # We really do not need this when ICP fixes the bootnode docker and certs issue
    # copy .docker contents to bootnode from masternode

    logFilePath = os.path.join(self.logsHome,"icpd_install.log")
    
    with open(logFilePath,"a+") as icpdInstallLogFile:
      self.setupBootNode(icpdInstallLogFile)

      # create /ibm folder and extract icp4d.tar contents to it
      TR.info(methodName,"Extract icp4d.tar to /ibm")

      self.makeDir('/ibm')
      call('tar -xvf /tmp/icp4d.tar -C /ibm/',shell=True, stdout=icpdInstallLogFile)
      os.chdir('/ibm')
      
      # cd to /ibm and give +x to installer file
      installCMD = self.installMap['installCMD']
      TR.info(methodName,"install CMD : %s" %(installCMD))
      os.chmod(installCMD, stat.S_IEXEC)	

      # docker login to registry to be on safer side
      registry = self.bootstrap.ClusterDNSName+':8500'
      dockerCMD = 'docker login '+registry+'/zen -u '+self.bootstrap.AdminUser+' -p '+self.bootstrap.AdminPassword
      call(dockerCMD, shell=True, stdout=icpdInstallLogFile)
      storageclass = int(self.storageclassValue)-1
      #Run installer with subprocess Popen command as pass input values through stdin pipe
      input = '\nA\nzen\nY\n'+registry+'/zen\n\nY\nN\n'+str(storageclass)+'\nY\nY'
      TR.info(methodName,"Input for installer : %s" %(input))
      
      runInstaller = 'sudo /ibm/'+installCMD
      process=Popen(runInstaller,shell=True,
                            stdin=PIPE,
                            stdout=icpdInstallLogFile,
                            stderr=icpdInstallLogFile,close_fds=True)     
      stdoutdata,stderrdata=process.communicate(input)


      TR.info(methodName,"%s"%(stdoutdata))    
      manageUser = "sudo python /root/manage_admin_user.py admin "+self.bootstrap.AdminPassword
      TR.info(methodName,"Start manageUser = %s"%(manageUser))    
      call(manageUser, shell=True, stdout=icpdInstallLogFile)
      TR.info(methodName,"End manageUser = %s"%(manageUser))    
      TR.info(methodName,"IBM Cloud Private for Data installation completed.")

    #endwith
  #endDef  

  def signalWaitHandle(self, eth, etm, ets):

    """
      Send a status signal to the "install completed" wait condition via the pre-signed URL
      provided to the stack.
      
      If the instance rc is 0, we send a --success true 
      If the instance rc is non-zero we send a --success false
      More detail on the status is provided in the --reason option of the signal.

      NOTE: A failure signal (--success false) causes a rollback of the CloudFormation templates.
      If the deployer does not use --disable-rollback, then the VMs are deleted and doing a post
      mortem can be more difficult. 
    """
    methodName = 'signalWaitHandle'
    try:
      if (self.rc == 0):
        success = 'true'
        status = 'SUCCESS'
      else:
        success = 'false'
        status = 'FAILURE: Check boot node logs in S3 log bucket or on the boot node EC2 instance in /root/logs bootstrap.log and /opt/icp/%s/cluster/logs install.log.*' % self.bootstrap.ICPVersion
      #endIf
      data = "%s: IBM Cloud Private installation elapsed time: %d:%02d:%02d" % (status,eth,etm,ets)
      TR.info(methodName,"Signaling: %s with status: %s, data: %s" % (self.bootstrap.ICPDInstallationCompletedURL,status,data))
      # Deployer should use --disable-rollback to avoid deleting the stack on failures and allow a post mortem.
      check_call(['/usr/local/bin/cfn-signal', 
                  '--success', success, 
                  '--id', self.bootStackId, 
                  '--reason', status, 
                  '--data', data, 
                  self.bootstrap.ICPDInstallationCompletedURL
                  ])
    except CalledProcessError as e:
      TR.error(methodName, "ERROR return code: %s, Exception: %s" % (e.returncode, e), e)
      raise e      
    #endTry    
  #endDef 


  def main(self,argv):
    methodName ="main"
    self.rc = 0
    self.bootstrap = Bootstrap()
    
    try:  
        beginTime = Utilities.currentTimeMillis()
        cmdLineArgs = Utilities.getInputArgs(self.ArgsSignature,argv[1:])
        trace, logFile = self.bootstrap._configureTraceAndLogging(cmdLineArgs)
        TR.info(methodName,"BOOT0101I BEGIN Bootstrap AWS ICPD Quickstart version 1.0.0.")
        if (trace):
            TR.info(methodName,"BOOT0102I Tracing with specification: '%s' to log file: '%s'" % (trace,logFile))
        #endIf
       
        region = cmdLineArgs.get('region')
        self.bootstrap.region = region
        self.bootstrap.role = cmdLineArgs.get('role')
        self.bootstrap.fqdn = socket.getfqdn()

        self.bootStackId = cmdLineArgs.get('stackid')
        self.bootstrap.rootStackName = cmdLineArgs.get('stack-name')  
        self.bootstrap._init(self.bootstrap.rootStackName,self.bootStackId)
        
        self.logExporter = LogExporter(region=self.bootstrap.region,
                                   bucket=self.bootstrap.ICPDeploymentLogsBucketName,
                                   keyPrefix='logs/%s' % self.bootstrap.rootStackName,
                                   role=self.bootstrap.role,
                                   fqdn=self.bootstrap.fqdn
                                   )
        self.icpHome = "/opt/icp/%s" % self.bootstrap.ICPVersion
        installMapPath = os.path.join(self.home,"maps","icpd-install-artifact-map.yaml")
        self.installMap = self.bootstrap.loadInstallMap(mapPath=installMapPath, version=self.bootstrap.ICPDVersion, region=self.bootstrap.region)
        icpdS3Path = "{version}/{object}".format(version=self.installMap['version'],object=self.installMap['icpd-base-install-archive'])
        destPath = "/tmp/icp4d.tar"
        storageClassCmd = "kubectl get storageclass | nl | grep aws-efs | awk '{print $1}'"
        TR.info(methodName,"check_output Get StorageClass value from kubectl %s"%(storageClassCmd))
        self.storageclassValue=check_output(['bash','-c', storageClassCmd])
        TR.info(methodName,"check_output  StorageclassValue returned : %s"%(self.storageclassValue))
        self.bootstrap.getS3Object(self.bootstrap.ICPDArchiveBucketName, icpdS3Path, destPath) 
      
        self.stackIds =  self.bootstrap._getStackIds(self.bootStackId)
        self.bootstrap._getHosts(self.stackIds)
        
        self.installICPD()
    except ExitException:
        pass # ExitException is used as a "goto" end of program after emitting help info

    except Exception, e:
        TR.error(methodName,"ERROR: %s" % e, e)
        self.rc = 1
      
    except BaseException, e:
        TR.error(methodName,"UNEXPECTED ERROR: %s" % e, e)
        self.rc = 1

    finally:
        try:
          # Copy icpHome/logs to the S3 bucket for logs.
          self.logExporter.exportLogs("%s/cluster/logs" % self.icpHome)
        except Exception, e:
          TR.error(methodName,"ERROR: %s" % e, e)
          self.rc = 1
        #endTry

   
        endTime = Utilities.currentTimeMillis()
        elapsedTime = (endTime - beginTime)/1000
        etm, ets = divmod(elapsedTime,60)
        eth, etm = divmod(etm,60) 

        if (self.rc == 0):
          TR.info(methodName,"BOOT0103I SUCCESS END Boostrap AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
        else:
          TR.info(methodName,"BOOT0104I FAILED END Boostrap AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
        #endIf
      
        try:
          # Copy the bootstrap logs to the S3 bucket for logs.
          self.logExporter.exportLogs(self.logsHome)
        except Exception, e:
          TR.error(methodName,"ERROR: %s" % e, e)
          self.rc = 1
        #endTry
      
        self.signalWaitHandle(eth,etm,ets)

    #endTry
    if (TR.traceFile):
      TR.closeTraceLog()
    #endIf
    
    sys.exit(self.rc)

    #endWith
  #endDef    
#endClass    


if __name__ == '__main__':
  mainInstance = ICPDBootstrap()
  mainInstance.main(sys.argv)
#endIf