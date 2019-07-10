#!/usr/bin/python
import sys
import os
import time
import stat
import string
from subprocess import call, check_call, CalledProcessError, Popen, check_output, PIPE
import socket
import fileinput
import yaml
import shutil
from yapl.aws.LogExporter import LogExporter
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.ICPExceptions import ICPInstallationException
from yapl.exceptions.Exceptions import ExitException
from yapl.utilities import Utilities
from bootstrap import Bootstrap
TR = Trace(__name__)


class DeployAddons(object):
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
        self.logsHome = os.path.join(self.home, "logs")
        self.dv = ["data-virtualization"]
        self.dsx = ["decision-optimization","data-refinery","spss-modeler","watson-explorer"]
        self.db2wh = ["db2-warehouse"]
    
    def readStackProps(self):
      try:
        methodName = "readStackProps"  
        stackPropsPath = os.path.join(self.home,"mystack.props")
        file = open(stackPropsPath)
        file.readline
        for line in file:
            fields = line.strip().split("=")
            if(fields[0]=="REGION"):
              self.bootstrap.region= fields[1]
            elif(fields[0]=="STACK_NAME"):
              self.bootstrap.rootStackName = fields[1]
            elif(fields[0]=="STACK_ID"):
              self.bootStackId = fields[1].lstrip('\"')
              self.bootStackId = self.bootStackId.rstrip('\"')
            elif(fields[0]=="ROLE"):
              self.bootstrap.role = fields[1]    
        #endFor
        TR.info(methodName,"StackName: %s, BootStackId: %s, region: %s, role: %s"%(self.bootstrap.rootStackName,self.bootStackId,self.bootstrap.region,self.bootstrap.role))
      except Exception, e:
       TR.error(methodName,"Exception: %s" % e, e)    
    #endDef  

    def replaceClusterName(self, fileName, existingValue, icpdInstallLogFile):
        methodName = "replaceClusterName"
        try:
            TR.info(methodName,"Replace existing value %s in file %s with %s" %(existingValue,fileName,self.registry))
            for line in fileinput.input(fileName, inplace=True):
                print line.replace(existingValue, self.registry),                     
        except Exception, e:
            TR.error(methodName,"Exception: %s" % e, e)   
    #endDef  

    def addNodeManagement(self, icpdInstallLogFile):
        methodName = "addNodeManagement"
        try:
            self.registry = self.bootstrap.ClusterDNSName+':8500'
            
            dockerLoginCMD = 'sudo docker login '+self.registry+'/zen -u '+self.bootstrap.AdminUser+' -p '+self.bootstrap.AdminPassword
            TR.info(methodName,"Logging into docker repository %s" %self.registry)
            call(dockerLoginCMD, shell=True, stdout=icpdInstallLogFile)


            dockerCMD = 'sudo docker rmi -f zenaddnode:v1 &>/dev/null'
            TR.info(methodName,"Removing old archive and docker images (if exists)")
            call(dockerCMD, shell=True, stdout=icpdInstallLogFile)
            dockerCMD = 'sudo docker rmi -f '+self.registry+'/ibmcom/zenaddnode:v1 &>/dev/null'
            call(dockerCMD, shell=True, stdout=icpdInstallLogFile)
    
            TR.info(methodName,"Downloading zenaddnode.tar")
            icpdS3Path = "{version}/{object}".format(version=self.installMap['version'],object=self.installMap['zenaddnode'])
            destPath = "/root/zenaddnode.tar"
            self.bootstrap.getS3Object(self.bootstrap.ICPDArchiveBucketName, icpdS3Path, destPath)

            TR.info(methodName,"Extract zenaddnode content %s" %os.getcwd())
            
            tarCMD = 'sudo tar -xvf /root/zenaddnode.tar'
            call(tarCMD, shell=True, stdout=icpdInstallLogFile)
            time.sleep(30)
            TR.info(methodName,"Loading and pushing the docker images ")
            dockerLoadCMD = 'sudo docker load -i /root/zenaddnode/zenaddnode.tar'
            call(dockerLoadCMD, shell=True, stdout=icpdInstallLogFile)
            dockerTagCMD = 'sudo docker tag zenaddnode:v1 '+self.registry+'/ibmcom/zenaddnode:v1'
            call(dockerTagCMD, shell=True, stdout=icpdInstallLogFile)
            dockerPushCMD = 'sudo docker push '+self.registry+'/ibmcom/zenaddnode:v1'
            call(dockerPushCMD, shell=True, stdout=icpdInstallLogFile)

            TR.info(methodName,"Delete existing deployment (if exists)")
            kubectlCMD = 'sudo kubectl delete deploy node-management -n kube-system --grace-period=0 --force &>/dev/null || true'
            call(kubectlCMD, shell=True, stdout=icpdInstallLogFile)
            time.sleep(60)

            TR.info(methodName,"Create new deployment")
            self.replaceClusterName("/root/zenaddnode/node_management.yaml", "DOCKER_REPOSITORY_FILLER", icpdInstallLogFile)
            kubectlCreateCMD = 'sudo kubectl create -f /root/zenaddnode/node_management.yaml'
            call(kubectlCreateCMD, shell=True, stdout=icpdInstallLogFile)
            time.sleep(120)
            TR.info(methodName,"Node-management pod is now deployed")

        except Exception, e:
            TR.error(methodName,"Exception: %s" % e, e)       
    #endDef    

      

    def main(self, argv):
        methodName = "main"
        self.rc = 0
        self.bootstrap = Bootstrap()
        try:
            os.chdir("/root")
            beginTime = Utilities.currentTimeMillis()
            trace = "*=all"
            logFile = "/root/logs/addons_deploy.log"
            if (logFile):
                TR.appendTraceLog(logFile)
            if (trace):
                TR.info(methodName, "NINIT0102I Tracing with specification: '%s' to log file: '%s'" % (
                    trace, logFile))
            # endIf
            self.readStackProps()
            self.bootstrap._init(self.bootstrap.rootStackName,self.bootStackId) 
            self.logExporter = LogExporter(region=self.bootstrap.region,
                                   bucket=self.bootstrap.ICPDeploymentLogsBucketName,
                                   keyPrefix='logs/%s' % self.bootstrap.rootStackName,
                                   role=self.bootstrap.role,
                                   fqdn=self.bootstrap.fqdn
                                   )

            addontoInstall = argv[1]
            dedicatedNode = ""
            if(len(argv)==3):
                dedicatedNode = argv[2]
            #endIf    
            addonList=""
            TR.info(methodName,"addontoInstall %s" %addontoInstall)
            if(addontoInstall=='Data_Virtualization'):
                addonList = self.dv
            elif(addontoInstall=='Db2_Warehouse'):
                addonList = self.db2wh
            elif(addontoInstall=='DSX_Premium'):
                addonList = self.dsx     
            TR.info(methodName,"Addons to be installed %s" %addonList)

            installMapPath = os.path.join(self.home,"maps","icpd-install-artifact-map.yaml")
            self.installMap = self.bootstrap.loadInstallMap(mapPath=installMapPath, version=self.bootstrap.ICPDVersion, region=self.bootstrap.region)
            
            for addonName in addonList:
                logFilePath = os.path.join(self.logsHome, addonName+".log")
                with open(logFilePath,"a+") as icpdInstallLogFile:
                    icpdS3Path = "{version}/{object}".format(version=self.installMap['version'],object=self.installMap[addonName+"-archive"])
                    destPath = self.installMap[addonName+"-dest"]
                    self.bootstrap.getS3Object(self.bootstrap.ICPDArchiveBucketName, icpdS3Path, destPath)
                    os.chmod(destPath, stat.S_IEXEC)
                    if(addonName!="db2-warehouse"):
                        if(addonName=="data-virtualization"):
                            #run kubectl create pvc.yaml
                            kubectlCMD = "sudo kubectl create -f /root/dv-pvc.yaml"
                            check_call(kubectlCMD,shell=True,stdout=icpdInstallLogFile)
                        #endIf    
                        installCMD = "sudo "+self.installMap["addon-install-CMD"]
                        addon_execute = installCMD+ " "+destPath

                        input = 'Y\nY\nY\nY\n'
                        TR.info(methodName,"Input for installer : %s" %(input))
                        process=Popen(addon_execute,shell=True,
                                                stdin=PIPE,
                                                stdout=icpdInstallLogFile,
                                                stderr=icpdInstallLogFile,close_fds=True)     
                        stdoutdata,stderrdata=process.communicate(input)
                        TR.info(methodName,"%s"%(stdoutdata))
                    else:
                        TR.info(methodName,"Install DB2wh")

                        self.addNodeManagement(icpdInstallLogFile)    
                        TR.info(methodName,"Create  db2-storage pvc")
                        kubectlCMD = "sudo kubectl create -f /root/db-pvc.yaml"
                        check_call(kubectlCMD,shell=True,stdout=icpdInstallLogFile)
                        os.chdir("/ibm/InstallPackage/databases/")   
                        os.makedirs('/ibm/InstallPackage/databases/Extract')
                        call('tar -xvf '+destPath+' -C Extract',shell=True, stdout=icpdInstallLogFile)

                        os.chdir('/ibm/InstallPackage/databases/Extract')
                        self.replaceClusterName("ibm-db2wh-2.0.0-x86_64.json", "mycluster.icp:8500", icpdInstallLogFile)
                        call('tar -xvf zen-databases-catalog.tar.gz', shell=True, stdout=icpdInstallLogFile)
    
                        os.chdir("/ibm/InstallPackage/databases/Extract/zen-databases-catalog")
                        self.replaceClusterName("values.yaml", "mycluster.icp:8500", icpdInstallLogFile)      
                        call('tar cvzf ../zen-databases-catalog.tar.gz .', shell=True, stdout=icpdInstallLogFile)
                        
                        os.chdir("/ibm/InstallPackage/databases/Extract")
                        shutil.rmtree('/ibm/InstallPackage/databases/zen-databases-catalog', ignore_errors=True)
                        
                        tarcmd = "tar cvzf "+destPath+" ."
                        call(tarcmd, shell=True, stdout=icpdInstallLogFile)
                        os.chdir("/root")

                        copyCMD = "sudo kubectl cp /root/.ssh/id_rsa kube-system/$(kubectl get pods -n kube-system | grep node-management | awk {'print $1'}):/tools/add-node-playbook/ssh_key"
                        TR.info(methodName,"Copy the key into the deployment %s"%copyCMD)
                        check_call(copyCMD, shell=True, stdout=icpdInstallLogFile)
                        TR.info(methodName,"Copied the key into the deployment%s"%copyCMD)

                        TR.info(methodName,"Enable db2wh")
                    
                        url  = "wget -qO- http://instance-data/latest/meta-data/local-ipv4"
                        bootNode_IP = check_output(url,shell=True)
                        
                        enableCMD = "sudo kubectl exec -it $(kubectl get pods -n kube-system | grep node-management | awk {'print $1'}) -n kube-system -- /tools/manage-nodes.sh --enable --master "+bootNode_IP+" --ppa-archive "+destPath+" --registry "+self.registry+" --icp-user admin  --icp-password "+self.bootstrap.AdminPassword+" --private-key"
                        check_call(enableCMD, shell=True, stdout=icpdInstallLogFile)
                        TR.info(methodName,"Enable db2wh")

                        os.chdir("/ibm/InstallPackage/databases/")
                        call('tar -xvf '+destPath,shell=True, stdout=icpdInstallLogFile)
                       
                        helmCMD = "sudo helm install --timeout 600 --tls --set arch=amd64 --set dbType=db2wh --name db2wh-catalog-3.6.1-amd64 --namespace zen zen-databases-catalog.tar.gz"
                        TR.info(methodName,"Execute Helm command %s"%helmCMD)
                        check_call(helmCMD, shell=True, stdout=icpdInstallLogFile)
                        TR.info(methodName,"Executed Helm command %s"%helmCMD)

                        if(dedicatedNode!=""):
                            TR.info(methodName,"Enable dedicated node for db2wh deployment with node %s" %dedicatedNode)
                            check_call(copyCMD, shell=True, stdout=icpdInstallLogFile)
                            configureCMD = "sudo kubectl exec -it $(kubectl get pods -n kube-system | grep node-management | awk {'print $1'}) -n kube-system -- /tools/manage-nodes.sh --configure-node --target-node "+dedicatedNode+" --master "+bootNode_IP+" --ppa-archive "+destPath+" --registry "+self.registry+" --icp-user admin  --icp-password "+self.bootstrap.AdminPassword+" --private-key"
                            check_call(configureCMD, shell=True, stdout=icpdInstallLogFile)
                            TR.info(methodName,"Enabled dedicated node for db2wh deployment")
                        #endIf    
                        
                     #endIf       
                #endWith    
            #endFor
        except ExitException:
            pass  # ExitException is used as a "goto" end of program after emitting help info

        except Exception, e:
            TR.error(methodName, "ERROR: %s" % e, e)
            self.rc = 1

        except BaseException, e:
            TR.error(methodName, "UNEXPECTED ERROR: %s" % e, e)
            self.rc = 1

        finally:
            endTime = Utilities.currentTimeMillis()
            elapsedTime = (endTime - beginTime)/1000
            etm, ets = divmod(elapsedTime, 60)
            eth, etm = divmod(etm, 60)

            if (self.rc == 0):
                TR.info(methodName, "BOOT0103I SUCCESS END Addon installation AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (
                    eth, etm, ets))
            else:
                TR.info(methodName, "BOOT0104I FAILED END Addon installation AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (
                    eth, etm, ets))
            # endIf

            try:
                # Copy the bootstrap logs to the S3 bucket for logs.
                self.logExporter.exportLogs(self.logsHome)
            except Exception, e:
                TR.error(methodName, "ERROR: %s" % e, e)
                self.rc = 1
            # endTry
        if (TR.traceFile):
            TR.closeTraceLog()
        # endIf

        sys.exit(self.rc)

        # endWith
    # endDef
# endClass


if __name__ == '__main__':
    mainInstance = DeployAddons()
    mainInstance.main(sys.argv)
# endIf
