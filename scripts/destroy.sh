#!/bin/bash
echo $1
echo $2
if [ "$1" == "Portworx" ] ; then
    CLUSTERID=$(oc get machineset -n openshift-machine-api -o jsonpath='{.items[0].metadata.labels.machine\.openshift\.io/cluster-api-cluster}')
    WORKER_INSTANCE_ID=`aws ec2 describe-instances --filters "Name=tag:Name,Values=$CLUSTERID-worker*" --output text --query 'Reservations[*].Instances[*].InstanceId'`
    DEVICE_NAME=`aws ec2 describe-instances --filters "Name=tag:Name,Values=$CLUSTERID-worker*" --output text --query 'Reservations[*].Instances[*].BlockDeviceMappings[*].DeviceName' | uniq`
    for winstance in ${WORKER_INSTANCE_ID[@]}; do
    for device in ${DEVICE_NAME[@]}; do
    aws ec2 modify-instance-attribute --instance-id $winstance --block-device-mappings "[{\"DeviceName\": \"$device\",\"Ebs\":{\"DeleteOnTermination\":true}}]"
    done
    done
    aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn $POLICY_ARN
    aws iam delete-policy --policy-arn $POLICY_ARN

fi    
sudo /ibm/openshift-install destroy cluster --dir=/ibm/installDir --log-level=info
aws ssm put-parameter \
    --name $2"_CleanupStatus" \
    --type "String" \
    --value "READY" \
    --overwrite