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
cp -r src/ build/

# Build the archive.
mkdir dist

pushd build/
zip -r ../dist/mdq-server.zip *
popd

rm -f setup.cfg

echo "update AWS Lamba service"

aws lambda update-function-code \
--function-name reloadMetadata \
--zip-file fileb://dist/mdq-server.zip

#aws lambda update-function-code \
#--function-name serveMetadata \
#--zip-file fileb://dist/mdq-server.zip