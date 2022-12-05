FROM python:2.7.18-slim-buster

RUN apt-get update && apt-get install -y apache2 apache2-dev python2 libapache2-mod-wsgi

# Make a few default directories that apache complains about
RUN mkdir -p /var/www/html/
RUN mkdir -p /var/www/html/live.momo/htaccess/
RUN mkdir -p /var/www/html/autoconfig.momo/
RUN mkdir -p /var/www/services/broker/
RUN mkdir -p /var/www/services/mx/
RUN mkdir -p /var/www/html/start/site/
RUN mkdir -p /var/www/html/start/thunderbird.net/
RUN mkdir -p /var/www/html/tbstats/docs/
RUN mkdir -p /var/www/html/style_guide/_site/
RUN mkdir -p /var/www/html/statictest/www/
RUN mkdir -p /var/www/html/start/site/en-US/maintenance/
RUN mkdir -p /var/www/tbservices/

# Log directory
RUN mkdir -p /etc/apache2/logs/
# SSL directory
RUN mkdir -p /etc/apache2/ssl/

# Generate SSL certs
RUN openssl genrsa -out /etc/apache2/ssl/ssl.key 3072
RUN openssl req -new -out /etc/apache2/ssl/ssl.csr -sha256 -key /etc/apache2/ssl/ssl.key -subj "/C=CA/CN=*.thunderbird.test"
RUN openssl x509 -req -in /etc/apache2/ssl/ssl.csr -days 3650 -signkey /etc/apache2/ssl/ssl.key -out /etc/apache2/ssl/ssl.crt -outform PEM

# Setup our virtualenv
RUN pip install virtualenv
RUN virtualenv -p python2.7 /var/www/tbservices/
# Install some libs into our virtualenv
RUN /var/www/tbservices/bin/pip install requests webob lib

# Enable some additional mods
RUN a2enmod socache_shmcb
RUN a2enmod rewrite
RUN a2enmod headers
RUN a2enmod expires
RUN a2enmod ssl

# Create a symlink so we can get docker logs working
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/other_vhosts_access.log

# Boot apache
EXPOSE 80
EXPOSE 443
CMD ["apachectl", "-D", "FOREGROUND"]