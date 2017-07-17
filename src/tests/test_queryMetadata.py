import sys
import unittest
import time
import hashlib

from moto import mock_dynamodb2

from src.lambda_scripts.queryMetadata import *


class QueryTestCase(unittest.TestCase):

    def setUp(self):
        """
        setUp will run before execution of each test case
        """
        # TODO need to update url depending on region accessing
        self.dynamo_url = 'https://dynamodb.us-west-1.amazonaws.com'
        self.good_event = {
            'params': {
                'path': {
                    'entityId': 'entityIDValue'
                },
                'header': {
                    'If-None-Match': 'Some vlaue'
                }
            }
        }

        self.no_path_event = {
            'params': {
                'header': {
                    'If-None-Match': 'Some vlaue'
                }
            }
        }

        self.no_ifnone_event = {
            'params': {
                'path': {
                    'entityId': 'entityIDValue'
                },
                'header': ''
            }
        }

    def tearDown(self):
        """
        tearDown will run after execution of each test case
        """
        pass

    def test_verify_params_pass(self):
        """
        Verify all parameters passed in from event dictionary are present and accounted for
        """

        event = verify_params(self.good_event)
        self.assertTrue(event)

    def test_verify_params_no_path(self):
        """
        Verify parameters passed in event dict are present but NO EntityId info
        """
        with self.assertRaises(Exception) as exit_code:
            event = verify_params(self.no_path_event)
            self.assertEqual(exit_code.exception.error_code, '304')

    def test_verify_params_no_ifnone(self):
        """
        Verify parameters passed in event dict are present but NO header info
        """
        with self.assertRaises(Exception) as exit_code:
            event = verify_params(self.no_ifnone_event)
            self.assertEqual(exit_code.exception.error_code, '304')

    @mock_dynamodb2
    def test_get_dynamodb_client_success(self):
        """
        Checks endpoint of get_dynamodb_client function
        """
        dyna_db = get_dynamodb_client()
        self.assertEqual(dyna_db._endpoint.host, self.dynamo_url)

    @mock_dynamodb2
    def test_get_db_record(self):
        """
        Build db and record and then verify can pull correctly
        """

        dynamo_db = get_dynamodb_client()
        new_table = self._create_db_table(dynamo_db)

        etag_one = hashlib.md5('safdfowuwer0uw'.encode()).hexdigest()
        item_one = {
            'entity_id': 'https://ci.unicon_test.net/shibboleth',
            'document': 'New document to capture',
            'provider': 'Provider One',
            'etag': etag_one,
            'timestamp': '1499805012.394676'
        }

        response = self._add_to_table(dynamo_db, item_one)

        print('first record added: ', response)

        etag_two = hashlib.md5('asfwerwercfw'.encode()).hexdigest()
        item_two = {
            'entity_id': 'https://ci.unicon_test_two.net/shibboleth_two',
            'document': 'Another New document to capture',
            'provider': 'Provider Two',
            'etag': etag_two,
            'timestamp': '1499805035.394676'
        }

        response_two = self._add_to_table(dynamo_db, item_two)
        print('second record added: ', response_two)

        dynamo_db_new = get_dynamodb_client()
        result = get_db_record(dynamo_db_new, 'https://ci.unicon_test.net/shibboleth')

        self.assertEqual(etag_one, result)

    @mock_dynamodb2
    def test_get_db_record_bad_entity_id(self):
        """
        Build db and then verify can capture error when no record in db for fictitious entityId
        """

        dynamo_db = get_dynamodb_client()
        new_table = self._create_db_table(dynamo_db)

        etag_one = hashlib.md5('safdfowuwer0uw'.encode()).hexdigest()
        item_one = {
            'entity_id': 'https://ci.unicon_test.net/shibboleth',
            'document': 'New document to capture',
            'provider': 'Provider One',
            'etag': etag_one,
            'timestamp': '1499805012.394676'
        }

        response = self._add_to_table(dynamo_db, item_one)

        print('first record added: ', response)

        etag_two = hashlib.md5('asfwerwercfw'.encode()).hexdigest()
        item_two = {
            'entity_id': 'https://ci.unicon_test_two.net/shibboleth_two',
            'document': 'Another New document to capture',
            'provider': 'Provider Two',
            'etag': etag_two,
            'timestamp': '1499805035.394676'
        }

        response_two = self._add_to_table(dynamo_db, item_two)
        print('second record added: ', response_two)

        dynamo_db_new = get_dynamodb_client()
        result = get_db_record(dynamo_db_new, 'https://ci.unicon_test_two.net/shibboleth_WRONG')

        self.assertNotEqual(etag_one, result)

    def _create_db_table(self, dynamo_db):
        """
        Method to build dynamo db for testing.

        :return: newly created table
        """

        new_table = dynamo_db.create_table(
            AttributeDefinitions=[
                {
                    'AttributeName': 'entityID',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'metadata',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'provider',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'etag',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'changed',
                    'AttributeType': 'N'
                }
            ],
            TableName='metadata',
            KeySchema=[
                {
                    'AttributeName': 'entityID',
                    'KeyType': 'HASH'
                },
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        time.sleep(5)

        status = dynamo_db.describe_table(
            TableName='metadata'
        )

        self.assertEqual(status['Table']['TableStatus'], 'ACTIVE', 'Error creating mocked database table ')

        return new_table

    def _add_to_table(self, dynamo_db, data_to_add):
        """
        Add record to newly created table in dynamo
        """

        response = dynamo_db.put_item(
            TableName='metadata',
            Item={
                'entityID': {
                    "S": data_to_add['entity_id'],
                },
                'metadata': {
                    "S": data_to_add['document'],
                },
                'provider': {
                    "S": data_to_add['provider'],
                },
                'etag': {
                    "S": data_to_add['etag'],
                },
                'changed': {
                    "N": data_to_add['timestamp'],
                },
            },
        )
        return response


if __name__ == '__main__':
    unittest.main()
