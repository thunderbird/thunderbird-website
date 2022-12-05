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

# Setup our virtualenv
RUN pip install virtualenv
RUN virtualenv -p python2.7 /var/www/tbservices/
# Install some libs into our virtualenv
RUN /var/www/tbservices/bin/pip install requests webob lib

# Create a symlink so we can get docker logs working
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/other_vhosts_access.log

# Enable some additional mods
RUN a2enmod socache_shmcb
RUN a2enmod rewrite
RUN a2enmod headers
RUN a2enmod expires

# Copy over settings.py and wsgi.py
#COPY ./settings.py /var/www/html/start/
#COPY ./wsgi.py /var/www/html/start/
RUN touch /var/www/html/start/__init__.py

# Boot apache
EXPOSE 80
CMD ["apachectl", "-D", "FOREGROUND"]