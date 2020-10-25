#!/usr/bin/python
import sys, os.path, time, stat, socket, base64,json
import boto3
import shutil
import requests
import yapl.Utilities as Utilities
from subprocess import call,check_output, check_call, CalledProcessError, Popen, PIPE
from os import chmod, environ
from botocore.exceptions import ClientError
from yapl.Trace import Trace, Level
from yapl.LogExporter import LogExporter
from yapl.Exceptions import MissingArgumentException

TR = Trace(__name__)
StackParameters = {}
StackParameterNames = []
class CPDInstall(object):
    ArgsSignature = {
                    '--region': 'string',
                    '--stack-name': 'string',
                    '--stackid': 'string',
                    '--logfile': 'string',
                    '--loglevel': 'string',
                    '--trace': 'string'
                   }

    def __init__(self):
        """
        Constructor
        NOTE: Some instance variable initialization happens in self._init() which is 
        invoked early in main() at some point after _getStackParameters().
        """
        object.__init__(self)
        self.home = os.path.expanduser("/ibm")
        self.logsHome = os.path.join(self.home,"logs")
        self.sshHome = os.path.join(self.home,".ssh")
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

        trace = self._getArg(['trace', 'loglevel'], traceArgs)

        if (trace):
            if (not logFile):
                TR.appendTraceLog('trace.log')
            #endDef

        TR.configureTrace(trace)
        #endIf
        return (trace,logFile)
    #endDef
    def getStackParameters(self, stackId):
        """
        Return a dictionary with stack parameter name-value pairs from the  
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
        initialized in getStackParameters().
        """
        if (attributeName in StackParameterNames):
            StackParameters[attributeName] = attributeValue
        else:
            object.__setattr__(self, attributeName, attributeValue)
        #endIf
    #endDef
   
 
    def installCPD(self,icpdInstallLogFile):
        """
        creates a OC project with user defined name
        Downloads binary file from S3 and extracts it to /ibm folder
        installs user selected services using transfer method
        """

        methodName = "installCPD"
        self.getS3Object(bucket=self.cpdbucketName, s3Path="3.0/cpd-linux", destPath="/ibm/cpd-linux")
        os.chmod("/ibm/cpd-linux", stat.S_IEXEC)	
        self.repoFile = "/ibm/repo.yaml"
        
        
        self.getS3Object(bucket=self.cpdbucketName, s3Path="3.0/repo.yaml", destPath=self.repoFile)
        TR.info(methodName, "updating repo.yaml with apikey value provided")
        
        #TODO change this later
        self.updateTemplateFile(self.repoFile, '${apikeyusername}',self.APIUsername)
        self.updateTemplateFile(self.repoFile ,'${apikey}',self.apiKey)
      
        default_route = "oc get route default-route -n openshift-image-registry --template='{{ .spec.host }}'"
        TR.info(methodName,"Get default route  %s"%default_route)
        try:
            self.regsitry = check_output(['bash','-c', default_route]) 
            TR.info(methodName,"Completed %s command with return value %s" %(default_route,self.regsitry))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        self.ocpassword = self.readFileContent("/ibm/installDir/auth/kubeadmin-password").rstrip("\n\r")
        try:
            oc_login = "oc login -u kubeadmin -p "+self.ocpassword
            retcode = call(oc_login,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Log in to OC with admin user %s"%retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    


        # oc set env deployment/image-registry -n openshift-image-registry REGISTRY_STORAGE_S3_CHUNKSIZE=104857600

        set_s3_storage_limit = "oc set env deployment/image-registry -n openshift-image-registry REGISTRY_STORAGE_S3_CHUNKSIZE=104857600"
        try:
            retcode = call(set_s3_storage_limit,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"set_s3_storage_limit %s retcode=%s" %(set_s3_storage_limit,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))  


        oc_new_project ="oc new-project "+self.Namespace
        try:
            retcode = call(oc_new_project,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Create new project with user defined project name %s,retcode=%s" %(self.Namespace,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        self.token = self.getToken(icpdInstallLogFile)
        if(self.StorageType=='OCS'):
            self.storageClass = "ocs-storagecluster-cephfs"
            self.storageOverrideFile = "/ibm/override_ocs.yaml"
            self.storageOverride = " -o"+self.storageOverrideFile
        elif(self.StorageType=='Portworx'):    
            self.storageClass = "portworx-shared-gp3"
            self.storageOverrideFile = "/ibm/override_px.yaml"
            self.storageOverride = " -o"+self.storageOverrideFile
        elif(self.StorageType=='EFS'):
            self.storageClass = "aws-efs"
            self.storageOverride = ""
        litestart = Utilities.currentTimeMillis()
        TR.info(methodName,"Start installing Lite package")
        self.installAssemblies("lite",icpdInstallLogFile)
        liteend = Utilities.currentTimeMillis()
        self.printTime(litestart, liteend, "Installing Lite")

        get_cpd_route_cmd = "oc get route -n "+self.Namespace+ " | grep '"+self.Namespace+"' | awk '{print $2}'"
        TR.info(methodName, "Get CPD URL")
        try:
            self.cpdURL = check_output(['bash','-c', get_cpd_route_cmd]) 
            TR.info(methodName, "CPD URL retrieved %s"%self.cpdURL)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        if(self.installSpark):
            TR.info(methodName,"Start installing Spark AE package")
            sparkstart = Utilities.currentTimeMillis()
            self.installAssemblies("spark",icpdInstallLogFile)
            sparkend = Utilities.currentTimeMillis()
            TR.info(methodName,"Spark AE  package installation completed")
            self.printTime(sparkstart, sparkend, "Installing Spark AE")   

        if(self.installDV):
            TR.info(methodName,"Start installing DV package")
            dvstart = Utilities.currentTimeMillis()
            self.installAssemblies("dv",icpdInstallLogFile)
            dvend = Utilities.currentTimeMillis()
            TR.info(methodName,"DV package installation completed")
            self.printTime(dvstart, dvend, "Installing DV")    
        
        if(self.installWSL):

            TR.info(methodName,"Start installing WSL package")
            wslstart = Utilities.currentTimeMillis()
            self.installAssemblies("wsl",icpdInstallLogFile)
            wslend = Utilities.currentTimeMillis()
            TR.info(methodName,"WSL package installation completed")
            self.printTime(wslstart, wslend, "Installing WSL")
        
        if(self.installWML):
            TR.info(methodName,"Start installing WML package")
            wmlstart = Utilities.currentTimeMillis()
            self.installAssemblies("wml",icpdInstallLogFile)
            wmlend = Utilities.currentTimeMillis()
            TR.info(methodName,"WML package installation completed")
            self.printTime(wmlstart, wmlend, "Installing WML")
        
        if(self.installWKC):
            TR.info(methodName,"Start installing WKC package")
            wkcstart = Utilities.currentTimeMillis()
            self.installAssemblies("wkc",icpdInstallLogFile)
            wkcend = Utilities.currentTimeMillis()
            TR.info(methodName,"WKC package installation completed")
            self.printTime(wkcstart, wkcend, "Installing WKC")

        if(self.installOSWML):
            TR.info(methodName,"Start installing AI Openscale package")
            aiostart = Utilities.currentTimeMillis()
            self.installAssemblies("aiopenscale",icpdInstallLogFile)
            aioend = Utilities.currentTimeMillis()
            TR.info(methodName,"AI Openscale package installation completed")
            self.printTime(aiostart, aioend, "Installing AI Openscale")    

        if(self.installCDE):
            TR.info(methodName,"Start installing Cognos Dashboard package")
            cdestart = Utilities.currentTimeMillis()
            self.installAssemblies("cde",icpdInstallLogFile)
            cdeend = Utilities.currentTimeMillis()
            TR.info(methodName,"Cognos Dashboard package installation completed")
            self.printTime(cdestart, cdeend, "Installing Cognos Dashboard")  

               


        TR.info(methodName,"Installed all packages.")
    #endDef    
    def printTime(self, beginTime, endTime, text):
        """
        method to capture time elapsed for each event during installation
        """
        methodName = "printTime"
        elapsedTime = (endTime - beginTime)/1000
        etm, ets = divmod(elapsedTime,60)
        eth, etm = divmod(etm,60) 
        TR.info(methodName,"Elapsed time (hh:mm:ss): %d:%02d:%02d for %s" % (eth,etm,ets,text))
    #endDef

    def getToken(self,icpdInstallLogFile):
        """
        method to get sa token to be used to push and pull from local docker registry
        """
        methodName = "getToken"
        create_sa_cmd = "oc create serviceaccount cpdtoken"
        TR.info(methodName,"Create service account cpdtoken %s"%create_sa_cmd)
        try:
            retcode = call(create_sa_cmd,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Created service account cpdtoken %s"%retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        addrole_cmd = "oc policy add-role-to-user admin system:serviceaccount:"+self.Namespace+":cpdtoken"
        TR.info(methodName," Add role to service account %s"%addrole_cmd)
        try:
            retcode = call(addrole_cmd,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Role added to service account %s"%retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        get_token_cmd = "oc serviceaccounts get-token cpdtoken"
        TR.info(methodName,"Retrieve token from service account %s"%get_token_cmd)
        return check_output(['bash','-c', get_token_cmd])
    #endDef    
    def updateTemplateFile(self, source, placeHolder, value):
        """
        method to update placeholder values in templates
        """
        source_file = open(source).read()
        source_file = source_file.replace(placeHolder, value)
        updated_file = open(source, 'w')
        updated_file.write(source_file)
        updated_file.close()
    #endDef    
    def readFileContent(self,source):
        file = open(source,mode='r')
        content = file.read()
        file.close()
        return content.rstrip()

    def installAssemblies(self, assembly, icpdInstallLogFile):
        """
        method to install assemlies
        for each assembly this method will execute adm command to apply all prerequistes
        Images will be pushed to local registry
        Installation will be done for the assembly using local registry
        """
        methodName = "installAssemblies"

        registry = self.regsitry+"/"+self.Namespace
        apply_cmd = "/ibm/cpd-linux adm -r /ibm/repo.yaml -a "+assembly+"  -n "+self.Namespace+" --accept-all-licenses --apply | tee /ibm/logs/"+assembly+"_apply.log"
        TR.info(methodName,"Execute apply command for assembly %s"%apply_cmd)
        try:
            retcode = call(apply_cmd,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Executed apply command for assembly %s returned %s"%(assembly,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))

        install_cmd = "/ibm/cpd-linux -c "+self.storageClass+" "+self.storageOverride+" -r /ibm/repo.yaml -a "+assembly+" -n "+self.Namespace+" --transfer-image-to="+registry+" --target-registry-username=kubeadmin  --target-registry-password="+self.token+" --cluster-pull-prefix image-registry.openshift-image-registry.svc:5000/"+self.Namespace+" --accept-all-licenses --insecure-skip-tls-verify | tee /ibm/logs/"+assembly+"_install.log"
        try:     
            retcode = call(install_cmd,shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"Execute install command for assembly %s returned %s"%(assembly,retcode))  
        except CalledProcessError as e:
            TR.error(methodName,"Exception while installing service %s with message %s" %(assembly,e))
            self.rc = 1
 

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
        
        s3url = self.s3.generate_presigned_url(ClientMethod='get_object',Params={'Bucket': bucket, 'Key': s3Path},ExpiresIn=60)
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
    
    def validateInstall(self, icpdInstallLogFile):
        """
            This method is used to validate the installation at the end. At times some services fails and it is not reported. 
            We use this method to check if cpd operator is up and running. We will then get the helm list of deployed services and validate for each of the services selected by user. IF the count adds up to the defined count then installation is successful. Else  will be flagged it as failure back to cloud Formation.
        """

        methodName = "validateInstall"
        count = 3
        TR.info(methodName,"Validate Installation status")
        if(self.installDV):
            count = count+1
        if(self.installOSWML):
            count = count+1    
        if(self.installSpark):
            count = count+1    
        if(self.installWKC):
            count = count+6
        if(self.installCDE):
            count = count+1
        if(self.installWML):
            count = count+2
        if(self.installWSL):
            count = count+4            

        # CCS Count
        if(self.installCDE or self.installWKC or self.installWSL or self.installWML):
            count = count+8
        # DR count    
        if(self.installWSL or self.installWKC):
            count = count+1                

        operator_pod = "oc get pods | grep cpd-install-operator | awk '{print $1}'"
        operator_status = "oc get pods | grep cpd-install-operator | awk '{print $3}'"
        validate_cmd = "oc exec -it $(oc get pods | grep cpd-install-operator | awk '{print $1}') -- helm list --tls"
        operator = check_output(['bash','-c',operator_pod])
        TR.info(methodName,"Operator pod %s"%operator)
        if(operator == ""):
            self.rc = 1
            return
        op_status = check_output(['bash','-c',operator_status])
        TR.info(methodName,"Operator pod status is %s"%op_status)
        if(op_status.rstrip()!="Running"):
            self.rc = 1
            return   
        install_status = check_output(['bash','-c',validate_cmd])
        TR.info(methodName,"Installation status is %s"%install_status)
        TR.info(methodName,"Actual Count is %s Deployed count is %s"%(count,install_status.count("DEPLOYED")))
        if(install_status.count("DEPLOYED")< count):
            self.rc = 1
            TR.info(methodName,"Installation Deployed count  is %s"%install_status.count("DEPLOYED"))
            return   

    #endDef    

    def manageUser(self, icpdInstallLogFile):
        """
        method to update the default password of admin user of CPD with user defined password 
        Note: CPD password will be same as Openshift Cluster password
        """
        methodName = "manageUser"  
        manageUser = "sudo python /ibm/manage_admin_user.py "+self.Namespace+" admin "+self.password
        TR.info(methodName,"Start manageUser")    
        try:
            call(manageUser, shell=True, stdout=icpdInstallLogFile)
            TR.info(methodName,"End manageUser")    
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
                
    # #endDef
    # #     
    # def activateLicense(self, icpdInstallLogFile):
    #     """
    #     method to activate trial license for cpd installation
    #     """
    #     methodName = "activateLicense"
    #     self.updateTemplateFile('/ibm/activate-license.sh','<ELB_DNSNAME>',self.hostname)
    #     TR.info(methodName,"Start Activate trial")
    #     icpdUrl = "https://"+self.hostname
    #     activatetrial = "sudo python /ibm/activate-trial.py "+icpdUrl+" admin "+self.password+" /ibm/trial.lic"
    #     try:
    #         call(activatetrial, shell=True, stdout=icpdInstallLogFile)
    #     except CalledProcessError as e:
    #         TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
    #     TR.info(methodName,"End Activate trial")
    #     TR.info(methodName,"IBM Cloud Pak for Data installation completed.")
    # #endDef    

    def updateStatus(self, status):
        methodName = "updateStatus"
        TR.info(methodName," Update Status of installation")
        data = "301_AWS_STACKNAME="+self.stackName+",Status="+status
        updateStatus = "curl -X POST https://un6laaf4v0.execute-api.us-west-2.amazonaws.com/testtracker --data "+data
        try:
            call(updateStatus, shell=True)
            TR.info(methodName,"Updated status with data %s"%data)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
    #endDef    
    
    def configureEFS(self):
        """
        Configure an EFS volume and configure all worker nodes to be able to use 
        the EFS storage provisioner.
        """
        methodName = "configureEFS"
        
        TR.info(methodName,"STARTED configuration of EFS")
        # Create the EFS provisioner service account

        """
        oc create -f efs-configmap.yaml -n default
        oc create serviceaccount efs-provisioner
        oc create -f  efs-rbac-template.yaml
        oc create -f efs-storageclass.yaml
        oc create -f efs-provisioner.yaml
        oc create -f efs-pvc.yaml
        """
    
    #    self.updateTemplateFile(workerocs,'${az1}', self.zones[0])
        self.updateTemplateFile("/ibm/templates/efs/efs-configmap.yaml",'${file-system-id}',self.EFSID)
        self.updateTemplateFile("/ibm/templates/efs/efs-configmap.yaml",'${aws-region}',self.region)
        self.updateTemplateFile("/ibm/templates/efs/efs-configmap.yaml",'${efsdnsname}',self.EFSDNSName)

        self.updateTemplateFile("/ibm/templates/efs/efs-provisioner.yaml",'${file-system-id}',self.EFSID)
        self.updateTemplateFile("/ibm/templates/efs/efs-provisioner.yaml",'${aws-region}',self.region)

        TR.info(methodName,"Invoking: oc create -f efs-configmap.yaml -n default")
        cm_cmd = "oc create -f /ibm/templates/efs/efs-configmap.yaml -n default"
        retcode = call(cm_cmd, shell=True)
        if (retcode != 0):
            TR.info(methodName,"Invoking: oc create -f efs-configmap.yaml -n default %s" %retcode)
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf

        TR.info(methodName,"Invoking: oc create serviceaccount efs-provisioner")
        sa_cmd = "oc create serviceaccount efs-provisioner"
        retcode = call(sa_cmd, shell=True)
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf

        TR.info(methodName,"Invoking: oc create -f  efs-rbac-template.yaml")
        rbac_cmd = "oc create -f  /ibm/templates/efs/efs-rbac-template.yaml"
        retcode = call(rbac_cmd, shell=True)
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf

        TR.info(methodName,"Invoking: oc create -f efs-storageclass.yaml")
        sc_cmd = "oc create -f /ibm/templates/efs/efs-storageclass.yaml"
        retcode = call(sc_cmd, shell=True)
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf
        
        TR.info(methodName,"Invoking: oc create -f efs-provisioner.yaml")
        prov_cmd = "oc create -f /ibm/templates/efs/efs-provisioner.yaml"
        retcode = call(prov_cmd, shell=True)
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf
        
        TR.info(methodName,"Invoking: oc create -f efs-pvc.yaml")
        pvc_cmd = "oc create -f /ibm/templates/efs/efs-pvc.yaml"
        retcode = call(pvc_cmd, shell=True)
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf                
        
        TR.info(methodName,"COMPLETED configuration of EFS.")
      
    #endDef   
    
    def configureOCS(self,icpdInstallLogFile):
        """
        This method reads user preferences from stack parameters and configures OCS as storage classs accordingly.
        Depending on 1 or 3 AZ appropriate template file is used to create machinesets.
        """
        methodName = "configureOCS"
        TR.info(methodName,"  Start configuration of OCS for CPD")
        workerocs = "/ibm/templates/ocs/workerocs.yaml"
        workerocs_1az = "/ibm/templates/ocs/workerocs1AZ.yaml"
        if(len(self.zones)==1):
            shutil.copyfile(workerocs_1az,workerocs)
        self.updateTemplateFile(workerocs,'${az1}', self.zones[0])
        self.updateTemplateFile(workerocs,'${ami_id}', self.amiID)
        self.updateTemplateFile(workerocs,'${instance-type}', self.OCSInstanceType)
        self.updateTemplateFile(workerocs,'${instance-count}', self.NumberOfOCS)
        self.updateTemplateFile(workerocs,'${region}', self.region)
        self.updateTemplateFile(workerocs,'${cluster-name}', self.ClusterName)
        self.updateTemplateFile(workerocs, 'CLUSTERID', self.clusterID)
        self.updateTemplateFile(workerocs,'${subnet-1}',self.PrivateSubnet1ID)
        

        if(len(self.zones)>1):
            self.updateTemplateFile(workerocs,'${az2}', self.zones[1])
            self.updateTemplateFile(workerocs,'${az3}', self.zones[2])
            self.updateTemplateFile(workerocs,'${subnet-2}',self.PrivateSubnet2ID)
            self.updateTemplateFile(workerocs,'${subnet-3}',self.PrivateSubnet3ID)

        create_ocs_nodes_cmd = "oc create -f "+workerocs
        TR.info(methodName,"Create OCS nodes")
        try:
            retcode = check_output(['bash','-c', create_ocs_nodes_cmd])
            time.sleep(300)
            TR.info(methodName,"Created OCS nodes %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        
        ocs_nodes = []
        get_ocs_nodes = "oc get nodes --show-labels | grep storage-node |cut -d' ' -f1 "
        try:
            ocs_nodes = check_output(['bash','-c',get_ocs_nodes])
            nodes = ocs_nodes.split("\n")
            TR.info(methodName,"OCS_NODES %s"%nodes)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        i =0
        while i < len(nodes)-1:
            TR.info(methodName,"Labeling for OCS node  %s " %nodes[i])
            label_cmd = "oc label nodes "+nodes[i]+" cluster.ocs.openshift.io/openshift-storage=''"
            try: 
                retcode = check_output(['bash','-c', label_cmd])
                TR.info(methodName,"Label for OCS node  %s returned %s" %(nodes[i],retcode))
            except CalledProcessError as e:
                TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
            i += 1


        deploy_olm_cmd = "oc create -f /ibm/templates/ocs/deploy-with-olm.yaml"
        TR.info(methodName,"Deploy OLM")
        try:
            retcode = check_output(['bash','-c', deploy_olm_cmd]) 
            time.sleep(300)
            TR.info(methodName,"Deployed OLM %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        create_storage_cluster_cmd = "oc create -f /ibm/templates/ocs/ocs-storagecluster.yaml"
        TR.info(methodName,"Create Storage Cluster")
        try:
            retcode = check_output(['bash','-c', create_storage_cluster_cmd]) 
            time.sleep(600)
            TR.info(methodName,"Created Storage Cluster %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        install_ceph_tool_cmd = "curl -s https://raw.githubusercontent.com/rook/rook/release-1.1/cluster/examples/kubernetes/ceph/toolbox.yaml|sed 's/namespace: rook-ceph/namespace: openshift-storage/g'| oc apply -f -"
        TR.info(methodName,"Install ceph toolkit")
        try:
            retcode = check_output(['bash','-c', install_ceph_tool_cmd]) 
            TR.info(methodName,"Installed ceph toolkit %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output)) 
        TR.info(methodName,"Configuration of OCS for CPD completed")
    #endDef    

    def preparePXInstall(self,icpdInstallLogFile):
        """
        This method does all required background work like creating policy required to spin up EBS volumes, updating security group with portworx specific ports.
        """
        methodName = "preparePXInstall"
        TR.info(methodName,"Pre requisite for Portworx Installation")

        
        """
        #INST_PROFILE_NAME=`aws ec2 describe-instances --query 'Reservations[*].Instances[*].[IamInstanceProfile.Arn]' --output text | cut -d ':' -f 6 | cut -d '/' -f 2 | grep worker* | uniq`
        """
        TR.info(methodName,"Get INST_PROFILE_NAME")
        tag_value = self.clusterID+"-worker*"
        TR.info(methodName,"Tag value of worker to look for %s"%tag_value)
        response = self.ec2.describe_instances(Filters=[{'Name': 'tag:Name','Values': [tag_value]}])
        TR.info(methodName,"response %s"%response)
        reservation = response['Reservations']
        TR.info(methodName,"reservation %s"%reservation)
        for item in reservation:
            instances = item['Instances']
            TR.info(methodName,"instances %s"%instances)
            for instance in instances:
                if 'IamInstanceProfile' in instance:
                    instanceProfile = instance['IamInstanceProfile']['Arn'].split("/")[1]
                    TR.info(methodName,"instanceProfile %s"%instanceProfile)

        TR.info(methodName,"Instance profile retrieved %s"%instanceProfile)
        #ROLE_NAME=`aws iam get-instance-profile --instance-profile-name $INST_PROFILE_NAME --query 'InstanceProfile.Roles[*].[RoleName]' --output text`        
        TR.info(methodName,"Get Role name")
        iamresponse = self.iam.get_instance_profile(InstanceProfileName=instanceProfile)
        rolename = iamresponse['InstanceProfile']['Roles'][0]['RoleName']
        TR.info(methodName,"Role name retrieved %s"%rolename)
        #POLICY_ARN=`aws iam create-policy --policy-name portworx-policy-${VAR} --policy-document file://policy.json --query 'Policy.Arn' --output text`

        policycontent = {'Version': '2012-10-17', 'Statement': [{'Action': ['ec2:AttachVolume', 'ec2:ModifyVolume', 'ec2:DetachVolume', 'ec2:CreateTags', 'ec2:CreateVolume', 'ec2:DeleteTags', 'ec2:DeleteVolume', 'ec2:DescribeTags', 'ec2:DescribeVolumeAttribute', 'ec2:DescribeVolumesModifications', 'ec2:DescribeVolumeStatus', 'ec2:DescribeVolumes', 'ec2:DescribeInstances'], 'Resource': ['*'], 'Effect': 'Allow'}]}
        TR.info(methodName,"Get policy_arn")
        policyName = "portworx-policy-"+self.ClusterName
        policy = self.iam.create_policy(PolicyName=policyName,PolicyDocument=json.dumps(policycontent))
        policy_arn = policy['Policy']['Arn']
        destroy_sh = "/ibm/destroy.sh"
        self.updateTemplateFile(destroy_sh,'$ROLE_NAME',rolename)
        self.updateTemplateFile(destroy_sh,'$POLICY_ARN',policy_arn)
        TR.info(methodName,"Policy_arn retrieved %s"%policy_arn)
        # aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn $POLICY_ARN
        TR.info(methodName,"Attach IAM policy")
        response = self.iam.attach_role_policy(RoleName=rolename,PolicyArn=policy_arn)
        TR.info(methodName,"Attached role policy returned %s"%response)
        """
        WORKER_TAG=`aws ec2 describe-security-groups --query 'SecurityGroups[*].Tags[*][Value]' --output text | grep worker`
        MASTER_TAG=`aws ec2 describe-security-groups --query 'SecurityGroups[*].Tags[*][Value]' --output text | grep master`
        WORKER_GROUP_ID=`aws ec2 describe-security-groups --filters Name=tag:Name,Values=$WORKER_TAG --query "SecurityGroups[*].{Name:GroupId}" --output text`
        MASTER_GROUP_ID=`aws ec2 describe-security-groups --filters Name=tag:Name,Values=$MASTER_TAG --query "SecurityGroups[*].{Name:GroupId}" --output text`
        """
        TR.info(methodName,"Retrieve tags and group id from security groups")
        ret = self.ec2.describe_security_groups()
        worker_sg_value = self.clusterID+"-worker-sg"
        master_sg_value = self.clusterID+"-master-sg"
        sec_groups = ret['SecurityGroups']
        for sg in sec_groups:
            if 'Tags' in sg:
                tags = sg['Tags']
                for tag in tags:
                    if worker_sg_value in tag['Value']:
                        worker_tag = tag['Value']
                    elif master_sg_value in tag['Value']:
                        master_tag = tag['Value']

        worker_group = self.ec2.describe_security_groups(Filters=[{'Name':'tag:Name','Values':[worker_tag]}])
        sec_groups = worker_group['SecurityGroups']
        for sg in sec_groups:
            worker_group_id = sg['GroupId']
        master_group = self.ec2.describe_security_groups(Filters=[{'Name':'tag:Name','Values':[master_tag]}])
        sec_groups = master_group['SecurityGroups']
        for sg in sec_groups:
            master_group_id = sg['GroupId']

        TR.info(methodName,"Retrieved worker tag %s master tag %s and  worker group id %s  master group id %s from security groups"%(worker_tag,master_tag,worker_group_id,master_group_id))
        """
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 17001-17020 --source-group $MASTER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 17001-17020 --source-group $WORKER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 111 --source-group $MASTER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 111 --source-group $WORKER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 2049 --source-group $MASTER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 2049 --source-group $WORKER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 20048 --source-group $MASTER_GROUP_ID
        aws ec2 authorize-security-group-ingress --group-id $WORKER_GROUP_ID --protocol tcp --port 20048 --source-group $WORKER_GROUP_ID 
        """  
        TR.info(methodName,"Start authorize-security-group-ingress")
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':17001,'ToPort':17020,'UserIdGroupPairs':[{'GroupId':master_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':17001,'ToPort':17020,'UserIdGroupPairs':[{'GroupId':worker_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':111,'ToPort':111,'UserIdGroupPairs':[{'GroupId':worker_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':111,'ToPort':111,'UserIdGroupPairs':[{'GroupId':master_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':2049,'ToPort':2049,'UserIdGroupPairs':[{'GroupId':worker_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':2049,'ToPort':2049,'UserIdGroupPairs':[{'GroupId':master_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':20048,'ToPort':20048,'UserIdGroupPairs':[{'GroupId':worker_group_id}]}])
        self.ec2.authorize_security_group_ingress(GroupId=worker_group_id,IpPermissions=[{'IpProtocol':'tcp','FromPort':20048,'ToPort':20048,'UserIdGroupPairs':[{'GroupId':master_group_id}]}])
        TR.info(methodName,"End authorize-security-group-ingress")
        TR.info(methodName,"Done Pre requisite for Portworx Installation")
    #endDef    

    def updateScc(self,icpdInstallLogFile):
        """
            This method is used to update the SCC required for portworx installation.
        """
        methodName = "updateScc"
        TR.info(methodName,"Start Updating SCC for Portworx Installation")
        """
        oc adm policy add-scc-to-user privileged system:serviceaccount:kube-system:px-account
        oc adm policy add-scc-to-user privileged system:serviceaccount:kube-system:portworx-pvc-controller-account
        oc adm policy add-scc-to-user privileged system:serviceaccount:kube-system:px-lh-account
        oc adm policy add-scc-to-user anyuid system:serviceaccount:kube-system:px-lh-account
        oc adm policy add-scc-to-user anyuid system:serviceaccount:default:default
        oc adm policy add-scc-to-user privileged system:serviceaccount:kube-system:px-csi-account
        """
        list = ["px-account","portworx-pvc-controller-account","px-lh-account","px-csi-account"]
        oc_adm_cmd = "oc adm policy add-scc-to-user privileged system:serviceaccount:kube-system:"
        for scc in list:
            cmd = oc_adm_cmd+scc
            TR.info(methodName,"Run get_nodes command %s"%cmd)
            try:
                retcode = check_output(['bash','-c', cmd]) 
                TR.info(methodName,"Completed %s command with return value %s" %(cmd,retcode))
            except CalledProcessError as e:
                TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        cmd = "oc adm policy add-scc-to-user anyuid system:serviceaccount:default:default"
        try:
            retcode = check_output(['bash','-c', cmd])
            TR.info(methodName,"Completed %s command with return value %s" %(cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        cmd = "oc adm policy add-scc-to-user anyuid system:serviceaccount:kube-system:px-lh-account"
        try:
            retcode = check_output(['bash','-c', cmd]) 
            TR.info(methodName,"Completed %s command with return value %s" %(cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        TR.info(methodName,"Done Updating SCC for Portworx Installation")
    #endDef    

    def labelNodes(self,icpdInstallLogFile):
        methodName = "labelNodes"
        TR.info(methodName,"  Start Label nodes for Portworx Installation")
        """
        WORKER_NODES=`oc get nodes | grep worker | awk '{print $1}'`
        for wnode in ${WORKER_NODES[@]}; do
        oc label nodes $wnode node-role.kubernetes.io/compute=true
        done
        """

        get_nodes = "oc get nodes | grep worker | awk '{print $1}'"
        TR.info(methodName,"Run get_nodes command %s"%get_nodes)
        try:
            worker_nodes = check_output(['bash','-c', get_nodes]) 
            TR.info(methodName,"Completed %s command with return value %s" %(get_nodes,worker_nodes))
            nodes = worker_nodes.split("\n")
            TR.info(methodName,"worker nodes %s"%nodes)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        i =0
        while i < len(nodes)-1:
            TR.info(methodName,"Labeling for worker node  %s " %nodes[i])
            label_cmd = "oc label nodes "+nodes[i]+" node-role.kubernetes.io/compute=true"
            try:
                retcode = check_output(['bash','-c', label_cmd])
                TR.info(methodName,"Label for Worker node  %s returned %s" %(nodes[i],retcode))
            except CalledProcessError as e:
                TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
            i += 1

        TR.info(methodName,"Done Label nodes for Portworx Installation")
        
    #endDef

    def setpxVolumePermission(self,icpdInstallLogFile):
        """
        This method sets delete of termination permission to the volumes created by portworx on the worker nodes.
        """
        methodName = "setpxVolumePermission"
        TR.info(methodName,"Start setpxVolumePermission")
        """
        WORKER_INSTANCE_ID=`aws ec2 describe-instances --filters 'Name=tag:Name,Values=*worker*' --output text --query 'Reservations[*].Instances[*].InstanceId'`
        DEVICE_NAME=`aws ec2 describe-instances --filters 'Name=tag:Name,Values=*worker*' --output text --query 'Reservations[*].Instances[*].BlockDeviceMappings[*].DeviceName' | uniq`
        for winstance in ${WORKER_INSTANCE_ID[@]}; do
        for device in ${DEVICE_NAME[@]}; do
        aws ec2 modify-instance-attribute --instance-id $winstance --block-device-mappings "[{\"DeviceName\": \"$device\",\"Ebs\":{\"DeleteOnTermination\":true}}]"
        done
        done
        """
        tag_value=self.clusterID+"-worker*"
        response = self.ec2.describe_instances(Filters=[{'Name': 'tag:Name','Values': [tag_value,]}])
        reservation = response['Reservations']
        for item in reservation:
            instances = item['Instances']
            for instance in instances:
                deviceMappings = instance['BlockDeviceMappings']
                for device in deviceMappings:
                    resp = self.ec2.modify_instance_attribute(InstanceId=instance['InstanceId'],BlockDeviceMappings=[{'DeviceName': device['DeviceName'],'Ebs': {'DeleteOnTermination': True}}])
                    TR.info(methodName,"Modified instance attribute for instance %s device name %s returned %s"%(instance['InstanceId'],device['DeviceName'],resp))
                #endFor
            #endFor
        #endFor
        TR.info(methodName,"Completed setpxVolumePermission")    
    #endDef    

    def configurePx(self, icpdInstallLogFile):
        methodName = "configurePx"
        TR.info(methodName,"  Start configuration of Portworx for CPD")
        default_route = "oc get route default-route -n openshift-image-registry --template='{{ .spec.host }}'"
        TR.info(methodName,"Get default route  %s"%default_route)
        try:
            self.ocr = check_output(['bash','-c', default_route]) 
            TR.info(methodName,"Completed %s command with return value %s" %(default_route,self.ocr))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        create_secret_cmd = "oc create secret docker-registry regcred --docker-server="+self.ocr+"  --docker-username=kubeadmin --docker-password="+self.ocpassword+" -n kube-system"
        TR.info(methodName,"Create OC secret for PX installation  %s"%create_secret_cmd)
        try:
            retcode = check_output(['bash','-c', create_secret_cmd]) 
            TR.info(methodName,"Completed %s command with return value %s" %(create_secret_cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        self.preparePXInstall(icpdInstallLogFile)
        time.sleep(30)
        self.updateScc(icpdInstallLogFile)
        time.sleep(30)
        self.labelNodes(icpdInstallLogFile)
        time.sleep(30)
        label_cmd = "oc get nodes --show-labels  | grep 'node-role.kubernetes.io/compute=true'"
        TR.info(methodName,"Run label_cmd command %s"%label_cmd)
        try:
            retcode = check_output(['bash','-c', label_cmd]) 
            TR.info(methodName,"Completed %s command with return value %s" %(label_cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        time.sleep(30)
        px_install_cmd = "oc apply -f /ibm/templates/px/px-install.yaml"
        TR.info(methodName,"Run px-install command %s"%px_install_cmd)
        try:
            retcode = check_output(['bash','-c', px_install_cmd]) 
            TR.info(methodName,"Completed %s command with return value %s" %(px_install_cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        time.sleep(180)
        
        px_spec_cmd = "oc create -f /ibm/templates/px/px-spec.yaml"
        TR.info(methodName,"Run px-spec command %s"%px_spec_cmd)
        try:
            retcode = check_output(['bash','-c', px_spec_cmd]) 
            TR.info(methodName,"Completed %s command with return value %s" %(px_spec_cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        time.sleep(300)

        create_px_sc = "oc create -f /ibm/templates/px/px-storageclasses.yaml"
        TR.info(methodName,"Run px sc command %s"%create_px_sc)
        try:
            retcode = check_output(['bash','-c', create_px_sc]) 
            TR.info(methodName,"Completed %s command with return value %s" %(create_px_sc,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        
        self.setpxVolumePermission(icpdInstallLogFile)

        TR.info(methodName,"Configuration of Portworx for CPD completed")
    #endDef    

    def installOCP(self, icpdInstallLogFile):
        methodName = "installOCP"
        TR.info(methodName,"  Start installation of Openshift Container Platform")

        installConfigFile = "/ibm/installDir/install-config.yaml"
        autoScalerFile = "/ibm/templates/cpd/machine-autoscaler.yaml"
        healthcheckFile = "/ibm/templates/cpd/health-check.yaml"

        
        icf_1az = "/ibm/installDir/install-config-1AZ.yaml"
        icf_3az = "/ibm/installDir/install-config-3AZ.yaml"
        
        asf_1az = "/ibm/templates/cpd/machine-autoscaler-1AZ.yaml"
        asf_3az = "/ibm/templates/cpd/machine-autoscaler-3AZ.yaml"
        
        hc_1az = "/ibm/templates/cpd/health-check-1AZ.yaml"
        hc_3az = "/ibm/templates/cpd/health-check-3AZ.yaml"

        if(len(self.zones)==1):
            shutil.copyfile(icf_1az,installConfigFile)
            shutil.copyfile(asf_1az,autoScalerFile)
            shutil.copyfile(hc_1az, healthcheckFile)
        else:
            shutil.copyfile(icf_3az,installConfigFile)
            shutil.copyfile(asf_3az,autoScalerFile)
            shutil.copyfile(hc_3az, healthcheckFile)
        

        self.updateTemplateFile(installConfigFile,'${az1}',self.zones[0])
        self.updateTemplateFile(installConfigFile,'${baseDomain}',self.DomainName)
        self.updateTemplateFile(installConfigFile,'${master-instance-type}',self.MasterInstanceType)
        self.updateTemplateFile(installConfigFile,'${worker-instance-type}',self.ComputeInstanceType)
        self.updateTemplateFile(installConfigFile,'${worker-instance-count}',self.NumberOfCompute)
        self.updateTemplateFile(installConfigFile,'${master-instance-count}',self.NumberOfMaster)
        self.updateTemplateFile(installConfigFile,'${region}',self.region)
        self.updateTemplateFile(installConfigFile,'${subnet-1}',self.PrivateSubnet1ID)
        self.updateTemplateFile(installConfigFile,'${subnet-2}',self.PublicSubnet1ID)
        self.updateTemplateFile(installConfigFile,'${pullSecret}',self.readFileContent(self.pullSecret))
        self.updateTemplateFile(installConfigFile,'${sshKey}',self.readFileContent("/root/.ssh/id_rsa.pub"))
        self.updateTemplateFile(installConfigFile,'${clustername}',self.ClusterName)
        self.updateTemplateFile(installConfigFile, '${FIPS}',self.EnableFips)
        self.updateTemplateFile(installConfigFile, '${machine-cidr}', self.VPCCIDR)
        self.updateTemplateFile(autoScalerFile, '${az1}', self.zones[0])
        self.updateTemplateFile(healthcheckFile, '${az1}', self.zones[0])


        if(len(self.zones)>1):
            self.updateTemplateFile(installConfigFile,'${az2}',self.zones[1])
            self.updateTemplateFile(installConfigFile,'${az3}',self.zones[2])
            self.updateTemplateFile(installConfigFile,'${subnet-3}',self.PrivateSubnet2ID)
            self.updateTemplateFile(installConfigFile,'${subnet-4}',self.PrivateSubnet3ID)
            self.updateTemplateFile(installConfigFile,'${subnet-5}',self.PublicSubnet2ID)
            self.updateTemplateFile(installConfigFile,'${subnet-6}',self.PublicSubnet3ID)

            self.updateTemplateFile(autoScalerFile, '${az2}', self.zones[1])
            self.updateTemplateFile(autoScalerFile, '${az3}', self.zones[2])
            self.updateTemplateFile(healthcheckFile, '${az2}', self.zones[1])
            self.updateTemplateFile(healthcheckFile, '${az3}', self.zones[2])
        
        TR.info(methodName,"Download Openshift Container Platform")
        self.getS3Object(bucket=self.cpdbucketName, s3Path="3.0/openshift-install", destPath="/ibm/openshift-install")
        self.getS3Object(bucket=self.cpdbucketName, s3Path="3.0/oc", destPath="/usr/bin/oc")
        self.getS3Object(bucket=self.cpdbucketName, s3Path="3.0/kubectl", destPath="/usr/bin/kubectl")
        os.chmod("/usr/bin/oc", stat.S_IEXEC)
        os.chmod("/usr/bin/kubectl", stat.S_IEXEC)	
        TR.info(methodName,"Initiating installation of Openshift Container Platform")
        os.chmod("/ibm/openshift-install", stat.S_IEXEC)
        install_ocp = "sudo ./openshift-install create cluster --dir=/ibm/installDir --log-level=debug"
        TR.info(methodName,"Output File name: %s"%icpdInstallLogFile)
        try:
            process = Popen(install_ocp,shell=True,stdout=icpdInstallLogFile,stderr=icpdInstallLogFile,close_fds=True)
            stdoutdata,stderrdata=process.communicate()
        except CalledProcessError as e:
            TR.error(methodName, "ERROR return code: %s, Exception: %s" % (e.returncode, e), e)
            raise e    
        TR.info(methodName,"Installation of Openshift Container Platform %s %s" %(stdoutdata,stderrdata))
        time.sleep(30)
        destDir = "/root/.kube"
        if (not os.path.exists(destDir)):
            os.makedirs(destDir)
        shutil.copyfile("/ibm/installDir/auth/kubeconfig","/root/.kube/config")
        
        self.ocpassword = self.readFileContent("/ibm/installDir/auth/kubeadmin-password").rstrip("\n\r")
        self.logincmd = "oc login -u kubeadmin -p "+self.ocpassword
        try:
            call(self.logincmd, shell=True,stdout=icpdInstallLogFile)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        
        get_clusterId = r"oc get machineset -n openshift-machine-api -o jsonpath='{.items[0].metadata.labels.machine\.openshift\.io/cluster-api-cluster}'"
        TR.info(methodName,"get_clusterId %s"%get_clusterId)
        try:
            self.clusterID = check_output(['bash','-c',get_clusterId])
            TR.info(methodName,"self.clusterID %s"%self.clusterID)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        
        self.updateTemplateFile(autoScalerFile, 'CLUSTERID', self.clusterID)
        create_machine_as_cmd = "oc create -f "+autoScalerFile
        TR.info(methodName,"Create of Machine auto scaler")
        try:
            retcode = check_output(['bash','-c', create_machine_as_cmd]) 
            TR.info(methodName,"Created Machine auto scaler %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        self.updateTemplateFile(healthcheckFile, 'CLUSTERID', self.clusterID)
        create_healthcheck_cmd = "oc create -f "+healthcheckFile
        TR.info(methodName,"Create of Health check")
        try:
            retcode = check_output(['bash','-c', create_healthcheck_cmd]) 
            TR.info(methodName,"Created Health check %s" %retcode)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        TR.info(methodName,"Create OCP registry")

        registry_mc = "/ibm/templates/cpd/insecure-registry.yaml"
        registries  = "/ibm/templates/cpd/registries.conf"
        crio_conf   = "/ibm/templates/cpd/crio.conf"
        crio_mc     = "/ibm/templates/cpd/crio-mc.yaml"
        
        route = "default-route-openshift-image-registry.apps."+self.ClusterName+"."+self.DomainName
        self.updateTemplateFile(registries, '${registry-route}', route)
        
        config_data = base64.b64encode(self.readFileContent(registries))
        self.updateTemplateFile(registry_mc, '${config-data}', config_data)
        
        crio_config_data = base64.b64encode(self.readFileContent(crio_conf))
        self.updateTemplateFile(crio_mc, '${crio-config-data}', crio_config_data)

        route_cmd = "oc patch configs.imageregistry.operator.openshift.io/cluster --type merge -p '{\"spec\":{\"defaultRoute\":true,\"replicas\":"+self.NumberOfAZs+"}}'"
        TR.info(methodName,"Creating route with command %s"%route_cmd)
        try:
            retcode = check_output(['bash','-c', route_cmd]) 
            TR.info(methodName,"Created route with command %s returned %s"%(route_cmd,retcode))
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        destDir = "/etc/containers/"
        if (not os.path.exists(destDir)):
            os.makedirs(destDir)
        shutil.copyfile(registries,"/etc/containers/registries.conf")
        create_registry = "oc create -f "+registry_mc
        create_crio_mc  = "oc create -f "+crio_mc

        TR.info(methodName,"Creating registry mc with command %s"%create_registry)
        try:
            reg_retcode = check_output(['bash','-c', create_registry]) 
            TR.info(methodName,"Creating crio mc with command %s"%create_crio_mc)
            
            crio_retcode = check_output(['bash','-c', create_crio_mc]) 
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        TR.info(methodName,"Created regsitry with command %s returned %s"%(create_registry,reg_retcode))
        TR.info(methodName,"Created Crio mc with command %s returned %s"%(create_crio_mc,crio_retcode))
        
        create_cluster_as_cmd = "oc create -f /ibm/templates/cpd/cluster-autoscaler.yaml"
        TR.info(methodName,"Create of Cluster auto scaler")
        try:
            retcode = check_output(['bash','-c', create_cluster_as_cmd]) 
            TR.info(methodName,"Created Cluster auto scaler %s" %retcode)    
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
        """
        "oc create -f ${local.ocptemplates}/wkc-sysctl-mc.yaml",
        "oc create -f ${local.ocptemplates}/security-limits-mc.yaml",
        """
        sysctl_cmd =  "oc create -f /ibm/templates/cpd/wkc-sysctl-mc.yaml"
        TR.info(methodName,"Create SystemCtl Machine config")
        try:
            retcode = check_output(['bash','-c', sysctl_cmd]) 
            TR.info(methodName,"Created  SystemCtl Machine config %s" %retcode) 
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        secLimits_cmd =  "oc create -f /ibm/templates/cpd/security-limits-mc.yaml"
        TR.info(methodName,"Create Security Limits Machine config")
        try:
            retcode = check_output(['bash','-c', secLimits_cmd]) 
            TR.info(methodName,"Created  Security Limits Machine config %s" %retcode)  
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))  
        time.sleep(600)

        oc_route_cmd = "oc get route console -n openshift-console | grep 'console' | awk '{print $2}'"
        TR.info(methodName, "Get OC URL")
        try:
            self.openshiftURL = check_output(['bash','-c', oc_route_cmd]) 
            TR.info(methodName, "OC URL retrieved %s"%self.openshiftURL)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    

        TR.info(methodName,"  Completed installation of Openshift Container Platform")
    #endDef   

    def __init(self, stackId, stackName, icpdInstallLogFile):
        methodName = "_init"
        global StackParameters, StackParameterNames
        boto3.setup_default_session(region_name=self.region)
        self.cfnResource = boto3.resource('cloudformation', region_name=self.region)
        self.cf = boto3.client('cloudformation', region_name=self.region)
        self.ec2 = boto3.client('ec2', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        self.iam = boto3.client('iam',region_name=self.region)
        self.secretsmanager = boto3.client('secretsmanager', region_name=self.region)
        self.ssm = boto3.client('ssm', region_name=self.region)

        StackParameters = self.getStackParameters(stackId)
        StackParameterNames = StackParameters.keys()
        TR.info(methodName,"self.stackParameters %s" % StackParameters)
        TR.info(methodName,"self.stackParameterNames %s" % StackParameterNames)
        self.logExporter = LogExporter(region=self.region,
                            bucket=self.ICPDDeploymentLogsBucketName,
                            keyPrefix=stackName,
                            fqdn=socket.getfqdn()
                            )                    
        TR.info(methodName,"Create ssh keys")
        command = "ssh-keygen -P {}  -f /root/.ssh/id_rsa".format("''")
        try:
            call(command,shell=True,stdout=icpdInstallLogFile)
            TR.info(methodName,"Created ssh keys")
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))    
    
    def getSecret(self, icpdInstallLogFile):
        methodName = "getSecret"
        TR.info(methodName,"Start Get secrets %s"%self.cpdSecret)
        get_secret_value_response = self.secretsmanager.get_secret_value(SecretId=self.cpdSecret)
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            secretDict = json.loads(secret)
            #TR.info(methodName,"Secret %s"%secret)
            self.password = secretDict['adminPassword']
            #TR.info(methodName,"password %s"%self.password)
            self.apiKey = secretDict['apikey']
            #TR.info(methodName,"apiKey %s"%self.apiKey)
        TR.info(methodName,"End Get secrets")
    #endDef    

    def updateSecret(self, icpdInstallLogFile):
        methodName = "updateSecret"
        TR.info(methodName,"Start updateSecret %s"%self.ocpSecret)
        secret_update = '{"ocpPassword":'+self.ocpassword+'}'
        response = self.secretsmanager.update_secret(SecretId=self.ocpSecret,SecretString=secret_update)
        TR.info(methodName,"Updated secret for %s with response %s"%(self.ocpSecret, response))
        TR.info(methodName,"End updateSecret")
    #endDef
    #     
    def exportResults(self, name, parameterValue ,icpdInstallLogFile):
        methodName = "exportResults"
        TR.info(methodName,"Start export results")
        self.ssm.put_parameter(Name=name,
                           Value=parameterValue,
                           Type='String',
                           Overwrite=True)
        TR.info(methodName,"Value: %s put to: %s." % (parameterValue,name))
    #endDef    
    def main(self,argv):
        methodName = "main"
        self.rc = 0
        try:
            beginTime = Utilities.currentTimeMillis()
            cmdLineArgs = Utilities.getInputArgs(self.ArgsSignature,argv[1:])
            trace, logFile = self._configureTraceAndLogging(cmdLineArgs)
            self.region = cmdLineArgs.get('region')
            if (logFile):
                TR.appendTraceLog(logFile)   
            if (trace):
                TR.info(methodName,"Tracing with specification: '%s' to log file: '%s'" % (trace,logFile))

            logFilePath = os.path.join(self.logsHome,"icpd_install.log")
    
            with open(logFilePath,"a+") as icpdInstallLogFile:  
                self.stackId = cmdLineArgs.get('stackid')
                self.stackName = cmdLineArgs.get('stack-name')
                self.amiID = environ.get('AMI_ID')
                self.cpdSecret = environ.get('CPD_SECRET')
                self.ocpSecret = environ.get('OCP_SECRET')
                self.cpdbucketName = environ.get('ICPDArchiveBucket')
                self.ICPDInstallationCompletedURL = environ.get('ICPDInstallationCompletedURL')
                TR.info(methodName, "amiID %s "% self.amiID)
                TR.info(methodName, "cpdbucketName %s "% self.cpdbucketName)
                TR.info(methodName, "ICPDInstallationCompletedURL %s "% self.ICPDInstallationCompletedURL)
                TR.info(methodName, "cpdSecret %s "% self.cpdSecret)
                TR.info(methodName, "ocpSecret %s "% self.ocpSecret)
                self.__init(self.stackId,self.stackName, icpdInstallLogFile)
                self.zones = Utilities.splitString(self.AvailabilityZones)
                TR.info(methodName," AZ values %s" % self.zones)
                TR.info(methodName,"RedhatPullSecret %s" %self.RedhatPullSecret)
               
                secret = self.RedhatPullSecret.split('/',1)
                TR.info(methodName,"Pull secret  %s" %secret)  
                self.pullSecret = "/ibm/pull-secret"
                #self.getS3Object(bucket=secret[0], s3Path=secret[1], destPath=self.pullSecret)
                s3_cp_cmd = "aws s3 cp "+self.RedhatPullSecret+" "+self.pullSecret
                TR.info(methodName,"s3 cp cmd %s"%s3_cp_cmd)
                call(s3_cp_cmd, shell=True,stdout=icpdInstallLogFile)
                self.getSecret(icpdInstallLogFile)
                
                ocpstart = Utilities.currentTimeMillis()
                self.installOCP(icpdInstallLogFile)
                ocpend = Utilities.currentTimeMillis()
                self.printTime(ocpstart, ocpend, "Installing OCP")

                self.installWKC = Utilities.toBoolean(self.WKC)
                self.installWSL = Utilities.toBoolean(self.WSL)
                self.installDV = Utilities.toBoolean(self.DV)
                self.installWML = Utilities.toBoolean(self.WML)
                self.installOSWML = Utilities.toBoolean(self.OpenScale)
                self.installCDE = Utilities.toBoolean(self.CDE)
                self.installSpark= Utilities.toBoolean(self.Spark)
                #self.EnableFips = Utilities.toBoolean(self.EnableFips)

                if(self.installOSWML):
                    self.installWML=True

                
                storagestart = Utilities.currentTimeMillis()
                if(self.StorageType=='OCS'):
                    self.configureOCS(icpdInstallLogFile)
                elif(self.StorageType=='Portworx'):
                    TR.info(methodName,"PortworxSpec %s" %self.PortworxSpec)
                    spec = self.PortworxSpec.split('/',1)
                    TR.info(methodName,"spec  %s" %spec)
                    self.spec = "/ibm/templates/px/px-spec.yaml"
                    #self.getS3Object(bucket=spec[0], s3Path=spec[1], destPath=self.spec)
                    s3_cp_cmd = "aws s3 cp "+self.PortworxSpec+" "+self.spec
                    TR.info(methodName,"s3 cp cmd %s"%s3_cp_cmd)
                    call(s3_cp_cmd, shell=True,stdout=icpdInstallLogFile)
                    self.configurePx(icpdInstallLogFile)
                elif(self.StorageType=='EFS'):
                    self.EFSDNSName = environ.get('EFSDNSName')
                    self.EFSID = environ.get('EFSID')   
                    self.configureEFS()

                storageend = Utilities.currentTimeMillis()
                self.printTime(storagestart, storageend, "Installing storage")    

                self.installCPD(icpdInstallLogFile)
                self.validateInstall(icpdInstallLogFile)
                self.manageUser(icpdInstallLogFile)
                self.updateSecret(icpdInstallLogFile)
                self.exportResults(self.stackName+"-OpenshiftURL", "https://"+self.openshiftURL, icpdInstallLogFile)
                self.exportResults(self.stackName+"-CPDURL", "https://"+self.cpdURL, icpdInstallLogFile)
            #endWith    
            
        except Exception as e:
            TR.error(methodName,"Exception with message %s" %e)
            self.rc = 1
        finally:
            try:
            # Copy icpHome/logs to the S3 bucket for logs.
                self.logExporter.exportLogs("/var/log/")
                self.logExporter.exportLogs("/ibm/cpd-linux-workspace/Logs")
                self.logExporter.exportLogs("%s" % self.logsHome)
            except Exception as  e:
                TR.error(methodName,"ERROR: %s" % e, e)
                self.rc = 1
            #endTry          
        endTime = Utilities.currentTimeMillis()
        elapsedTime = (endTime - beginTime)/1000
        etm, ets = divmod(elapsedTime,60)
        eth, etm = divmod(etm,60) 

        if (self.rc == 0):
            success = 'true'
            status = 'SUCCESS'
            TR.info(methodName,"SUCCESS END CPD Install AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
            # TODO update this later
            self.updateStatus(status)
        else:
            success = 'false'
            status = 'FAILURE: Check logs in S3 log bucket or on the Boot node EC2 instance in /ibm/logs/icpd_install.log and /ibm/logs/post_install.log'
            TR.info(methodName,"FAILED END CPD Install AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
            # # TODO update this later
            self.updateStatus(status)
           
        #endIf 
        try:
            data = "%s: IBM Cloud Pak installation elapsed time: %d:%02d:%02d" % (status,eth,etm,ets)    
            check_call(['cfn-signal', 
                            '--success', success, 
                            '--id', self.stackId, 
                            '--reason', status, 
                            '--data', data, 
                            self.ICPDInstallationCompletedURL
                            ])     
        except CalledProcessError as e:
            TR.error(methodName, "ERROR return code: %s, Exception: %s" % (e.returncode, e), e)
            raise e                                                
    #end Def    
#endClass
if __name__ == '__main__':
  mainInstance = CPDInstall()
  mainInstance.main(sys.argv)
#endIf