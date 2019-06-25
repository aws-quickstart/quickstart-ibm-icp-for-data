#!/bin/bash
set -e

err_check() {
   echo "Error activating your license"
}

trap 'err_check ' ERR

ICPD_URL=https://<CLUSTERDNSNAME>:31843
ICPD_ADMIN_USER=$1
ICPD_ADMIN_PASSWORD=$2
ICPD_LICENSE=$3

echo ""
echo "Activating your ICPD"
echo ""
ICPD_TOKEN=$(curl -s -k -X GET ${ICPD_URL}/v1/preauth/validateAuth -u ${ICPD_ADMIN_USER}:${ICPD_ADMIN_PASSWORD} | python -c 'import sys, json; print json.load(sys.stdin)["accessToken"]')


message=$(curl -s -i -k -X POST ${ICPD_URL}/api/v1/usermgmt/v1/license/update -F  'action=TrialToPermanent' -F "upfile=@./${ICPD_LICENSE}" -H 'Content-Type: multipart/form-data' -H 'Accept: application/json' -H "Cookie: ibm-private-cloud-session=${ICPD_TOKEN}")

if [[ $message == *"success"* ]]; then
 echo "Your license is activated"
else
 echo "Error activating license: $message"
fi