#!/bin/bash

# copy .docker folder content - config.json from master node
FILE_NAME=$3/cluster/config.yaml

# Key in Property File
icpuname="default_admin_user:"
icppw="default_admin_password:"
# Variable to hold the Property Value
prop_uname=`cat ${FILE_NAME} | grep ${icpuname} | cut -d' ' -f2`
prop_pwd=`cat ${FILE_NAME} | grep ${icppw} | cut -d' ' -f2`

echo $(pwd)
echo "create .docker"
mkdir -p .docker
cd .docker
echo $(pwd)
echo "scp -o StrictHostKeyChecking=no root@$1:~/.docker/config.json ."
scp -o StrictHostKeyChecking=no root@$1:~/.docker/config.json .
echo "copied config.json from master node"
echo $(ls)
# copy certifcates from master node
echo "cd /etc/docker/"
cd /etc/docker/
echo "create certs.d"
mkdir -p certs.d
echo "create certs.d/$2\:8500"
mkdir -p certs.d/$2\:8500
cd certs.d/$2\:8500
echo $(pwd)
echo "scp -o StrictHostKeyChecking=no root@$1:/etc/docker/certs.d/$2\:8500/ca.crt ."
scp -o StrictHostKeyChecking=no root@$1:/etc/docker/certs.d/$2\:8500/ca.crt .
echo "copy root-ca.crt"
scp -o StrictHostKeyChecking=no root@$1:/etc/docker/certs.d/$2\:8500/root-ca.crt .
echo $(ls)
# extract icpd tar file to /ibm dir
echo "create /ibm"
mkdir -p /ibm
echo "cd to /tmp and extract icpd tar to /ibm"
cd /tmp
 tar -xvf icp4d.tar -C /ibm/
cd /ibm
echo $(ls)
echo "change permission for installer"
chmod +x installer.x86_64.373
echo $(ls -la)
echo "Docker login"
docker login $2:8500/zen -u ${prop_uname} -p ${prop_pwd}
echo "run installer to extract icpd"
storageclass=$(($(kubectl get storageclass | nl | grep aws-efs | awk '{print $1}') - 1))
echo ${storageclass}
printf "\nA\nzen\nY\n$2:8500/zen\n\nY\nN\n${storageclass}\nY\nY" | ./installer.x86_64.373 
cp /ibm/InstallPackage/components/install.log /root/logs