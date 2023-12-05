#!/bin/bash

# Fetch the webpage and extract all PEM file URLs
urls=$(curl https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html | grep -o 'https://truststore.pki.rds.amazonaws.com/[^"]*.pem')

# Loop through each URL and download the file
for url in $urls; do
    echo "Downloading $url ..."
    curl -O $url
done

echo "Download complete!"
