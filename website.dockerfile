FROM python:2.7.18-slim-buster as Build
WORKDIR /website
COPY . .

# Dependacies
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g less

# Pull down some gits
RUN pip install -r requirements-dev.txt

RUN mkdir -p /srv/www/site/
RUN mkdir -p /srv/www/site/en-US/maintenance/
RUN mkdir -p /srv/www/thunderbird.net/

