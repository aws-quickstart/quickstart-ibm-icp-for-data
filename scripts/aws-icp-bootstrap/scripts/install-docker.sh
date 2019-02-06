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
  echo "Usage: install-docker.sh [options]"
  echo "   --playbook <playbook_path>   - (optional) the path to the Ansible playbook used to install Docker."
  echo "                                  Defaults to install-docker.yaml."
  echo "   --nodes <target_nodes>       - (optional) a pattern or group name that specifies target nodes for the playbook."
  echo "                                  Defaults to all."
  echo "   --inventory <inventory_path> - (optional) path to the host inventory, pass-through to ansible-playbook."
  echo "                                  Defaults to /etc/ansible/hosts"
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

playbook=""
nodes=""
inventory=""

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

    --playbook|-playbook )  playbook="$2"; shift
                  ;;

    --nodes|-nodes )  nodes="$2"; shift
                  ;;
    
    --inventory|-inventory )  inventory="$2"; shift
                  ;;

    * ) usage; info $LINENO "Unknown option: $arg in command line." 
        exit 2
        ;;
  esac
  # shift to next key-value pair
  shift
done

if [ -z "$playbook" ]; then
  info $LINENO "The playbook path is defaulting to ${PWD}/install-docker.yaml"
  playbook="${PWD}/install-docker.yaml"
fi

if [ -z "$nodes" ]; then
  info $LINENO "The target nodes is defaulting to all."
  nodes=all
fi

if [ -z "$inventory" ]; then
  info $LINENO "The hosts inventory is defaulting to /etc/ansible/hosts."
  inventory="/etc/ansible/hosts"
fi

ansible-playbook "$playbook" --extra-vars "target_nodes=$nodes" --inventory "$inventory" | tee -a $LOGFILE

