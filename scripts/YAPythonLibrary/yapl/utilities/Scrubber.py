"""
Created on Jan 25, 2019

@author: Peter Van Sickel - pvs@us.ibm.com

Description:
  Module to support scrubbing values from various types of objects before
  writing the object to a log file.  
  
  Originally developed to scrub passwords and access IDs from a dictionary
  object that holds such values. 

"""

def dreplace(source, replacements):
  """
    Return a new dictionary created from source with attribute values 
    from the replacements dictionary replacing the corresponding values
    in the source dictionary.
    
    source       - source dictionary
    replacements - replacement values dictionary
    
    If replacements is empty or None, then nothing is done.
    A reference to the source dictionary is returned.
     
  """
  
  if (not replacements):
    result = source
  else:
    result = source.copy()
    for key,value in replacements.iteritems():
      if (result.get(key) != None):
        result[key] = value
      #endIf
    #endFor
  #endIf
  return result
#endDef
  
