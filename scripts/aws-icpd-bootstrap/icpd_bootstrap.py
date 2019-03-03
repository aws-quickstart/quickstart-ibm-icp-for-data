#!/usr/bin/python
import sys, os.path, time
from subprocess import call, check_call, CalledProcessError
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

  
  def installICPD(self):
    """
      Install ICPD by executing the script
      
      Script will copy required pre-requiste and extract the installer and run the deploy scripts
      
      It is assumed all the pre-installation configuration steps have been completed.
    """
    methodName = "installICPD"
    TR.info(methodName,"IBM Cloud Private for Data installation started.")

    logFilePath = os.path.join(self.logsHome,"icpd_install.log")
    with open(logFilePath,"a+") as knownHostsFile:
      TR.info(methodName,"self.home = %s"%(self.home))
      # Sharath MasterIPAddress needs to be retrieved from hosts
      TR.info(methodName," MasterIPAddress = %s CLustername = %s" %(self.bootstrap.getMasterIPAddresses()[0], self.bootstrap.ClusterDNSName))
      retcode = call(['sudo','/root/icpd_configure.sh', str(self.bootstrap.getMasterIPAddresses()[0]), str(self.bootstrap.ClusterDNSName), str(self.icpHome)], stdout=knownHostsFile)
      
    
      if (retcode != 0):
        raise ICPInstallationException("Error calling: './icpd_configure.sh' - Return code: %s" % retcode)
      #endif  
    #endwith
    TR.info(methodName,"IBM Cloud Private for Data installation completed.")

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