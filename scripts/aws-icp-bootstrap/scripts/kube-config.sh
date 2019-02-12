#!/bin/bash

source variables.sh

set -e

cd $(dirname "$(find /opt -path "*" -type d -name "cluster")")

# Get kubectl
# Append a -ee on the version number for Cloud Native Installs (e.g. v1.9.1-ee)
sudo docker run -e LICENSE=accept --net=host -v /usr/local/bin:/data ibmcom/icp-inception-amd64:3.1.0-ee cp /usr/local/bin/kubectl /data

# Make config directory
mkdir -p ~/.kube


if [ ! -f /var/lib/kubelet/kubectl-config ]; then
  # Boot (Bastion) Node approach
  scp ${SSH_USER}@$MASTER_IP:/var/lib/kubelet/kubectl-config ~/.kube/config
else
  sudo cp /var/lib/kubelet/kubectl-config ~/.kube/config
fi

if [ ! -f /etc/cfc/conf/kubecfg.crt ]; then
  # Boot (Bastion) Node approach
  scp ${SSH_USER}@$MASTER_IP:/etc/cfc/conf/kubecfg.crt ~/.kube/kubecfg.crt
else
  sudo cp /etc/cfc/conf/kubecfg.crt ~/.kube/kubecfg.crt
fi

if [ ! -f /etc/cfc/conf/kubecfg.key ]; then
  # Boot (Bastion) Node approach
  scp ${SSH_USER}@$MASTER_IP:/etc/cfc/conf/kubecfg.key ~/.kube/kubecfg.key
else
  sudo cp /etc/cfc/conf/kubecfg.key ~/.kube/kubecfg.key
fi

sudo chown -R $USER  ~/.kube/

#Set kube config
kubectl config set-cluster cfc-cluster --server="https://${CLUSTER_NAME}:8001" --insecure-skip-tls-verify=true
kubectl config set-context kubectl --cluster=cfc-cluster
kubectl config set-credentials user --client-certificate=$HOME/.kube/kubecfg.crt --client-key=$HOME/.kube/kubecfg.key
kubectl config set-context kubectl --user=user
kubectl config use-context kubectl
