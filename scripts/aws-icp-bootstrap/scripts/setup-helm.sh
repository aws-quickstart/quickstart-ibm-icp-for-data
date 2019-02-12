#!/usr/bin/env bash
#  Purpose
#  This scripts sets up the Helm CLI
#

set -e
set -u

HELMVERSION=2.9.1
curl -k -Lo /tmp/helm-linux-amd64.tar.gz https://mycluster.icp:8443/api/cli/helm-linux-amd64.tar.gz --header "Authorization: $(cloudctl tokens | grep "Access token:" | cut -d' ' -f3- | sed -e 's/^[[:space:]]*//')"
tar -zxf /tmp/helm-linux-amd64.tar.gz -C /tmp
chmod +x /tmp/linux-amd64/helm
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm

helm init --client-only
helm repo add ibm-charts https://raw.githubusercontent.com/IBM/charts/master/repo/stable/
helm repo add ibmcase-spring https://raw.githubusercontent.com/ibm-cloud-architecture/refarch-cloudnative-spring/master/docs/charts/
helm repo add --ca-file <(openssl s_client -showcerts -connect "mycluster.icp:8443" </dev/null 2>/dev/null|openssl x509 -outform PEM) --cert-file ~/.kube/kubecfg.crt --key-file ~/.kube/kubecfg.key mgmt-charts https://mycluster.icp:8443/mgmt-repo/charts

CERTCNT=$(find ~/.helm -type f -name "cert.pem" | wc -l)
KEYCNT=$(find ~/.helm -type f -name "key.pem" | wc -l)

if [[ "${CERTCNT}" -eq 0 ]]; then
  echo -e "Something went wrong with the cluster-config command.  Manually patching helm home with cert.pem"
  cp $(find /opt -path "*/cfc-certs/helm/*" -type f -name "admin.crt") ~/.helm/cert.pem
fi

if [[ "${KEYCNT}" -eq 0 ]]; then
  echo -e "Something went wrong with the cluster-config command.  Manually patching helm home with key.pem"
  cp $(find /opt -path "*/cfc-certs/helm/*" -type f -name "admin.key") ~/.helm/key.pem
fi

helm version --tls

# Hint ... if you cannot connect to tiller
# Reset your ICP tiller deploy ... by doing these two steps on your boot/master node
#
# kubectl delete deploy tiller-deploy -n kube-system
# kubectl apply --force --overwrite=true -f $(find /opt -name tiller.yaml)
