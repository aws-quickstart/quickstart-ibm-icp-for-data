#!/bin/bash
###############################################################################
# Licensed Material - Property of IBM
# 5724-I63, 5724-H88, (C) Copyright IBM Corp. 2018 - All Rights Reserved.
# US Government Users Restricted Rights - Use, duplication or disclosure
# restricted by GSA ADP Schedule Contract with IBM Corp.
#
# DISCLAIMER:
# The following source code is sample code created by IBM Corporation.
# This sample code is provided to you solely for the purpose of assisting you
# in the  use of  the product. The code is provided 'AS IS', without warranty or
# condition of any kind. IBM shall not be liable for any damages arising out of 
# your use of the sample code, even if IBM has been advised of the possibility 
# of such damages.
#
###############################################################################


# Provide usage information here.  
function usage {
  echo "Usage: configure-inception.sh [options]"
  echo "   --icpHome <path>             - (optional) the path to the ICP home directory"
  echo "                                  Defaults to /opt/icp"
  echo "   --help|-h                    - emit this usage information"
}

# The info() function has the following invocation form:
#  info $LINENO "msg"
#  info expects up to 2 "global" environment variables to be set:
#    $SCRIPT         - the name of the script that is calling info()
#    $LOGFILE        - the full path to the log file associated with 
#                      the script that is calling info()
#
function info {
  local lineno=$1; shift
  ts=$(date +[%Y/%m/%d-%T])
  echo "$ts $SCRIPT($lineno) $*" | tee -a $LOGFILE
}

##### "Main" starts here
SCRIPT=${0##*/}

# Make sure there is a "logs" directory in the current directory
if [ ! -d "${PWD}/logs" ]; then
  mkdir logs
  rc=$?
  if [ "$rc" != "0" ]; then
    # Not sure why this would ever happen, but...
    # Have to echo here since trace log is not set yet.
    echo "Creating ${PWD}/logs directory failed.  Exiting..."
    exit 1
  fi
fi

LOGFILE="${PWD}/logs/${SCRIPT%.*}.log"

icpHome=""

# process the input args
# For keyword-value arguments the arg gets the keyword and
# the case statement assigns the value to a script variable.
# If any "switch" args are added to the command line args,
# then it wouldn't need a shift after processing the switch
# keyword.  The script variable for a switch argument would
# be initialized to "false" or the empty string and if the 
# switch is provided on the command line it would be assigned
# "true".
#
while (( $# > 0 )); do
  arg=$1
  case $arg in
    -h|--help ) usage; exit 0
                  ;;

    --icpHome|-icpHome )  icpHome="$2"; shift
                  ;;

    * ) usage; info $LINENO "Unknown option: $arg in command line." 
        exit 2
        ;;
  esac
  # shift to next key-value pair
  shift
done

if [ -z "$icpHome" ]; then
  info $LINENO "The ICP home directory path is defaulting to /opt/icp"
  icpHome="/opt/icp"
fi

mkdir -p "$icpHome"
cd "$icpHome"

info $LINENO "Extracting the ICP meta-data from the inception container."
docker run -v $(pwd):/data -e LICENSE=accept ibmcom/icp-inception:2.1.0.3-ee cp -r cluster /data

cd ./cluster
cp /root/hosts .
cp /root/config.yaml .
cp /root/.ssh/id_rsa ssh_key
