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
chmod +x installer.x86_64.29
echo $(ls -la)
echo "run installer to extract icpd"
printf 'A\nA\n' | ./installer.x86_64.29 --existing-ICP
echo "find and replace docker registry and storage class"
sed -i "s/mycluster.icp/mycluster.icp4d-test.com/g" InstallPackage/components/install.yaml
sed -i "s/oketi-gluster/aws-efs/g" InstallPackage/components/install.yaml
sed -i "s/mycluster.icp/mycluster.icp4d-test.com/g" InstallPackage/components/installer.sh


echo "Docker login"
docker login $2:8500 -u ${prop_uname} -p ${prop_pwd}
echo "cd to InstallPackage"
echo $(pwd)
cd InstallPackage
echo " run deploy_on_existing.sh to install base modules"
printf "${prop_uname}\n${prop_pwd}\nY\nY\nY\nY\n" | ./deploy_on_existing.sh
echo "cd to components to install IIG and cognos modules"
cd components
echo $(pwd)
echo " run iig installer"
printf 'Y\nY\nY\nY\n' | ./deploy.sh /ibm/modules/ibm-iisee-zen-1.0.0.tar
echo " run cognos installer"
printf 'Y\nY\nY\nY\n' | ./deploy.sh /ibm/modules/ibm-dde-0.13.4-x86_64.tar
cp /ibm/InstallPackage/components/deploy.log /root/logs