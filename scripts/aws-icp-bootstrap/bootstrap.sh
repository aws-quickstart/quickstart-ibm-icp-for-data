#!/bin/bash


# Provide usage information here.  
function usage {
  echo "Usage: bootstrap.sh [options]"
  echo "   --os <distro>              - (required) Linux distro. ubuntu|redhat"
  echo "   --help|-h                  - emit this usage information"
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

os=""

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

    --os|-os )  os="$2"; shift
                  ;;
    
    * ) usage; info $LINENO "Unknown option: $arg in command line." 
        exit 2
        ;;
  esac
  # shift to next key-value pair
  shift
done

if [ -z "$os" ]; then
  os=ubuntu
  #info $LINENO "ERROR: The linux distribution must be provided."
  #exit 3
fi

# The mystack.props file holds the env vars 
#   REGION        - the AWS region name 
#   ROOT_STACK_ID - root template stack ID 
#   STACK_ID      - boot node template stack ID 
#   STACK_NAME    - the name of the boot node stack 
#   ROLE          - the ICP role of this stack, e.g., boot, master, proxy, worker, ...
# All the env vars are used to invoke bootstrap.py below.
# The mystack.props file is written out to root's home directory by the CloudFormation template.
source ~/mystack.props

# Hack to make scripts executable.
chmod +x scripts/*.sh

~/bootstrap.py --region "${REGION}" --stackid "${STACK_ID}" --stack-name ${STACK_NAME} --role ${ROLE} --logfile $LOGFILE --loglevel "@{LOGLEVEL}"
