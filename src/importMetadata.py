"""
Reads an SAML Metadata Aggregrate, validates the signature, splits out each entity descriptor,
re-signs each descriptor and stores in DynamoDb.
"""

from __future__ import print_function
from copy import deepcopy
import datetime
import hashlib
from urllib2 import urlopen
import sys

import botocore
import boto3
from lxml import etree
import pytz
import signxml

NSMAP = {None : "http://www.w3.org/2000/09/xmldsig#"}
DYNAMODB = boto3.client('dynamodb')
S3 = boto3.client('s3')

def lambda_handler(event, context):
    '''
        Updates a Dynamodb metadata table with a SAML metadata feed

        The event object MUST specify:
        - keyBucket: stores the signing validation certificate and signing key and certificate
        - metadataUrl: the url to load the metadata from
        - providerName: the name of the metadata provider (written to the metadata store)
        - providerSigningCert: the signing certificate used to validate the incoming metadata
        - ourSigningCert: the certificate of the private key used to re-sign the split out metadata
        - ourSigningKey: he private key used to re-sign the split out metadata
        - tableName: the destination AWS DynamoDb table acting as the metadata store

        The event object CAN specify:
        - descriptorType ('SPSSODescriptor' or 'IDPSSODescriptor'): process only the given type
    '''

    now = (datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
           - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()

    validate_event_object(event)

    handle = urlopen(event['metadataUrl'])
    md_dom = etree.parse(handle)
    md_root = md_dom.getroot()

    md_cert_pem = read_file_from_s3(event['providerSigningCert'], event['keyBucket'])
    our_cert = read_file_from_s3(event['ourSigningCert'], event['keyBucket'])
    our_key = read_file_from_s3(event['ourSigningKey'], event['keyBucket'])

    xml_signer = signxml.XMLSigner(method=signxml.methods.enveloped,
                                   signature_algorithm=u'rsa-sha256',
                                   digest_algorithm=u'sha256',
                                   c14n_algorithm=u'http://www.w3.org/2001/10/xml-exc-c14n#')

    try:
        asserted_metadata = signxml.XMLVerifier().verify(md_root, x509_cert=md_cert_pem)
        root = asserted_metadata.signed_xml

    except signxml.exceptions.InvalidSignature:
        print("ERROR: signature validation failure")
        sys.exit(5)

    valid_until = root.attrib['validUntil']

    for item in root.iter("{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor"):
        if 'descriptorType' in event and item.find(event['descriptorType']) is not None:
            entity_id = item.attrib['entityID']
            standalone = create_standalone_fragment(item, entity_id, valid_until)

            xml = sign_fragment(standalone, xml_signer, our_key, our_cert)
            doc = create_document(xml)
            update_dynamodb(entity_id, event['providerName'], doc, now)

    return 0

def validate_event_object(event):
    """
        Confirms that the event object has the required data
    """

    required_keys = ['keyBucket', 'metadataUrl', 'ourSigningCert', 'ourSigningKey',
                     'providerName', 'providerSigningCert', 'tableName']

    missing_keys = False

    for required_key in required_keys:
        if required_key not in event:
            print("%s is missing from the event object." % required_key)
            missing_keys = True

    if missing_keys is True:
        sys.exit(6)

    return

def create_standalone_fragment(node, entity_id, valid_until):
    """
        Take an XML node and creates a standalone XML fragment
        - node: the element being worked on
        - entity_id: the entityId of the provider
        - valid_until: the date the metadata is valid until
    """

    id_attribute = hashlib.md5(entity_id).hexdigest()

    copy = deepcopy(node)
    copy.attrib['ID'] = '_' + id_attribute
    copy.attrib['cacheDuration'] = 'P0Y0M0DT6H0M0.000S'
    copy.attrib['validUntil'] = valid_until
    return copy

def sign_fragment(fragment, xml_signer, key, cert):
    """
        Signs the xml fragment using the given signing key and certificate
    """

    fragment.insert(0, etree.Element("Signature", Id="placeholder", nsmap=NSMAP))
    return xml_signer.sign(fragment, key=key, cert=cert)

def create_document(fragment):
    """
        Converts the XML fragment into a standalone XML document
        returned as a string
    """

    doc = etree.tostring(fragment,
                         pretty_print=False,
                         xml_declaration=True,
                         encoding="UTF-8",
                         standalone="no")
    return doc

def update_dynamodb(entity_id, provider, document, timestamp):
    """
        Stores a provider's metdata (XML Document) in DynamoDb
    """

    try:
        etag = hashlib.md5(document).hexdigest()
        response = DYNAMODB.update_item(
            TableName='metadata',
            Key={"entityID":{"S": entity_id}},
            UpdateExpression='SET metadata=:metadata, provider=:provider, etag=:etag, last_changed=:changed, last_seen=:changed',
            ExpressionAttributeValues={
                ":metadata" : {"S": document},
                ":provider" : {"S": provider},
                ":etag" : {"S" : etag},
                ":changed" : {"N": str(timestamp)}
            },
            ConditionExpression="etag <> :etag"
        )

        return response
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':

            # Setting the last seen flag, so we don't delete it even though it hasn't changed.
            response = DYNAMODB.update_item(
                TableName='metadata',
                Key={"entityID":{"S": entity_id}},
                UpdateExpression='SET last_seen=:changed',
                ExpressionAttributeValues={
                    ":changed" : {"N": str(timestamp)}
                },
                ConditionExpression="etag <> :etag"
            )

        print(e.message)

def read_file_from_s3(filename, bucket):
    """
        Reads a document from S3
    """

    response = S3.get_object(Bucket=bucket, Key=filename)
    return response['Body'].read()
