#!/bin/bash
# ----------------------------------------------------------------------------------------------------\\
# Description:
#   Setup and deploy Transformation Advisor Helm Chart sample into IBM Cloud Private
# ----------------------------------------------------------------------------------------------------\\
set -e

# Get the variables
source 00-variables.sh

# Need to pre-create a secret required for Authentication
# As of TA 1.8.0, you need to create a secret on ICP.
# In the Secret, firstly, you need to enter a name, which will
# be asked in the TA helm installation page. Secondly, you need
# to select the namespace to the same one which your TA will be
# installed to. Thirdly, you need to add 2 entries of data with
# names of ...
#   db_username
#   secret
#
# The value of these values must be base64 encoded. For more
# information please visit TA helm installation readme.

#DB_USERNAME=$(echo -n $(openssl rand -hex 20) | base64)
#SECRET=$(echo -n $(openssl rand -hex 20) | base64)

DB_USERNAME=$(echo -n 'admin' | base64)
SECRET=$(echo -n 'sssshhhhhhh821$' | base64)
#STORAGE_CLASS=openebs-standard
STORAGE_CLASS=aws-efs

cat <<EOF | kubectl apply --overwrite -f -
  apiVersion: v1
  kind: Secret
  metadata:
    name: trans-adv-secret
    namespace: default
  type: Opaque
  data:
    db_username: ${DB_USERNAME}
    secret: ${SECRET}
EOF

helm install --tls ibm-charts/ibm-transadv-dev --name butterfly --set authentication.icp.edgeIp=${CLUSTER_NAME} --set authentication.icp.secretName=trans-adv-secret --set couchdb.persistence.storageClassName=${STORAGE_CLASS} --set transadvui.inmenu=true --set ingress.enabled=true

echo ""
echo "Congrats.  You can now browse to http://${PUBLIC_IP}/butterfly-ui to view your Transformation Advisor deployment"
echo ""