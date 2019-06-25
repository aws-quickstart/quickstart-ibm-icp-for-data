
"""
Created on 21 JUN 2018

@author: Peter Van Sickel pvs@us.ibm.com
"""


class AWSStackResourceException(Exception):
  """
    AWSStackResourceException is raised when something unexpected occurs 
    related to AWS CloudFormation stack resources.
  """
#endClass

class AWSStackException(Exception):
  """
    AWSStackException is raised when something unexpected occurs related 
    to AWS CloudFormation stacks.
  """
#endClass


