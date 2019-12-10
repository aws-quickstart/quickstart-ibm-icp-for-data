#!/bin/bash


##### "Main" starts here
SCRIPT=${0##*/}

echo $SCRIPT

aws s3 cp  ${CPD_QS_S3URI}scripts/  /ibm/ --recursive
mv /ibm/scaler.py /root/ose_scaling/aws_openshift_quickstart/scaler.py
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


echo "Installing docker"
yum install docker -y
systemctl start docker
LOGFILE="${PWD}/logs/${SCRIPT%.*}.log"

chmod +x /ibm/cpd_install.py
/ibm/cpd_install.py --region "${AWS_REGION}" --stackid "${AWS_STACKID}" --stack-name ${AWS_STACKNAME} --logfile $LOGFILE --loglevel "*=all"