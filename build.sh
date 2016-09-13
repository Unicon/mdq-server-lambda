#!/usr/bin/env bash

if [ "$(uname)" == "Darwin" ]; then
    #Macs binaries in the build aren't really supported, but can be used for testing.
    cp misc/setup.cfg .
fi 

# Remove previous builds
rm -rf build/ dist/

# Pull down dependencies
pip install -r misc/requirements.txt -t build/

# Copy in local src
cp -r src/* build/


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

# Build the archive.
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