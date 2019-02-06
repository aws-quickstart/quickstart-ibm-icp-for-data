
"""
Created on Dec 7, 2016

@author: Peter Van Sickel pvs@us.ibm.com
"""

class AccessDeniedException(Exception):
  """
    The AccessDeniedException is intended to be raised when some operation results in a 403 or some other
    access denied result.
  """
#endClass


class NotImplementedException(Exception):
  """
    The NotImplementedException is intended for use in code blocks where some function is not implemented.
    This serves as a way to do something explicit where code could be written to implement some function
    or feature, but was not.  The reason for non-implementation could be simply lack of time or lack of a
    requirement for such code.  The script library is a constantly evolving body of code that is being 
    developed on an as-needed basis.  Hence there are occasions when something is not implemented but it 
    is desirable to fail explicitly in a particular code path rather than implicitly in some unexpected
    code path.
  """
#endClass


class ExitException(Exception):
  """
    ExitException is used to jump to the end of a method that wraps its body 
    in a try-except.  This is useful for cases where some condition arises 
    that is not necessarily an error, but the path of execution should jump
    to the exit of the method.
  """
#endClass


class FileNotFoundException(Exception):
  """
    FileNotFoundException is raised when a file that is expected to exist at 
    a given path does not actually exist.
  """
#endClass


class FileTransferException(Exception):
  """
    FileTransferException is raised when there is a problem transferring a file from
    some source to some destination.
  """
#endClass


class InvalidArgumentException(Exception):
  """
    InvalidArgumentException is raised when the value of an argument provided is not
    "valid" for some reason, e.g., it is out of range or an incorrect type.
  """
#endClass


class InvalidConfigurationException(Exception):
  """
    An InvalidConfigurationException is raised when it is determined that a given configuration is invalid.
    This can be used for any kind of configuration and is intended to be used for any kind of configuration
    issue.
  """
#endClass


class InvalidConfigurationFile(Exception):
  """
    InvalidConfigurationFile is raised when a configuration file is being processed and 
    something is missing that is expected to be there.  Or a value that is found there 
    is incorrect in some way.  Usually the configuration file is a JSON file that is
    read in using a JSON parser and then the object is processed for content.  When 
    something unexpected appears with that content, this exception is raised.
  """
#endClass


class InvalidParameterException(Exception):
  """
    InvalidParameterException gets raised what a parameter for something is not valid.
    It could be that a parameter that is expected to be in a configuration file is not
    found in that file.  Or some other circumstance where a parameter does not match 
    a list of valid parameters.  The difference between an InvalidParameterException
    and an InvalidArgument exception may be a matter of opinion.  InvalidArgumentException
    is intended to be used in the context of a method call where a provided argument
    value is not valid.  InvalidParameterException is intended to be used in the 
    context of a parameterized object or configuration file.
  """
#endClass

class InstallationException(Exception):
  """
    InstallationException is raised when something unexpected occurs at some 
    point in a scripted installation process for a given component.
  """
#endClass

class MissingArgumentException(Exception):
  """
    The MissingArgumentException is thrown when a "required" keyword argument is not provided 
    with a non-empty value.  The scripts in the library make heavy use of keyword arguments 
    rather than positional arguments, but those arguments are often still required to be provided
    with some value.  Usually the keyword argument default value is the empty string, but 
    occasionally None is also used as a default value.  The caller must provide a non-empty
    value on method invocation.
  """
#endClass

class AttributeValueException(Exception):
  """
    The AttributeValueException is raised when an attribute value of an object is None or has
    a value that is not of the proper type or within the proper range.  In short, this exception
    is intended to be raised for any issue discovered with an attribute value.  The built-in
    Python AttributeError exception is more low level than AttributeValueException in that 
    the object supports the given attribute in question, it's just that the value is not
    as expected. 
  """
#endClass

class JSONException(Exception):
  """
    JSONException is raised when there is some problem consuming a JSON document or 
    converting a Python object into its corresponding JSON document.
  """
#endClass

