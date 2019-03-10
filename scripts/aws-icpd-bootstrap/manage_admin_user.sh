#!/bin/bash

#!/bin/sh
DSX_NAMESPACE="zen"
set -e
# Script usage
function usage {
  echo ""
  echo "Script Usage:"
  echo "./manage_admin_user.sh --disable-admin <ADMIN_USERNAME>     Disables dsxl admin with username <ADMIN_USERNAME>."
  echo "./manage_admin_user.sh --enable-admin <ADMIN_USERNAME>      Enables dsxl admin with username <ADMIN_USERNAME>. Sets new login password."
  echo ""
}
# This function gets the cloudant pod which is actually running.
# If multiple pods are returned, then the selection of pod is non-deterministic.
# If no pods are found, returns empty string
function getCloudantPod {
  # Find cloudant pods that are Running.
  cloudantpods=$(kubectl get pods --namespace=$DSX_NAMESPACE | grep "cloudant" | grep "Running" | grep "[ ][1-9][1-9]*/[1-9]" | sed "s#^\([^ ]*\).*[ ].*\$#\1#g")
  # Turn the string of pod names into an array, then pull the first one.
  read -r -a cloudantpodsarr <<< "$cloudantpods"
  echo "${cloudantpodsarr[0]}"
}
# This function fetchs latest admin record from cloudant db.
# curl request is executed inside cloudant pod
function getLatestAdminRecord {
  # arguments
  cloudantpod=$1
  username=$2
  adminRecord=$(kubectl -n $DSX_NAMESPACE exec -it $cloudantpod -- bash -c \
  'curl http://${CLOUDANT_USERNAME}:${CLOUDANT_PASSWORD}@cloudant-svc/privatecloud-users/$0' $username)
  echo "${adminRecord}"
}
# This function makes a curl request to update admin record
function updateCloudantDB {
  # arguments
  cloudantpod=$1
  username=$2
  newAdminRecord=$3
  result=$(kubectl -n $DSX_NAMESPACE exec -it $cloudantpod -- bash -c \
  'curl -X PUT -H "Accept: application/json" http://${CLOUDANT_USERNAME}:${CLOUDANT_PASSWORD}@cloudant-svc/privatecloud-users/$0 -d "$1"' $username "$newAdminRecord")
  echo "${result}"
}
# disable admin in cloudant DB
function disableAdminInCloudant {
  # arguments
  username=$1
  # get a running cloudant pod
  cloudantpod=$(getCloudantPod)
  # get latest admin record
  adminRecord=$(getLatestAdminRecord "${cloudantpod}" "${username}")
  # set current_account_status field to "disabled"
  newAdminRecord=$(echo $adminRecord | sed 's/"current_account_status":"enabled"/"current_account_status":"disabled"/')
  # update admin record
  result=$(updateCloudantDB "${cloudantpod}" "${username}" "${newAdminRecord}")
  success=$(echo $result | sed 's/.*"ok":[[:space:]]*\([a-z]*\).*/\1/')
  if "$success" = "true" ;
  then
    echo "$username account has been disabled."
  else
    echo "Error in disabling $username account. Try again."
  fi
}
# enable admin in cloudant DB
function enableAdminInCloudant {
   # arguments
  username=$1
  newPassword=$2
  # get a running cloudant pod
  cloudantpod=$(getCloudantPod)
  # get admin record
  adminRecord=$(getLatestAdminRecord "${cloudantpod}" "${username}")
  # send a curl request to usermgmt to encrypt new password
  newPasswordData=$(kubectl -n $DSX_NAMESPACE exec -it $cloudantpod -- bash -c \
  'curl -d "username=$0&password=$1" -X POST http://usermgmt-svc:8080/v1/usermgmt/generatePasswordHash' $username $newPassword)
  newSalt=$(echo $newPasswordData | grep -o '"salt":"[[:alnum:]]*"' | cut -d':' -f2)
  newPasswordHash=$(echo $newPasswordData | grep -o '"password_hash":"[[:alnum:]]*"' | cut -d':' -f2)
  # enable current_account_status and update new password
  updatedAdminRecord=$(echo $adminRecord | sed -e 's/"current_account_status":"disabled"/"current_account_status":"enabled"/' \
  -e 's/"salt":"[[:alnum:]]*"/"salt":'$newSalt'/' -e 's/"password_hash":"[[:alnum:]]*"/"password_hash":'$newPasswordHash'/' )
  # update cloudant DB
  result=$(updateCloudantDB "${cloudantpod}" "${username}" "${updatedAdminRecord}")
  success=$(echo $result | sed 's/.*"ok":[[:space:]]*\([a-z]*\).*/\1/')
  if "$success" = "true" ;
  then
    echo "$username account has been enabled."
  else
    echo "Error in enabling $username account. Try again."
  fi
}
if ! kubectl version > /dev/null 2>&1 ; then
  echo ""
  echo "ERROR: Unable to execute 'kubectl' commands."
  echo "To run this script you must configure the host with 'kubectl'"
  echo ""
  exit 1
fi
flagoptions=":-:"
while getopts "$flagoptions" option; do
  case "${option}" in
    -)
      case "${OPTARG}" in
        disable-admin)
          username="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
          disableAdminInCloudant ${username}
          ;;
        enable-admin)
          username="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
          password="${!OPTIND}"; OPTIND=$(( $OPTIND + 2 ))
          enableAdminInCloudant ${username} ${password}
          ;;
        *)
          if [ "$OPTERR" = 1 ] && [ "${optspec:0:1}" != ":" ]; then
            echo "Unknown option: --${OPTARG}" >&2
            usage
          fi
          ;;
      esac
      ;;
    *)
      if [ "$OPTERR" != 1 ] || [ "${optspec:0:1}" = ":" ]; then
        echo "Unknown option: '-${OPTARG}'" >&2
        usage
      fi
      ;;
  esac
done
if [ $OPTIND -eq 1 ]; then
  echo ""
  echo "ERROR: No options passed to script."
  echo ""
  usage
  exit 1
fi
shift $((OPTIND-1))