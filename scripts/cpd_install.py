#!/usr/bin/python
import sys, os.path, time, stat, socket
import boto3
import shutil
import requests
import yapl.Utilities as Utilities
from subprocess import call,check_output, check_call, CalledProcessError
from os import chmod
from botocore.exceptions import ClientError
from yapl.Trace import Trace, Level
from yapl.AWSConfigureEFS import ConfigureEFS
from yapl.LogExporter import LogExporter
from yapl.Exceptions import MissingArgumentException

TR = Trace(__name__)
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

    def configureEFS(self):
        """
        Configure an EFS volume and configure all worker nodes to be able to use 
        the EFS storage provisioner.
        """
        methodName = "configureEFS"
        
        TR.info(methodName,"STARTED configuration of EFS on all worker nodes")
        
        # Configure EFS storage on all of the worker nodes.
        playbookPath = os.path.join(self.home,"playbooks","configure-efs-mount.yaml")
        varTemplatePath = os.path.join(self.home,"playbooks","efs-var-template.yaml")
        manifestTemplatePath = os.path.join(self.home,"config","efs","manifest-template.yaml")
        rbacTemplatePath = os.path.join(self.home,"config","efs","rbac-template.yaml")
        serviceAccountPath = os.path.join(self.home,"config","efs","service-account.yaml")

        TR.info(methodName,"Invoking: oc project default")
    
        retcode = call(["oc", "project", "default"])
        if (retcode != 0):
            raise Exception("Error calling oc. Return code: %s" % retcode)
        #endIf

        TR.info(methodName,"Configure EFS")

        
        configEFS = ConfigureEFS(region=self.region,
                                stackId=self.stackId,
                                playbookPath=playbookPath,
                                varTemplatePath=varTemplatePath,
                                manifestTemplatePath=manifestTemplatePath,
                                rbacTemplatePath=rbacTemplatePath,
                                serviceAccountPath=serviceAccountPath)
        configEFS.configureEFS()
        TR.info(methodName,"COMPLETED configuration of EFS on all worker nodes.")
      
    #endDef   
    def installCPD(self,icpdInstallLogFile):
        """
        Installs pre-requsites for cpd installation by running mkfifo and install-sem playbooks
        prepares oc cluster with required user and roles
        copies certificates from node instance to ansible server and configures internal docker registry to push images
        creates a OC project with user defined name
        Downloads binary file from S3 and extracts it to /ibm folder
        installs wkc wml and wsl package by pushing images to local registry and using local registry.

        """

        methodName = "installCPD"
        check_cmd = "checkmodule -M -m -o mkfifo.mod mkfifo.te"
        call(check_cmd,shell=True, stdout=icpdInstallLogFile)

        package_cmd = "semodule_package -o mkfifo.pp -m mkfifo.mod"
        call(package_cmd,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"ansible-playbook: install-mkfifo.yaml started, find log here %s" % (os.path.join(self.logsHome,"install-mkfifo.log")))
        
        retcode = call('ansible-playbook /ibm/playbooks/install-mkfifo.yaml >> %s 2>&1' %(os.path.join(self.logsHome,"install-mkfifo.log")), shell=True, stdout=icpdInstallLogFile)
        if (retcode != 0):
            TR.error(methodName,"Error calling ansible-playbook install-mkfifo.yaml. Return code: %s" % retcode)
            raise Exception("Error calling ansible-playbook install-mkfifo.yaml. Return code: %s" % retcode)
        else:
            TR.info(methodName,"ansible-playbook: install-mkfifo.yaml completed.")
        
        retcode = call('ansible-playbook /ibm/playbooks/install-sem.yaml >> %s 2>&1' %(os.path.join(self.logsHome,"install-sem.log")), shell=True, stdout=icpdInstallLogFile)
        if (retcode != 0):
            TR.error(methodName,"Error calling ansible-playbook install-sem.yaml. Return code: %s" % retcode)
            raise Exception("Error calling ansible-playbook install-sem.yaml. Return code: %s" % retcode)
        else:
            TR.info(methodName,"ansible-playbook:install-sem.yaml completed.")

        retlogin = check_output(['bash','-c', 'oc login -u system:admin'])
        TR.info(methodName,"Logged in as system:admin with retcode %s" % retlogin)

        retproj = check_output(['bash','-c', 'oc project default'])
        TR.info(methodName,"Switched to default project %s" % retproj)
        
        registry_cmd = "oc get route | grep 'docker-registry'| awk {'print $2'}"
        registry_url = check_output(['bash','-c', registry_cmd]).rstrip("\n\r")
        TR.info(methodName,"Get url from docker-registry route %s" % registry_url)
        
        self.docker_registry = registry_url+":443/"+self.namespace
        TR.info(methodName," registry url %s" % self.docker_registry)

        retcode = call('oc adm policy add-cluster-role-to-user cluster-admin admin',shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Added cluster admin role to admin user %s"%retcode)

        oc_login = "oc login -u admin -p "+self.getPassword()
        retcode = call(oc_login,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Log in to OC with admin user %s"%retcode)

        oc_new_project ="oc new-project "+self.namespace
        retcode = call(oc_new_project,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Create new project with user defined project name %s,retcode=%s" %(self.namespace,retcode))

        nodeIP = self.getNodeIP()
        add_to_hosts = "echo "+nodeIP+" "+registry_url+" >> /etc/hosts"
        retcode = call(add_to_hosts,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"add entry to host file %s"%add_to_hosts)

        copycerts = "scp -r root@"+nodeIP+":/etc/docker/certs.d/docker-registry.default.svc:5000 /etc/docker/certs.d/"+registry_url+":443"
        retcode = call(copycerts,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Copy certs from compute node %s"%retcode)

        self.token = self.getToken(icpdInstallLogFile)
        # self.updateTemplateFile('/ibm/local_repo.yaml', '<REGISTRYURL>', self.docker_registry)
        # self.updateTemplateFile('/ibm/local_repo.yaml', '<PASSWORD>', self.token)
        # TR.info(methodName,"Update local repo file with sa token")

        # TR.info(methodName,"Download install package from S3 bucket %s" %self.cpdbucketName)
        # s3start =Utilities.currentTimeMillis()    
        # self.getS3Object(bucket=self.cpdbucketName, s3Path="2.5/cpd.tar", destPath='/tmp/cpd.tar')
        # s3end = Utilities.currentTimeMillis()
        # TR.info(methodName,"Downloaded install package from S3 bucket %s" %self.cpdbucketName)
        # self.printTime(s3start,s3end, "S3 download of cpd tar")

        # TR.info(methodName,"Extract install package")
        # call('tar -xvf /tmp/cpd.tar -C /ibm/',shell=True, stdout=icpdInstallLogFile)
        # extractend = Utilities.currentTimeMillis()
        # TR.info(methodName,"Extracted install package")
        # self.printTime(s3end, extractend, "Extracting cpd tar")
        litestart = Utilities.currentTimeMillis()
        TR.info(methodName,"Start installing Lite package")
        self.installAssemblies("lite","v2.5.0.0",icpdInstallLogFile)
        liteend = Utilities.currentTimeMillis()
        self.printTime(litestart, liteend, "Installing Lite")
        self.configureCPDRoute(icpdInstallLogFile)


        if(self.installWSL):
            TR.info(methodName,"Start installing WSL package")
            wslstart = Utilities.currentTimeMillis()
            self.installAssemblies("wsl","2.1.0",icpdInstallLogFile)
            wslend = Utilities.currentTimeMillis()
            TR.info(methodName,"WSL package installation completed")
            self.printTime(wslstart, wslend, "Installing WSL")

        if(self.installDV):
            TR.info(methodName,"Start installing DV package")
            TR.info(methodName,"Delete configmap node-config-compute-infra")
            delete_cm = "oc delete configmap -n openshift-node node-config-compute-infra"
            retcode = check_output(['bash','-c', delete_cm]) 
            TR.info(methodName,"Deleted configmap node-config-compute-infra %s" %retcode)
            TR.info(methodName,"Create configmap node-config-compute-infra")
            create_cm = "oc create -f /ibm/node-config-compute-infra.yaml"
            retcode = check_output(['bash','-c', create_cm]) 
            TR.info(methodName,"Created configmap node-config-compute-infra %s" %retcode)
            dvstart = Utilities.currentTimeMillis()
            self.installAssemblies("dv","v1.3.0.0",icpdInstallLogFile)
            dvend = Utilities.currentTimeMillis()
            TR.info(methodName,"DV package installation completed")
            self.printTime(dvstart, dvend, "Installing DV")
        
        if(self.installWML):
            TR.info(methodName,"Start installing WML package")
            wmlstart = Utilities.currentTimeMillis()
            self.installAssemblies("wml","2.1.0.0",icpdInstallLogFile)
            wmlend = Utilities.currentTimeMillis()
            TR.info(methodName,"WML package installation completed")
            self.printTime(wmlstart, wmlend, "Installing WML")
        
        if(self.installWKC):
            TR.info(methodName,"Start installing WKC package")
            wkcstart = Utilities.currentTimeMillis()
            self.installAssemblies("wkc","3.0.333",icpdInstallLogFile)
            wkcend = Utilities.currentTimeMillis()
            TR.info(methodName,"WKC package installation completed")
            self.printTime(wkcstart, wkcend, "Installing WKC")

        if(self.installOSWML):
            TR.info(methodName,"Start installing AI Openscale package")
            aiostart = Utilities.currentTimeMillis()
            self.installAssemblies("aiopenscale","v2.5.0.0",icpdInstallLogFile)
            aioend = Utilities.currentTimeMillis()
            TR.info(methodName,"AI Openscale package installation completed")
            self.printTime(aiostart, aioend, "Installing AI Openscale")



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
        retcode = call(create_sa_cmd,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Created service account cpdtoken %s"%retcode)

        addrole_cmd = "oc policy add-role-to-user admin system:serviceaccount:"+self.namespace+":cpdtoken"
        TR.info(methodName," Add role to service account %s"%addrole_cmd)
        retcode = call(addrole_cmd,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Role added to service account %s"%retcode)

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
    def installAssemblies(self,assembly,version,icpdInstallLogFile):
        """
        method to install assemlies
        for each assembly this method will execute adm command to apply all prerequistes
        Images will be pushed to local registry
        Installation will be done for the assembly using local registry
        """
        methodName = "installAssemblies"
        
        apply_cmd = "/ibm/cpd-linux adm -r /ibm/repo.yaml -a "+assembly+"  -n "+self.namespace+" --accept-all-licenses --apply | tee /ibm/logs/"+assembly+"_apply.log"
        TR.info(methodName,"Execute apply command for assembly %s"%apply_cmd)
        retcode = call(apply_cmd,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Executed apply command for assembly %s"%retcode)
     
        install_cmd = "/ibm/cpd-linux -c aws-efs -r /ibm/repo.yaml -a "+assembly+" -n "+self.namespace+" --version="+version+" --transfer-image-to="+self.docker_registry+" --target-registry-username=unused   --target-registry-password="+self.token+ " --cluster-pull-prefix=docker-registry.default.svc:5000/"+self.namespace+" --accept-all-licenses | tee /ibm/logs/"+assembly+"_install.log"

        retcode = call(install_cmd,shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"Execute install command for assembly %s"%retcode)     

    def getPassword(self):
        """
        method to get Password value from Secrets ARN
        """
        methodName = "getPassword"
        TR.info(methodName,"describe_stack_resource to get password")
        passwordSecrets = self.cf.describe_stack_resource(StackName=self.stackName,LogicalResourceId='OpenShiftPasswordSecret')
        resourceDetail = passwordSecrets['StackResourceDetail']
        value = self.secretsmanager.get_secret_value(SecretId=resourceDetail['PhysicalResourceId'])
        self.password =  value["SecretString"]
        TR.info(methodName,"retrived password from secrets")
        return self.password

    def getContainerELBDNS(self):
        """
        method to get Container ELB DNS Name from stack resource
        """
        methodName = "getContainerELBDNS"
        TR.info(methodName,"describe_stack_resource to get containerELB")
        containerELB =  self.cf.describe_stack_resource(StackName=self.stackName,LogicalResourceId='ContainerAccessELB')
        resourceDetail = containerELB['StackResourceDetail']
        elb = self.elb.describe_load_balancers(LoadBalancerNames=[resourceDetail['PhysicalResourceId']])
        TR.info(methodName,"Retrived containerELB %s" %elb.get('LoadBalancerDescriptions')[0].get('DNSName').lower())
        return elb.get('LoadBalancerDescriptions')[0].get('DNSName').lower()

    #endDef    

    def getOutputBucket(self):
        """
        method to get Output bucket name, either user defined or autogenerated value from stack resource
        """
        methodName = "getOutputBucket"
        TR.info(methodName,"describe_stack_resource to get OutputBucket")
        bucket =  self.cf.describe_stack_resource(StackName=self.stackName,LogicalResourceId='OutputBucket')
        resourceDetail = bucket['StackResourceDetail']
        TR.info(methodName,"OutputBucket = %s"%resourceDetail['PhysicalResourceId'])
        return resourceDetail['PhysicalResourceId']
    #endDef    
    def getNodeIP(self):
        """
        method to get Node IP value of one of the compute nodes
        First obtain Compute ASG resource and then fetch the first instance from the list of instances from ASG
        """
        methodName = "getNodeIP"
        TR.info(methodName,"describe_stack_resource to get Node IP")
        nodeASG = self.cf.describe_stack_resource(StackName=self.stackName,LogicalResourceId='OpenShiftNodeASG')
        resourceDetail = nodeASG['StackResourceDetail']
        grpName = list()
        grpName.append(resourceDetail['PhysicalResourceId'])
        asgs = self.autoScaling.describe_auto_scaling_groups(AutoScalingGroupNames=grpName)['AutoScalingGroups']
        instances = asgs[0]['Instances']
        instance = self.ec2.Instance(instances[0]['InstanceId'])
        TR.info(methodName,"Retrieved instance detail %s"%instance.private_ip_address)
        return instance.private_ip_address        
#endIf

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
    def configureCPDRoute(self, icpdInstallLogFile):
        """
        method to delete existing route created with default values and update the route template with ELB DNS name
        and create route resource using the template yaml
        """
        methodName = "configureCPDRoute"
        TR.info(methodName,"Delete exists route")
        delete_cmd = 'oc delete route '+self.namespace+'-cpd'
        retcode = check_output(['bash','-c', delete_cmd]) 
        TR.info(methodName,"Delete exists route %s"%retcode)
        TR.info(methodName,"Get container DNS name")
        self.hostname = self.getContainerELBDNS()
        TR.info(methodName,"container DNS name retrieved %s"%self.hostname)

        TR.info(methodName,"Update route template with hostname")
        self.updateTemplateFile('/ibm/route.yaml','<ELB_DNSNAME>',self.hostname)
        self.updateTemplateFile('/ibm/route.yaml','<NAMESPACE>',self.namespace)
        TR.info(methodName,"Create route with template file")
        retcode = check_output(['bash','-c', 'oc create -f /ibm/route.yaml']) 
        TR.info(methodName,"Created route with template file %s"%retcode)
    #endDef    
    
    def validateInstall(self, icpdInstallLogFile):
        methodName = "validateInstall"
        count = 3
        TR.info(methodName,"Validate Installation status")
        TR.info(methodName,"Lite Count is  %s"%count)
        if(self.installDV):
            count = count+1
            TR.info(methodName,"DV Count is  %s"%count)
        if(self.installOSWML):
            count = count+1
            TR.info(methodName,"AI OS Count is  %s"%count)    
        if(self.installWKC and self.installWML and self.installWSL):
            count = count+21
            TR.info(methodName,"WKC,WML,WSL Count is  %s"%count)
        else:    
            if(self.installWSL and self.installWKC):
                count =count+19
                TR.info(methodName,"WSL,WKC Count is  %s"%count)
            elif(self.installWML and self.installWSL):
                count =count+15
                TR.info(methodName,"WML,WSL Count is  %s"%count)
            elif(self.installWML and self.installWKC):
                count =count+17
                TR.info(methodName,"WKC,WML Count is  %s"%count)
            elif(self.installWKC):
                count = count+15
                TR.info(methodName,"WKC Count is  %s"%count)
            elif(self.installWSL):
                count = count+13
                TR.info(methodName,"WSL Count is  %s"%count)
            elif(self.installWML):
                count = count+10
                TR.info(methodName,"WML Count is  %s"%count)
        

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
        manageUser = "sudo python /ibm/manage_admin_user.py "+self.namespace+" admin "+self.password
        TR.info(methodName,"Start manageUser")    
        call(manageUser, shell=True, stdout=icpdInstallLogFile)
        TR.info(methodName,"End manageUser")    
    #endDef
    #     
    def activateLicense(self, icpdInstallLogFile):
        """
        method to activate trial license for cpd installation
        """
        methodName = "activateLicense"
        #self.updateTemplateFile('/ibm/activate-license.sh','<ELB_DNSNAME>',self.hostname)
        TR.info(methodName,"Start Activate trial")
        icpdUrl = "https://"+self.hostname
        activatetrial = "sudo python /ibm/activate-trial.py "+icpdUrl+" admin "+self.password+" /ibm/trial.lic"
        try:
            call(activatetrial, shell=True, stdout=icpdInstallLogFile)
        except CalledProcessError as e:
            TR.error(methodName,"command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
        TR.info(methodName,"End Activate trial")
        TR.info(methodName,"IBM Cloud Pak for Data installation completed.")
    #endDef    

    def updateStatus(self, status):
        methodName = "updateStatus"
        TR.info(methodName," Update Status of installation")
        data = "AWS_STACKNAME="+self.stackName+",Status="+status
        updateStatus = "curl -X POST https://un6laaf4v0.execute-api.us-west-2.amazonaws.com/testtracker --data "+data
        call(updateStatus, shell=True)
        TR.info(methodName,"Updated status with data %s"%data)
    #endDef    


    def main(self,argv):
        methodName = "main"
        self.rc = 0
        params = {}
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
                self.cfnResource = boto3.resource('cloudformation', region_name=self.region)
                self.cf = boto3.client('cloudformation', region_name=self.region)
                self.ec2 = boto3.resource('ec2', region_name=self.region)
                self.s3 = boto3.client('s3', region_name=self.region)
                self.elb = boto3.client('elb',region_name=self.region)
                self.secretsmanager = boto3.client('secretsmanager', region_name=self.region)
                self.autoScaling = boto3.client('autoscaling', region_name=self.region)
                self.stackParameters = self.getStackParameters(self.stackId)
                self.stackParameterNames = self.stackParameters.keys()
            
                list = self.stackParameters.get("AnsibleAdditionalEnvironmentVariables").split(",")
                params.update((dict(item.split("=", 1) for item  in list)))
                self.namespace = params.get('Namespace')
                self.cpdbucketName = params.get('ICPDArchiveBucket')
                self.ICPDInstallationCompletedURL = params.get('ICPDInstallationCompletedURL')
                self.installWKC = Utilities.toBoolean(params.get('WKC'))
                self.installWSL = Utilities.toBoolean(params.get('WSL'))
                self.installDV = Utilities.toBoolean(params.get('DV'))
                self.installWML = Utilities.toBoolean(params.get('WML'))
                self.installOSWML = Utilities.toBoolean(params.get('OSWML'))
                if(self.installOSWML):
                    self.installWML=True
                #endIf    
                self.apikey = params.get('APIKey')
                TR.info(methodName, "Retrieve namespace value from Env Variables %s" %self.namespace)
                self.logExporter = LogExporter(region=self.region,
                                   bucket=self.getOutputBucket(),
                                   keyPrefix='logs/%s' % self.stackName,
                                   fqdn=socket.getfqdn()
                                   )  
                self.configureEFS()
                self.getS3Object(bucket=self.cpdbucketName, s3Path="2.5/cpd-linux", destPath="/ibm/cpd-linux")
                os.chmod("/ibm/cpd-linux", stat.S_IEXEC)	
                if not self.apikey:
                    TR.info(methodName, "Downloading repo.yaml from S3 bucket")
                    os.remove("/ibm/repo.yaml")
                    self.getS3Object(bucket=self.cpdbucketName, s3Path="2.5/repo.yaml", destPath="/ibm/repo.yaml")
                else:
                    TR.info(methodName, "updating repo.yaml with apikey value provided")
                    self.updateTemplateFile('/ibm/repo.yaml','<APIKEY>',self.apikey)
                self.installCPD(icpdInstallLogFile)
                self.validateInstall(icpdInstallLogFile)
                self.manageUser(icpdInstallLogFile)
                if not self.apikey:
                    self.activateLicense(icpdInstallLogFile)
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
            self.updateStatus(status)
            os.remove("/ibm/trial.lic")
            #os.remove("/ibm/repo.yaml")
        else:
            success = 'false'
            status = 'FAILURE: Check logs in S3 log bucket or on the AnsibleConfigServer node EC2 instance in /ibm/logs/icpd_install.log and /ibm/logs/post_install.log'
            TR.info(methodName,"FAILED END CPD Install AWS ICPD Quickstart.  Elapsed time (hh:mm:ss): %d:%02d:%02d" % (eth,etm,ets))
            self.updateStatus(status)
            os.remove("/ibm/trial.lic")
            #os.remove("/ibm/repo.yaml")
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