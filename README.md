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