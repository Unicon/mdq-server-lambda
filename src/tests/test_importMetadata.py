import sys
import unittest
import time

from moto import mock_s3, mock_dynamodb2

from src.lambda_scripts.importMetadata import *


class ImportTestCase(unittest.TestCase):

    def setUp(self):
        """
        setUp will run before execution of each test case
        """

        self.bucket = 'Test_Bucket'
        self.file_name = 'KeyName'
        # Will need to update according to s3 location using
        self.s3_url = 'https://s3-us-west-1.amazonaws.com'
        self.dynamo_url = 'https://dynamodb.us-west-1.amazonaws.com'
        self.good_event = {
            'keyBucket': 'what',
            'metadataUrl': 'http://saml.cccmypath.org/metadata/ccc-metadata.xml',
            'ourSigningCert': 'stored in file dummy_our_cert.pem',
            'ourSigningKey': 'stored in file dummy_our_key.key',
            'providerName': 'again',
            'providerSigningCert': 'thisagain',
            'tableName': 'table'
        }
        self.our_cert = self._get_our_cert()
        self.our_key = self._get_our_key()

    def tearDown(self):
        """
        tearDown will run after execution of each test case
        """
        pass

    def test_validate_event_object_pass_dict(self):
        """
        Validates that the event object is a dict and has the required keys
        """
        event = validate_event_object(self.good_event)
        self.assertTrue(event)

    def test_validate_event_object_pass_string(self):
        """
        Validate error handling when event object is not a dict
        """
        with self.assertRaises(SystemExit) as exit_code:
            event = validate_event_object('This is a string')
        self.assertEqual(exit_code.exception.code, 6)

    @mock_s3
    def test_get_s3_client(self):
        """
        Checks endpoint of get_s3_client function
        """
        s3 = get_s3_client()
        self.assertEqual(s3._endpoint.host, self.s3_url)

    @mock_dynamodb2
    def test_get_dynamodb_client(self):
        """
        Checks endpoint of get_dynamodb_client function
        """
        dyna_db = get_dynamodb_client()
        self.assertEqual(dyna_db._endpoint.host, self.dynamo_url)

    @mock_s3
    def test_read_file_from_s3(self):
        """
        Checks read_file_from_s3 function can read file from S3
        """
        #Mock data
        s3_mock = get_s3_client()
        s3_mock.create_bucket(Bucket=self.bucket)
        s3_mock.put_object(Bucket=self.bucket,
                           Key=self.file_name,
                           Body='This is a test of the emergency broadcast system')

        # Function to test
        s3_file_data = read_file_from_s3(self.file_name, self.bucket)
        self.assertEqual(s3_file_data, b'This is a test of the emergency broadcast system')

    @mock_s3
    def test_read_file_from_s3_no_bucket(self):
        """
        Check read_file_from_s3 function catches error when bucket not there
        """
        #Mock Data
        s3_mock = get_s3_client()
        s3_mock.create_bucket(Bucket='NotGoodBucket')
        s3_mock.put_object(Bucket='NotGoodBucket',
                           Key=self.file_name,
                           Body='This is a test of the emergency broadcast system')

        # Function to test
        with self.assertRaises(SystemExit) as exit_code:
            s3_file_data = read_file_from_s3(self.file_name, self.bucket)
        self.assertEqual(exit_code.exception.code, 6)

    @mock_s3
    def test_read_file_from_s3_no_file(self):
        """
        Checks read_file_from_s3 function catches error when file not in bucket
        """
        #Mock Data
        s3_mock = get_s3_client()
        s3_mock.create_bucket(Bucket=self.bucket)
        s3_mock.put_object(Bucket=self.bucket,
                           Key='bad_file_name',
                           Body='This is a test of the emergency broadcast system')

        # Function to test
        with self.assertRaises(SystemExit) as exit_code:
            s3_file_data = read_file_from_s3(self.file_name, self.bucket)
        self.assertEqual(exit_code.exception.code, 6)

    def test_create_standalone_fragment(self):
        pass

    def test_get_and_validate_metadata(self):
        """
        Checks that the function validates a correct xml
        """
        # Need to use URL since file keeps throwing error
        handle = urlopen('http://saml.cccmypath.org/metadata/ccc-metadata.xml')
        dummy_data = handle.read()
        handle.close()

        handle_cert = open('src/tests/dummy_signing_cert.pem', 'r')
        md_cert_pem = handle_cert.read()
        handle_cert.close()

        root = get_and_validate_metadata(dummy_data, md_cert_pem)
        self.assertIsInstance(root, etree._Element)

    def test_get_and_validate_metadata_bad_xml(self):
        """
        Checks that the function does not validate a bad xml file
        """
        handle = open('src/tests/dummy_saml_data.xml', 'r')
        dummy_data = handle.read()
        handle.close()

        handle_cert = open('src/tests/dummy_signing_cert.pem', 'r')
        md_cert_pem = handle_cert.read()
        handle_cert.close()

        with self.assertRaises(SystemExit) as exit_code:
            root = get_and_validate_metadata(dummy_data, md_cert_pem)
        self.assertEqual(exit_code.exception.code, 5)

    @mock_dynamodb2
    def test_store_metadata(self):
        """
        Verify functionality to store metadata is correctly coded
        """

        dynamo_db = get_dynamodb_client()

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

        # first get root
        handle = urlopen('http://saml.cccmypath.org/metadata/ccc-metadata.xml')
        dummy_data = handle.read()
        handle.close()

        handle_cert = open('src/tests/dummy_signing_cert.pem', 'r')
        md_cert_pem = handle_cert.read()
        handle_cert.close()

        root = get_and_validate_metadata(dummy_data, md_cert_pem)

        updated_event = self.good_event
        updated_event['descriptorType'] = 'SPSSODescriptor'

        result = store_metadata(root, updated_event, self.our_key, self.our_cert)
        self.assertTrue(result)

        response = dynamo_db.describe_table(
            TableName='metadata'
        )

        self.assertGreater(response['Table']['ItemCount'], 0)

    @staticmethod
    def _get_our_cert():
        handle_cert = open('src/tests/dummy_our_cert.crt', 'r')
        our_cert = handle_cert.read()
        handle_cert.close()

        return our_cert

    @staticmethod
    def _get_our_key():
        handle_key = open('src/tests/dummy_our_key.key', 'rb')
        our_key = handle_key.read()
        handle_key.close()

        return our_key


if __name__ == '__main__':
    unittest.main()
