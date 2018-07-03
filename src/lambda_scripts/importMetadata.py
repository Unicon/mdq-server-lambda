"""
Reads in SAML Metadata Aggregate, validates the signature, splits out each entity descriptor,
re-signs each descriptor and stores in DynamoDb.
"""

from __future__ import print_function

import datetime
import hashlib
import sys
from copy import deepcopy

import boto3
import botocore
import pytz
import signxml
from lxml import etree
from urllib.request import urlopen
from botocore import exceptions

NSMAP = {None: "http://www.w3.org/2000/09/xmldsig#"}
URN = '{urn:oasis:names:tc:SAML:2.0:metadata}'


def lambda_handler(event, context):
    """
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

    :param event: data representing the captured activity
    :param context: runtime information for handler
    :type event: dict
    :type context:
    :return: irrelevant to functionality
    :rtype: int
    """
    validate_event_object(event)

    md_cert_pem = read_file_from_s3(event['providerSigningCert'], event['keyBucket'])
    our_cert = read_file_from_s3(event['ourSigningCert'], event['keyBucket'])
    our_key = read_file_from_s3(event['ourSigningKey'], event['keyBucket'])

    handle = urlopen(event['metadataUrl'])
    root = get_and_validate_metadata(handle.read(), md_cert_pem)

    success = store_metadata(root, event, our_key, our_cert)

    # TODO determine where this is going
    if success:
        return 0

    return 0


def validate_event_object(event):
    """
    Validate incoming event by confirming required keys for processing

    :param event: data representing the captured activity
    :type event: dict
    :return: success
    :rtype: bool
    """

    required_keys = ['keyBucket', 'metadataUrl', 'ourSigningCert', 'ourSigningKey',
                     'providerName', 'providerSigningCert', 'tableName']

    missing_keys = False

    for required_key in required_keys:
        if required_key not in event:
            print("%s is missing from the event object." % required_key)
            missing_keys = True

    if missing_keys:
        sys.exit(6)

    return True


def get_and_validate_metadata(metadata, md_cert_pem):
    """
    Validate metadata from event via XML Verifier class

    :param metadata: XML based metadata from provider
    :param md_cert_pem: Provider signing certification
    :type metadata: str
    :type md_cert_pem: str
    :return: Validated XML metadata
    :rtype: byte string
    """

    md_root = etree.fromstring(metadata)

    try:
        asserted_metadata = signxml.XMLVerifier().verify(md_root, x509_cert=md_cert_pem)
        root = asserted_metadata.signed_xml

    except signxml.exceptions.InvalidSignature:
        print("ERROR: signature validation failure")
        sys.exit(5)
    except signxml.exceptions:
        print("ERROR: Some other error occurred")
        sys.exit(5)

    return root


def store_metadata(root, event, our_key, our_cert):
    """
    Save attributes that match the event object's value stored under the 'descriptorType' key

    :param root: root of XML based metadata
    :param event: data representing the captured activity
    :param our_key: Our signing key
    :param our_cert: Our signing certificate
    :type root: byte string
    :type event: dict
    :type our_key: binary
    :type our_cert: string
    :return: success
    :rtype: bool
    """

    now = (datetime.datetime.utcnow().replace(tzinfo=pytz.utc) - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()

    xml_signer = signxml.XMLSigner(method=signxml.methods.enveloped,
                                   signature_algorithm=u'rsa-sha256',
                                   digest_algorithm=u'sha256',
                                   c14n_algorithm=u'http://www.w3.org/2001/10/xml-exc-c14n#')

    valid_until = root.attrib['validUntil']

    if 'descriptorType' in event:
        for item in root.iter(URN + "EntityDescriptor"):
            if item.find(URN + event['descriptorType']) is not None:
                entity_id = item.attrib['entityID']
                standalone = create_standalone_fragment(item, entity_id, valid_until)
                xml = sign_fragment(standalone, xml_signer, our_key, our_cert)
                doc = create_document(xml)
                update_dynamodb(entity_id, event['providerName'], doc, now)

    return True


def create_standalone_fragment(node, entity_id, valid_until):
    """
    Take an XML node and creates a standalone XML fragment

    :param node: the element being worked on
    :param entity_id: the entityId of the provider
    :param valid_until: the date the metadata is valid until
    :type node: XML node
    :type entity_id: string
    :type valid_until: string
    :return: updated XML node
    """

    id_attribute = hashlib.md5(entity_id.encode('utf-8')).hexdigest()

    copy = deepcopy(node)
    copy.attrib['ID'] = '_' + id_attribute
    copy.attrib['cacheDuration'] = 'P0Y0M0DT6H0M0.000S'
    copy.attrib['validUntil'] = valid_until
    return copy


def sign_fragment(fragment, xml_signer, key, cert):
    """
    Signs the xml fragment using the given signing key and certificate

    :param fragment: XML fragment
    :param xml_signer: XML Signature Signer object
    :param key: our signing key
    :param cert: our signing certificate
    :return: Signed fragment
    """

    fragment.insert(0, etree.Element("Signature", Id="placeholder", nsmap=NSMAP))
    return xml_signer.sign(fragment, key=key, cert=cert)


def create_document(fragment):
    """
    Converts the XML fragment into a standalone XML document

    :param fragment: XML standalone node
    :return: string of node
    """

    doc = etree.tostring(fragment,
                         pretty_print=False,
                         xml_declaration=True,
                         encoding="UTF-8",
                         standalone="no")
    return doc


def update_dynamodb(entity_id, provider, document, timestamp):
    """
    Stores a provider's metadata (XML Document) in DynamoDb

    :param entity_id: Entity Id from original XML node
    :param provider: Name of provider of XML metadata
    :param document: XML document of node
    :param timestamp: Time stamp
    :return:
    """

    dynamo_db = get_dynamodb_client()

    try:
        etag = hashlib.md5(document).hexdigest()
        response = dynamo_db.update_item(
            TableName='metadata',
            Key={"entityID": {"S": entity_id}},
            UpdateExpression='SET metadata=:metadata, provider=:provider, etag=:etag, last_changed=:changed, last_seen=:changed',
            ExpressionAttributeValues={
                ":metadata": {"S": document.decode()},
                ":provider": {"S": provider},
                ":etag": {"S": etag},
                ":changed": {"N": str(timestamp)}
            }, ConditionExpression="etag <> :etag"
        )
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
            # Setting the last seen flag, so we don't delete it even though it hasn't changed.
            response = dynamo_db.update_item(
                TableName='metadata',
                Key={"entityID": {"S": entity_id}},
                UpdateExpression='SET last_seen=:changed',
                ExpressionAttributeValues={
                    ":changed": {"N": str(timestamp)}
                },
                ConditionExpression="etag <> :etag"
            )

        print(e.response['Error']['Message'])

    return response


def read_file_from_s3(filename, bucket):
    """
    Reads a document from S3

    :param filename: name of file to read
    :param bucket: S3 bucket to pull from
    :return: data from file
    """
    s3 = get_s3_client()
    try:
        response = s3.get_object(Bucket=bucket, Key=filename)
    except botocore.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print("%s bucket is missing from S3" % bucket)
        elif error_code == 'NoSuchKey':
            print("%s file is missing from bucket %s in S3" % (filename, bucket))
        else:
            print("Unknown Error in getting file %s from %s bucket" % (filename, bucket))
        sys.exit(6)

    return response['Body'].read()


def get_s3_client():
    return boto3.client('s3')


def get_dynamodb_client():
    return boto3.client('dynamodb')
