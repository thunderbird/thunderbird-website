#!/bin/bash

echo 'pulling locale'
cd libs/locale && git pull
echo 'pulling product details'
cd ../product-details && git pull
echo 'pulling thunderbird notes'
cd ../thunderbird_notes && git pull
echo 'pulling roadmaps'
cd libs/thunderbird_roadmaps && git pull

echo 'done'
