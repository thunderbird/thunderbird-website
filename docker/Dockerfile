# Thunderbird Website Apache Container
#
# Build modes:
#   Development: docker build -t thunderbird-web .
#                (run "python build-site.py" first)
#
#   Production:  docker build --build-arg BUILD_ENV=prod -t thunderbird-web .
#   Staging:     docker build --build-arg BUILD_ENV=stage -t thunderbird-web .
#                (clones from tb-website-builds, ignores local dist/)

FROM quay.io/centos/centos:stream9

ARG BUILD_ENV=local

# Install packages
RUN dnf install -y epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf install -y httpd mod_ssl python3 python3-pip python3-mod_wsgi python3-libs git \
    && dnf clean all

# Create directories
RUN mkdir -p /var/www/html/start /var/www/html/live.momo /var/www/autoconfig.momo \
    /var/www/html/autoconfig.momo /var/www/html/autoconfig-temp /var/www/services/broker \
    /var/www/services/mx /var/www/tbservices /var/log/httpd/autoconfig \
    /var/www/html/tbstats /var/www/html/statictest/www /etc/httpd/conf

# Python virtual environment
RUN python3 -m venv /var/www/tbservices \
    && /var/www/tbservices/bin/pip install --no-cache-dir webob dnspython lxml

# Clone external repos
RUN git clone --depth 1 --branch prod https://github.com/thunderbird/live-redirects.git /var/www/html/live.momo

RUN git clone --recurse-submodules --branch prod https://github.com/thunderbird/broker.git /var/www/services/broker \
    && cp /var/www/services/broker/settings.py.dist /var/www/services/broker/settings.py \
    && cd /var/www/services/broker/lib/pygeoip && /var/www/tbservices/bin/pip install --no-cache-dir .

RUN git clone --depth 1 --branch prod https://github.com/thunderbird/http-mx.git /var/www/services/mx \
    && /var/www/tbservices/bin/pip install --no-cache-dir -r /var/www/services/mx/requirements.txt

RUN git clone --depth 1 --branch prod https://github.com/thunderbird/stats.git /var/www/html/tbstats

RUN git clone --depth 1 --branch prod https://github.com/thunderbird/autoconfig.git /var/www/autoconfig.momo

# Copy config files
COPY docker/scripts/update-autoconfig.sh /var/www/autoconfig.momo/update.sh
RUN chmod +x /var/www/autoconfig.momo/update.sh && /var/www/autoconfig.momo/update.sh

COPY docker/conf/ssl.conf /etc/httpd/conf.d/ssl.conf
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# =============================================================================
# Static files: source depends on BUILD_ENV
# =============================================================================

# For local builds: copy from build context (dist/ folder)
# These will be overwritten by clone for prod/stage builds
COPY dist/www.thunderbird.net /var/www/html/start/thunderbird.net
COPY dist/start.thunderbird.net /var/www/html/start/site
COPY dist/updates.thunderbird.net /var/www/html/start/updates.thunderbird.net
COPY dist/tb.pro /var/www/html/start/tb.pro
COPY wsgi.py /var/www/html/start/wsgi.py
COPY settings.py /var/www/html/start/settings.py
COPY media /var/www/html/start/thunderbird.net/media

# For prod/stage: clone tb-website-builds to OVERWRITE the copied files
# Branch mapping: stage -> master, prod -> prod
RUN if [ "$BUILD_ENV" != "local" ]; then \
      if [ "$BUILD_ENV" = "stage" ]; then BUILDS_BRANCH="master"; else BUILDS_BRANCH="prod"; fi \
      && echo "BUILD_ENV=$BUILD_ENV - cloning tb-website-builds branch $BUILDS_BRANCH..." \
      && rm -rf /var/www/html/start/* \
      && git clone --depth 1 --branch ${BUILDS_BRANCH} \
        https://github.com/thunderbird/tb-website-builds.git /var/www/html/start \
      && rm -rf /var/www/html/start/.git \
      && echo "Done cloning tb-website-builds"; \
    fi

# Set permissions
RUN chown -R apache:apache /var/www/html /var/www/services /var/www/autoconfig.momo /var/log/httpd/autoconfig
RUN rm -f /etc/httpd/conf.d/welcome.conf /etc/httpd/conf.d/autoindex.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f -H "Host: www.thunderbird.net" http://localhost/en-US/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
