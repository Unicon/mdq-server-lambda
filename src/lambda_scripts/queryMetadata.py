from __future__ import print_function

import sys
from urllib import parse

import boto3
from botocore import exceptions


def lambda_handler(event, context):
    """
    Provide an event that contains the following keys:

    The event object MUST specify:
      - params.path.entityId: the entityId of the requested entity.
      - params.header.If-None-Match: a previously provided ETag to take advantage of caching.

    :param event: data representing the captured activity
    :param context: runtime information for handler, currently not using
    :type event: dict
    :type context:

    :return: metadata information
    :rtype: bool
    """

    verify_params(event)
    dynamo = get_dynamodb_client()

    entity_id = event['params']['path']['entityId']
    entity_id = parse.unquote(entity_id)
    print('Current EntityId: ' + entity_id)

    # Striping single quotes until API Gateway Header JSON decoding issue fixed
    inbound_etag = event['params']['header']['If-None-Match'].replace('W/', '').replace('"', '').replace("'", '')
    print('Current Incoming ETag: ' + inbound_etag)

    db_etag = get_db_record(dynamo, entity_id)

    if inbound_etag == db_etag:
        print("ETags matched!")
        raise Exception('304')

    # TODO who is this returning to?
    # TODO since i am not sure where this was called from and where it is going what kind of error should be sent?
    return {'metadata': metadata, 'headers': {'etag': 'W/"{0}"'.format(db_etag)}, 'status': '200'}
    # Using single quotes until API Gateway Header JSON decoding issue fixed
    # return { 'metadata' : metadata, 'headers' : { 'etag': "W/'{0}'".format(ETag)}, 'status': '200'}


def verify_params(event):
    """
    Verify dictionary keys are in place, grouped all keys needed here.

    :param event: data representing the captured activity
    :type event: dict

    :return: success all keys present
    :rtype: bool
    """
    all_good = True
    message = ''
    if 'params' not in event:
        message = 'The following key was missing: params'
        all_good = False
    elif 'path' not in event['params']:
        message = 'The following key was missing: params->path'
        all_good = False
    elif 'entityId' not in event['params']['path']:
        message = 'The following key was missing: params->path->entityId'
        all_good = False
    elif 'header' not in event['params']:
        message = 'The following key was missing: params->header'
        all_good = False
    elif 'If-None-Match' not in event['params']['header']:
        message = 'The following key was missing: params->header->If-None-Match'
        all_good = False

    if not all_good:
        print(message)
        raise Exception('304')

    return True


def get_db_record(dynamo, entity_id):
    """
    get database record associated with entityId passed in

    :param dynamo: dynamo db handler
    :param entity_id: ID of record trying to get
    :type dynamo: object
    :type entity_id: string

    :return: Record
    """
    try:
        response = dynamo.get_item(
            TableName='metadata',
            Key={'entityID': {'S': entity_id}},
            AttributesToGet=['metadata', 'etag']
        )
    except exceptions.ClientError as e:
        print(e.response['Error']['Code'])
        return ''

    if 'Item' not in response:
        print("No record found for entity_id:", entity_id)
        return ''

    db_etag = response['Item']['etag']['S']
    print('Currently stored ETag: ' + db_etag)
    return db_etag


def get_dynamodb_client():
    return boto3.client('dynamodb')
