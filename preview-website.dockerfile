FROM python:3

RUN apt-get update && apt-get install -y git apache2 apache2-dev npm libapache2-mod-wsgi-py3
RUN npm install -g less

# Copy our Vhost
COPY docker/preview_tb_vhosts.conf /etc/apache2/conf-enabled/tb_vhosts.conf
# Copy our wsgi script
COPY wsgi.py /var/www/html/start/wsgi.py
COPY settings.py /var/www/html/start/settings.py

COPY . /build
WORKDIR /build

# Pre-build setup
RUN rm -rf thunderbird_notes
RUN git clone https://github.com/thundernest/thunderbird-notes.git thunderbird_notes

RUN rm -rf product-details
RUN git clone -b production https://github.com/mozilla-releng/product-details.git

RUN rm -rf locale
RUN git clone https://github.com/thundernest/thunderbird.net-l10n.git locale
RUN l10n_tools/compile.sh

# Build the website!
RUN python -m pip install -r ./requirements.txt
RUN python build-site.py

RUN cp -R /build/thunderbird.net /var/www/html/start/thunderbird.net

# Clean up build files
RUN rm -rf /build

# Create the directory for our wsgi script
RUN mkdir -p /var/www/tbservices/

# Log directory
RUN mkdir -p /etc/apache2/logs/
RUN mkdir -p /var/log/httpd/autoconfig/
# SSL directory
RUN mkdir -p /etc/apache2/ssl/

# Setup our virtualenv
RUN pip install virtualenv
RUN virtualenv -p python /var/www/tbservices/
# Install some libs into our virtualenv
RUN /var/www/tbservices/bin/pip install requests webob lib

# Enable some additional mods
RUN a2enmod socache_shmcb
RUN a2enmod rewrite
RUN a2enmod headers
RUN a2enmod expires
#RUN a2enmod ssl

# Create a symlink so we can get docker logs working
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/other_vhosts_access.log

# Boot apache
EXPOSE 80
#EXPOSE 443
CMD ["apachectl", "-D", "FOREGROUND"]