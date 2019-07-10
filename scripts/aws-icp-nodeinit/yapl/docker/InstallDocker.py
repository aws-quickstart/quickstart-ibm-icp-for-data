"""

Created on Jul 3, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

Description:
  This module invokes 1 or more Ansible playbooks to install and configure Docker
  using the Docker install executable that comes with IBM Cloud Private. 
  
History:
  2018-07-03 - pvs - Initial creation

"""

import sys, os.path
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import InvalidArgumentException
from yapl.exceptions.Exceptions import MissingArgumentException
from yapl.exceptions.Exceptions import AttributeValueException

# imports needed for interaction with Ansible
from collections import namedtuple
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.executor.playbook_executor import PlaybookExecutor

TR = Trace(__name__)

class InstallDocker:
  """
    Install Docker by invoking an Ansible playbook.
    The Ansible playbook does all the real work.
    The class is merely a vehicle to invoke the Ansible playbook.
  """


  def __init__(self, inventory_path='/etc/ansible/hosts/'):
    """
      Constructor
      
      inventory_path - file system path to host inventory
    """
    self.configureAnsible(inventory_path)
    
  #endDef
  

  def get_hosts(self, pattern):
    """
      Wrapper for Ansible InventoryManager get_hosts().
    """
    methodName = "get_hosts"
    if (not self.inventory):
      raise AttributeValueException("Scripting Error: The inventory instance variable is expected to have a value.")
    #endIf

    hosts = self.inventory.get_hosts(pattern)
    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName,"For pattern: %s, hosts: %s" % (pattern, hosts))
    #endIf
    return hosts
  #endDef


  def runPlaybook(self, playbook_path, extra_vars):
    """
      Helper method to run the Ansible playbook that is used to install Docker for ICP.
      
      extra_vars is a dictionary of key-value pairs where each key is the playbook variable name 
      and the value associated with the key is used as the variable value for running the playbook.
      For example:
        { 'target_nodes': 'worker' }
      The variable value can be a regular expression pattern that leads to a match with some hosts
      in the host inventory associated with this instance of the class.
    """

    self.variable_manager.extra_vars = extra_vars

    # The constructor for PlaybookExecutor has all of the following parameters required.
    pbex = PlaybookExecutor(playbooks=[playbook_path],
                            inventory=self.inventory,
                            variable_manager=self.variable_manager,
                            loader=self.loader,
                            options=self.options,
                            passwords=self.passwords)

    pbex.run()

  #endDef


  def configureAnsible(self, inventory_path):
    """
      Create instances if the various data structures needed to run an Ansible playbook.
    """

    if (not inventory_path):
      raise MissingArgumentException("An inventory path must he provided.")
    #endIf

    self.loader = DataLoader()

    # The Options tuple is a pain in the neck.  There is a boatload of possible options.  You would hope they would
    # all default to something reasonable.  There is no documentation that I can find on the possible values for options.
    # There is no documentation on which options are required.  You have to run your code and see what breaks.  The
    # examples show a lot of options that all seem to take on a "don't care" value, e.g., False, None.
    # NOTE: For every attribute listed in the Options namedtuple, an attribute value must be provided when the Options()
    # constructor is instantiated.
    # NOTE: I tried using forks=0 which I was hoping would lead to some default being used, but instead I got a "list index
    # out of range" error in Ansible code: linear.py which is invoked out of task_queue_manager.py.
    # NOTE: listtags, listtasks, listhosts, syntax and diff are all required for sure.  Errors occur if they are not attributes
    # of the given options.
    Options = namedtuple('Options', ['listtags', 'listtasks', 'listhosts', 'syntax', 'connection','module_path', 'forks', 'remote_user', 'private_key_file', 'ssh_common_args', 'ssh_extra_args', 'sftp_extra_args', 'scp_extra_args', 'become', 'become_method', 'become_user', 'verbosity', 'check', 'diff'])
    self.options = Options(listtags=False, listtasks=False, listhosts=False, syntax=False, connection='ssh', module_path=None, forks=5, remote_user=None, private_key_file=None, ssh_common_args=None, ssh_extra_args=None, sftp_extra_args=None, scp_extra_args=None, become=False, become_method=None, become_user=None, verbosity=None, check=False, diff=False)

    # Based on my skim of the InventoryManger code, sources is intended to be a list of paths.
    # It can also be a string that is one path or comma-separated string that is a list of paths.
    self.inventory = InventoryManager(loader=self.loader, sources=[inventory_path])

    # NOTE: VariableManager constructor doesn't require inventory, but if you don't provide one you get exceptions.
    self.variable_manager = VariableManager(loader=self.loader, inventory=self.inventory)

    # For now, we don't need any passwords.  Future version of script could support provision of passwords.
    self.passwords = {}

  #endDef
  
  
  
#endClass