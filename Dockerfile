FROM python:2.7.18-slim-buster as Build
WORKDIR /website
COPY . .

# Dependacies
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g less

# Pull down some gits
#RUN git clone https://github.com/thundernest/thunderbird-notes.git thunderbird_notes
#RUN git clone -b production https://github.com/mozilla-releng/product-details.git
RUN pip install -r requirements-dev.txt

RUN mkdir -p /srv/www/site/
RUN mkdir -p /srv/www/site/en-US/maintenance/
RUN mkdir -p /srv/www/thunderbird.net/

#CMD ["/usr/bin/python", "build-site.py", "--enus", "--watch"]
#RUN python build-site.py --enus
EXPOSE 8000

