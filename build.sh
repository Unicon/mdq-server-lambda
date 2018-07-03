#!/usr/bin/env bash

if [ "$(uname)" == "Darwin" ]; then
    #Macs binaries in the build aren't really supported, but can be used for testing, so adding this file to help
    cp misc/setup.cfg .
fi 

echo "Remove previous builds"
rm -rf build/ dist/

echo "Pull down general dependencies"
pip install -r misc/requirements.txt -t build/

echo "Adding in source code"
cp -r src/* build/

echo "build platform specific dependencies that AWS needs"
pwd="$PWD"
virtualenv builder
source ./builder/bin/activate
pushd builder
./bin/pip install cffi cryptography lxml
pushd lib64/python2.7/site-packages/
cp -r cffi* lxml* cryptography* _cffi* $pwd/build
popd
popd
deactivate

echo "Building the archive"
mkdir dist

pushd build/
zip -r9 ../dist/mdq-server.zip *
popd

rm -f setup.cfg

echo "Updating AWS Lamba service"

aws lambda update-function-code \
--function-name reloadMetadata \
--zip-file fileb://dist/mdq-server.zip

#aws lambda update-function-code \
#--function-name serveMetadata \
#--zip-file fileb://dist/mdq-server.zip