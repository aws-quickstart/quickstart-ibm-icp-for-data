#!/bin/bash


##### "Main" starts here
SCRIPT=${0##*/}

echo $SCRIPT
source ${P}
qs_enable_epel &> /var/log/userdata.qs_enable_epel.log
yum -y install jq
qs_retry_command 10 pip install boto3 &> /var/log/userdata.boto3_install.log


cd /tmp
qs_retry_command 10 wget https://s3-us-west-1.amazonaws.com/amazon-ssm-us-west-1/latest/linux_amd64/amazon-ssm-agent.rpm
qs_retry_command 10 yum install -y ./amazon-ssm-agent.rpm
systemctl start amazon-ssm-agent
systemctl enable amazon-ssm-agent
rm -f ./amazon-ssm-agent.rpm
cd -

aws s3 cp  ${CPD_QS_S3URI}scripts/  /ibm/ --recursive
cd /ibm
# Make sure there is a "logs" directory in the current directory
if [ ! -d "${PWD}/logs" ]; then
  mkdir logs
  rc=$?
  if [ "$rc" != "0" ]; then
    # Not sure why this would ever happen, but...
    # Have to echo here since trace log is not set yet.
    echo "Creating ${PWD}/logs directory failed.  Exiting..."
    exit 1
  fi
fi

LOGFILE="${PWD}/logs/${SCRIPT%.*}.log"


mkdir -p artifacts
mkdir -p  templates
chmod +x /ibm/cpd_install.py
chmod +x /ibm/destroy.sh
echo $HOME
export KUBECONFIG=/root/.kube/config
echo $KUBECONFIG
echo $PATH
/ibm/cpd_install.py --region "${AWS_REGION}" --stackid "${AWS_STACKID}" --stack-name ${AWS_STACKNAME} --logfile $LOGFILE --loglevel "*=all"