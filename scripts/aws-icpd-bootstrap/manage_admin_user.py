import subprocess
import os
import sys
import json

DSX_NAMESPACE="zen"

# This gets the cloudant pod which is actually running.
# If multiple pods are returned, then the selection of pod is non-deterministic.
# If no pods are found, returns empty string
def getCloudantPod():

  # Find cloudant pods that are Running.
  bash_command = "kubectl get pods --namespace=" +DSX_NAMESPACE+ " | grep 'cloudant' | grep 'Running' | grep '[ ][1-9][1-9]*/[1-9]' | sed 's#^\([^ ]*\).*[ ].*\$#\1#g'"
  cloudantpods = subprocess.check_output(['bash','-c', bash_command]).decode('UTF-8').split('\n')
  # Turn the string of pod names into an array, then pull the first one.

  return cloudantpods[0].split()[0]


# This fetchs latest admin record from cloudant db.
# curl request is executed inside cloudant pod
def getLatestAdminRecord(cloudantpod, username):

  bash_command = "kubectl -n " +DSX_NAMESPACE+ "  exec -it " +cloudantpod+ " -- bash -c 'curl http://${CLOUDANT_USERNAME}:${CLOUDANT_PASSWORD}@cloudant-svc/privatecloud-users/$0' " +username

  adminRecord=subprocess.check_output(['bash','-c', bash_command]).decode('UTF-8').split('\n')
  return adminRecord

# This makes a curl request to update admin record
def updateCloudantDB (cloudantpod, username, newAdminRecord):

  bash_command = "kubectl -n "+DSX_NAMESPACE+ " exec -it " +cloudantpod+ " -- bash -c 'curl -X PUT -H \"Accept: application/json\" http://${CLOUDANT_USERNAME}:${CLOUDANT_PASSWORD}@cloudant-svc/privatecloud-users/$0 -d \"$1\"' "+username+ " '"+newAdminRecord+"'"
  result=json.loads(subprocess.check_output(['bash','-c', bash_command]).decode('UTF-8').split('\n')[0])
  return result

# enable admin in cloudant DB
def enableAdminInCloudant(argv):

   # arguments
  username=argv[1]
  newPassword=argv[2]

  # get a running cloudant pod
  cloudantpod=getCloudantPod()

  # get admin record
  adminRecord=json.loads(getLatestAdminRecord(cloudantpod, username)[0])

  # send a curl request to usermgmt to encrypt new password
  bash_command = "kubectl -n "+DSX_NAMESPACE+ " exec -it " +cloudantpod+ " -- bash -c 'curl -d \"username=$0&password=$1\" -X POST http://usermgmt-svc:8080/v1/usermgmt/generatePasswordHash' "+username+ "  "+newPassword
  newPasswordData=json.loads(subprocess.check_output(['bash','-c', bash_command]).decode('UTF-8').split('\n')[0])

  newSalt=newPasswordData['salt']
  newPasswordHash=newPasswordData['password_hash']
  adminRecord['salt'] = newSalt
  adminRecord['password_hash'] = newPasswordHash 
  adminRecord['current_account_status'] = "enabled" 

  # aenable current_account_status and update new password
  # update cloudant DB
  result=updateCloudantDB(cloudantpod, username, json.dumps(adminRecord))
  success=result["ok"]
  print success
  if success == True:
    print username+ " account has been enabled."
  else:
    print "Error in enabling account. Try again."

if __name__ == "__main__":
  enableAdminInCloudant(sys.argv)