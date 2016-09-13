from copy import deepcopy
from lxml import etree
from urllib2 import urlopen

import botocore
import boto3
import decimal
import signxml
import sys
import uuid
import urllib2

NSMAP = {None : "http://www.w3.org/2000/09/xmldsig#"}
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    f = urlopen('http://md.incommon.org/InCommon/InCommon-metadata.xml')
    md_dom = etree.parse(f)
    md_root = md_dom.getroot()

    md_cert_pem = getFile('inc-md-cert.pem')
    our_cert = getFile('ours.pem')
    our_key = getFile('ours.key')

    try:
        asserted_metadata = signxml.XMLVerifier().verify(md_root, x509_cert=md_cert_pem)
        root = asserted_metadata.signed_xml

    except signxml.exceptions.InvalidSignature:
        print "ERROR: signature validation failure"
        sys.exit(5)

    id = root.attrib['ID']
    validUntil = root.attrib['validUntil']

    for item in root.iter("{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor"):
        
        standalone = createStandaloneFragment(item, validUntil)
        entityId = item.attrib['entityID']

        xml = signFragment(standalone, our_key, our_cert)
        doc = createDocument(xml, id, validUntil)
        updateDynamoDb(entityId, "InCommon", doc)
 
    return 0

def createStandaloneFragment(node, validUntil):
    copy = deepcopy(node)
    copy.attrib['ID'] = str(uuid.uuid4())
    copy.attrib['cacheDuration'] = 'P0Y0M0DT6H0M0.000S'
    copy.attrib['validUntil'] = validUntil
    return copy

def signFragment(fragment, key, cert):
    fragment.insert(0, etree.Element("Signature", Id="placeholder", nsmap=NSMAP))
    return signxml.XMLSigner().sign(fragment, key=key, cert=cert)

def createDocument(fragment, id, validUntil):
    return etree.tostring(fragment, pretty_print=False, xml_declaration=True, encoding='UTF-8', standalone='no')    

def updateDynamoDb(entityId, provider, document):
    #try:
        response = dynamodb.update_item(
            TableName='metadata',
            Key={"entityID": {"S": entityId} },
            UpdateExpression='SET metadata=:metadata, provider=:provider, last_updated=:last_updated',
            ExpressionAttributeValues={
                ":metadata" : {"S": document},
                ":provider" : {"S": provider}, 
                ":last_updated" : {"N": "5"}
            })

        return response
    #except botocore.exceptions.ClientError as e:
    #    pass

def getFile(filename):
    response = s3.get_object(Bucket="mdq-server", Key=filename)
    return response['Body'].read()

