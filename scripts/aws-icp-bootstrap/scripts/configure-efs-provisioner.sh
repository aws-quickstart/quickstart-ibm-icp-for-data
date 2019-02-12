#!/usr/bin/env bash
#  Purpose
#  This scripts sets up the EFS Provisioner
#

set -e
set -u

# No need to do this since the curl commands below are no longer in action.
#rm -rf /tmp/efsprov
#mkdir -p /tmp/efsprov

EFSFileSystemId=fs-c6d62ddf
EFSRegion=us-west-1
EFSProvisionerNamespace=default

clear
# The manifest.yaml and rbac.yaml are incorporated into the script package in config/efs
#curl -Lo /tmp/efsprov/manifest.yaml https://raw.githubusercontent.com/kubernetes-incubator/external-storage/master/aws/efs/deploy/manifest.yaml
#curl -Lo /tmp/efsprov/rbac.yaml https://raw.githubusercontent.com/kubernetes-incubator/external-storage/master/aws/efs/deploy/rbac.yaml

sed -i.bkp "s/namespace:.*/namespace: ${EFSProvisionerNamespace}/g" /tmp/efsprov/rbac.yaml

kubectl create -f /tmp/efsprov/rbac.yaml

cat <<EOF | kubectl create -f -
  apiVersion: v1
  kind: ServiceAccount
  metadata:
    name: efs-provisioner
EOF

sed -i.bkp "s/yourEFSsystemid/${EFSFileSystemId}/g" /tmp/efsprov/manifest.yaml
sed -i.bkp "s/yourEFSsystemID/${EFSFileSystemId}/g" /tmp/efsprov/manifest.yaml
sed -i.bkp "s/regionyourEFSisin/${EFSRegion}/g" /tmp/efsprov/manifest.yaml
sed -i.bkp "s/yourEFSregion/${EFSRegion}/g" /tmp/efsprov/manifest.yaml

# Useful Tools for Kubectl Patching
# http://www.jsonpointer.com
# https://json-patch-builder-online.github.io/
# http://jsonviewer.stack.hu/

kubectl patch clusterimagepolicies $(kubectl get clusterimagepolicies --no-headers | awk '{print $1}') -p '[{"op":"add","path":"/spec/repositories/-","value":{"name":"quay.io/external_storage/efs-provisioner:*"}}]' --type=json

kubectl apply -f /tmp/efsprov/manifest.yaml

kubectl patch storageclass aws-efs -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
