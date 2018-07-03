# Unit Testing
Using libraries:
* Python Unit Test
* Moto - Mocking lib for Boto3 - https://github.com/spulec/moto
* Coverage - Coverage report for Unit testing - https://coverage.readthedocs.io/en/coverage-4.4.1/index.html

# Run Unit Test/s without Coverage
Format:
```
python -m unittest <location of unit test file>.<filename>
```
To run all tests:
```
python -m unittest src.tests.test_importMetadata
```
To run specific test:
```
python -m unittest src.tests.test_importMetadata.<test method name>
example:
python -m unittest src.tests.test_importMetadata.ImportTestCase.test_store_metadata
```

# Run Unit Test/s with Coverage
Format:
```
coverage run -m <location of unit test file>.<filename>
```
To run coverage report (basic):
```
coverage report
```
To run html report:
```
coverage html
(Then access the htmlcov directory to view report in browser.)
```
To delete past coverages:
```
coverage erase
```

**Note: If getting coverage on system libraries, you can omit them via:**
```
coverage html --omit='/<directories ommitting>/*'
```


# Moto Mocking
To mock AWS functionality that is accessed via the 
Python boto3 library, you will have to add the correct 
decorator to the test method

For instance, if mocking a call to S3, use the 
'@mock_s3' decorator. The moto library will then capture 
the test and mock the appropriate boto3 S3 function calls
to AWS.


