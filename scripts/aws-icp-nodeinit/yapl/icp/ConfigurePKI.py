

"""
Created on Aug 11, 2018

@author: Peter Van Sickel - pvs@us.ibm.com

Description:
  ConfigurePKI handles the configuration of ICP that works with keys and certificates.
  
History:
  
"""

import os
import uuid
import socket
from OpenSSL import crypto
from yapl.utilities.Trace import Trace, Level
from yapl.exceptions.Exceptions import MissingArgumentException



TR = Trace(__name__)


class ConfigurePKI:
  """
    Class to support the configuration of a Public Key Infrastructure for an
    IBM Cloud Private deployment.
  """

  def __init__(self,**restArgs):
    """
      Constructor
      The restArgs must include:
      
        pkiDirectory           - the path to the directory where PKI key and certificate for the 
                                 are to be created.
        pkiFileName            - the root name of the PKI key (.key file) and certificate (.crt file).  
      
      The restArgs may include:
        Parameters associated with the creation of the X.509 certificate
          C  - country code string, e.g., US
          ST - state or province code string
          O  - organization string
          OU - organization unit string
          CN - common name. Defaults to the host's FQDN
          serialNumber - serial number for the cert.  Defaults to a random number.
          notBefore - adjustment to current time (in seconds) when cert becomes valid.  Defaults to 0, i.e., "now".
          notAfter  - adjustment to current time (in seconds) when cert becomes invalid.  Defaults to 10 years.
          issuer - the certificate issuer/signer, defaults to self-signed.

        Parameters associated with the PKI key.
          bits - the size of the key.  Defaults to 2048.
       
       All incoming key and certificate parameters are stashed in a dictionary that
       can then be used as a restArgs for various methods.  
    """
    methodName = "ConfigurePKI"
    
    self.keyAndCertParms = {}
    
    self.pkiDirectory = restArgs.get('pkiDirectory')
    if (not self.pkiDirectory):
      raise MissingArgumentException("A PKI directory path (pkiDirectory) must be provided.")
    #endIf
    
    self.pkiFileName = restArgs.get('pkiFileName')
    if (not self.pkiFileName):
      raise MissingArgumentException("A PKI root file name (pkiFileName) must be provided.")
    #endIf
    
    self.fqdn = socket.getfqdn()

    C = restArgs.get('C')
    if (C):
      self.keyAndCertParms['C'] = C
    #endIf
    
    ST = restArgs.get('ST')
    if (ST):
      self.keyAndCertParms['ST'] = ST
    #endIf
    
    O = restArgs.get('O')
    if (O):
      self.keyAndCertParms['O'] = O
    #endIf
    
    OU = restArgs.get('OU')
    if (OU):
      self.keyAndCertParms['OU'] = OU
    #endIf
    
    CN = restArgs.get('CN')
    if (not CN):
      CN = self.fqdn
      if (TR.isLoggable(Level.FINE)):
        TR.fine(methodName, "Defaulting CN to FQDN: %s" % CN)
      #endIf
    #endIf
    self.keyAndCertParms['CN'] = CN
    
    notBefore = restArgs.get('notBefore')
    if (notBefore == None):
      notBefore = 0
    #endIf
    self.keyAndCertParms['notBefore'] = notBefore
    
    notAfter = restArgs.get('notAfter')
    if (notAfter == None):
      notAfter = self.getDefaultExpiry()
    #endIf
    self.keyAndCertParms['notAfter'] = notAfter
    
    issuer = restArgs.get('issuer')
    if (not issuer):
      issuer = None # self-sign this certificate
    #endIf
    self.keyAndCertParms['issuer'] = issuer

    
    # Collect private key related parameters into keyParms.
    bits = restArgs.get('bits')
    if (not bits):
      bits = 2048
      if (TR.isLoggable(Level.FINE)):
        TR.fine(methodName, "Defaulting the key size to %d" % bits)
      #endIf
    #endIf
    self.keyAndCertParms['bits'] = bits
    
  #endDef
  
  def getPKIParameters(self):
    """
      Return the PKI key and certificate parameters dictionary associated 
      with this instance.
      
      The dictionary can be dereferenced and used in calls to the methods
      supported by this class.
    """
    return self.keyAndCertParms
  #endDef
  
    
  def getDefaultExpiry(self):
    return 10*365*24*60*60      # 10 years expiry date
  #endDef
  
  
  def genSerialNumber(self):
    """
      Return a serial number that is used in creating an X.509 certificate.
    """
    return uuid.uuid4().int
  #endDef

  
  def createRSAKey(self, **restArgs):
    """
      Return an instance of a PKey that is an RSA key of the given number of bits.
      
      The RSA key is typically used to create an X.509 certificate. 
    """
    
    bits = restArgs.get('bits',2048)
    
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, bits)  # generate RSA key-pair
    
    return key   
  #endDef
  
  
  def createX509Cert(self,certKey=None,**restArgs):
    """
      Create an X509 certificate using the given key pair or a created RSA key pair
      and using the current FQDN if a CN is not provided in the restArgs.
      
      The restArgs may include:
        C  - country code string, e.g., US
        ST - state or province code string
        O  - organization string
        OU - organization unit string
        CN - common name, typically provided by the caller
        serialNumber - serial number for the cert.  Defaults to a random number.
        notBefore - adjustment to current time (in seconds) when cert becomes valid.  Defaults to 0, i.e., "now".
        notAfter  - adjustment to current time (in seconds) when cert becomes invalid.  Defaults to 10 years.
        issuer - the certificate issuer/signer, defaults to self-signed.

      issuer is an X509Name according to the Python Crypto documentation.
      See https://pyopenssl.org/en/stable/api/crypto.html#x509-objects
      
      Found sample code here:
      https://gist.github.com/ninovsnino/8b0e5ce773b959da6c16
      
      See Python interface to OpenSSL doc here:
      https://pyopenssl.org/en/stable/api.html
    """
    
    if (not certKey):
      certKey = self.createRSAKey()
    #endIf
    
    cert = crypto.X509()
    
    C = restArgs.get('C')
    if (C):
      cert.get_subject().C = C
    #endIf
    
    ST = restArgs.get('ST')
    if (ST):
      cert.get_subject().ST = ST
    #endIf
    
    O = restArgs.get('O')
    if (O):
      cert.get_subject().O = O
    #endIf
    
    OU = restArgs.get('OU')
    if (OU):
      cert.get_subject().OU = OU
    #endIf
    
    CN = restArgs.get('CN')
    if (not CN):
      CN = self.keyAndCertParms.get('CN')
      if (not CN):
        raise MissingArgumentException("A CN value is a required certificate parameter.")
      #endIf
    #endIf
    cert.get_subject().CN = CN
    
    serialNumber = restArgs.get('serialNumber')
    if (not serialNumber):
      serialNumber = self.genSerialNumber()
    #endIf
    cert.set_serial_number(serialNumber)
    
    notBefore = restArgs.get('notBefore')
    if (notBefore == None):
      notBefore = 0
    #endIf
    cert.gmtime_adj_notBefore(notBefore)
    
    notAfter = restArgs.get('notAfter')
    if (notAfter == None):
      notAfter = self.getDefaultExpiry()
    #endIf
    cert.gmtime_adj_notAfter(notAfter)  
    
    issuer = restArgs.get('issuer')
    if (not issuer):
      issuer = cert.get_subject() # self-sign this certificate
    #endIf
    cert.set_issuer(issuer)
    
    cert.set_pubkey(certKey)
    cert.sign(certKey, 'sha256')
    
    return cert    
  #endDef
  
  
  def dumpX509Cert(self, cert, certFilePath):
    """
      Write out a text file for the given cert to the given certFilePath.
    """

    # wt is "write text"
    with open(certFilePath,"wt") as certFile:
      certFile.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    #endWith
  #endDef
    
    
  def dumpPrivateKey(self, key, keyFilePath):
    """
      Write out a text file of the private key for the given key (pair) to the given keyFilePath.
    """
    
    # wt is "write text"
    with open(keyFilePath,"wt") as keyFile:
      keyFile.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
    #endWith
  #endDef


  def createKeyCertPair(self,**restArgs):
    """
      Return a tuple private RSA key, X.509 certificate.
      
      Write the private key and the X.509 certificate to .key and .crt files 
      to the instance pkiDirectory using the pkiFileName as the root file name.  
      
    """
    methodName = "createKeyCertPair"
    
    if (not os.path.exists(self.pkiDirectory)):
      os.makedirs(self.pkiDirectory,0600)
    #endIf
    
    key = self.createRSAKey(**restArgs)
    cert = self.createX509Cert(certKey=key,**restArgs)
        
    keyFilePath = os.path.join(self.pkiDirectory, "%s.key" % self.pkiFileName)
    if (TR.isLoggable(Level.FINE)):
      TR.info(methodName, "Writing private key to: %s" % keyFilePath)
    #endIf
    self.dumpPrivateKey(key, keyFilePath)
    
    certFilePath = os.path.join(self.pkiDirectory, "%s.crt" % self.pkiFileName)
    if (TR.isLoggable(Level.FINE)):
      TR.fine(methodName, "Writing public certificate to: %s" % certFilePath)
    #endIf
    self.dumpX509Cert(cert, certFilePath)
    
    return (key,cert)
  #endDef
    
#endClass
