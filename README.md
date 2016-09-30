# mdq-server-lambda
An AWS Lambda-based metadata query (mdq) server implementation

This is a very alpha/POC version. Use at your own risk!

# Building

Lambda is particular about the version of .so files installed by pip. This requires that the project be build in an AWS AMI. While you can build on OS X, that archive will not execute after being pushed to AWS. You'll have an easier time starting an EC2 isntance with the appropriate AMI. See https://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html for supported AMI versions.

From the project directory, run `./build`, then upon seeting `Updating AWS Lambda service`, hit `Ctrl+C`. 

Then run (be sure to change the `<account-id>`):

```
aws lambda create-function \
--function-name reloadMetdata \
--runtime python2.7 \
--role arn:aws:iam::<account-id>:role/lambda_basic_execution \
--handler importInc.handler_name \
--zip-file fileb://dist/mdq-server.zip
```

Upon sequent builds, `./build` can be used exclusively to push updates.

# Preping an AMI 
On a clean AMI, run:

```
sudo pip install --upgrade pip
sudo yum install -y gcc libffi-devel libxml2-devel libxslt-devel openssl-devel 
```

Just to get this documented, seperate Lambda function for query:

```
from __future__ import print_function

import boto3
import json
import urllib

print('Loading function')

def lambda_handler(event, context):
    '''Provide an event that contains the following keys:

      - params.path.entityId: the entityId of the requested entity.
      - params.header.If-None-Match: a previously provided ETag to take advantage of caching.
    '''
    
    if 'params' in event and 'path' in event['params'] and 'entityId' in event['params']['path']:
        entityId = event['params']['path']['entityId']
        entityId = urllib.unquote(entityId)
        print(entityId)
        
        inboundETag = ''
        if 'header' in event['params'] and 'If-None-Match' in event['params']['header']:
            #Striping single quotes until API Gateway Header JSON decoding issue fixed
            inboundETag = event['params']['header']['If-None-Match'].replace('W/','').replace('"','').replace("'",'')
            print(inboundETag)
    
        dynamo = boto3.client('dynamodb')
    
        response = dynamo.get_item(
            TableName='metadata',
            Key={'entityID': {'S': entityId}},
            AttributesToGet=['metadata','etag']
            )
        if 'Item' not in response:
            raise Exception('404')
            
        ETag = response['Item']['etag']['S']
        print(ETag)
        if inboundETag == ETag:
            print("ETag matched")
            raise Exception('304')
        
        metadata = response['Item']['metadata']['S']
        #print(metadata)
        
        return { 'metadata' : metadata, 'headers' : { 'etag': 'W/"{0}"'.format(ETag)}, 'status': '200'}
        #Using single quotes until API Gateway Header JSON decoding issue fixed
        #return { 'metadata' : metadata, 'headers' : { 'etag': "W/'{0}'".format(ETag)}, 'status': '200'}
    
    else:
        raise Exception('404')
        
```