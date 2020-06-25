#!/bin/bash
docker-compose build
docker-compose run buildpack
docker-compose down