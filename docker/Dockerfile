# Thunderbird Website Apache Container
#
# Build modes:
#   Local/Dev:   docker build -t thunderbird-web .
#                (clones libs, installs deps, runs tests, builds all sites)
#
#   Production:  docker build --build-arg BUILD_ENV=prod -t thunderbird-web .
#   Staging:     docker build --build-arg BUILD_ENV=stage -t thunderbird-web .
#                (clones from tb-website-builds, no local build)

FROM quay.io/centos/centos:stream9

ARG BUILD_ENV=local

# Install packages (python3.11 for building, python3 for mod_wsgi runtime)
RUN dnf install -y epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf install -y httpd mod_ssl python3 python3-pip python3-mod_wsgi python3-libs python3.11 python3.11-pip git npm \
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

# Copy source files (needed for local builds)
COPY . /build/

# For local builds: build the websites from source using a venv
RUN if [ "$BUILD_ENV" = "local" ]; then \
      echo "BUILD_ENV=local - building websites from source..." \
      && cd /build \
      && mkdir -p libs \
      && git clone --depth 1 https://github.com/thunderbird/thunderbird.net-l10n.git libs/locale \
      && git clone --depth 1 -b production https://github.com/mozilla-releng/product-details.git libs/product-details \
      && git clone --depth 1 https://github.com/thunderbird/thunderbird-notes.git libs/thunderbird_notes \
      && git clone --depth 1 https://github.com/thunderbird/roadmaps-overview.git libs/thunderbird_roadmaps \
      && npm install -g less \
      && python3.11 -m venv /build/venv \
      && /build/venv/bin/pip install --upgrade pip \
      && /build/venv/bin/pip install -r requirements-dev.txt \
      && /build/venv/bin/python build-site.py \
      && /build/venv/bin/python build-site.py --startpage \
      && /build/venv/bin/python build-site.py --updates \
      && /build/venv/bin/python build-site.py --tbpro \
      && /build/venv/bin/python build-site.py --roadmaps \
      && cp -r /build/dist/www.thunderbird.net /var/www/html/start/thunderbird.net \
      && cp -r /build/dist/start.thunderbird.net /var/www/html/start/site \
      && cp -r /build/dist/updates.thunderbird.net /var/www/html/start/updates.thunderbird.net \
      && cp -r /build/dist/tb.pro /var/www/html/start/tb.pro \
      && cp -r /build/dist/roadmaps.thunderbird.net /var/www/html/start/roadmaps.thunderbird.net \
      && cp /build/wsgi.py /var/www/html/start/wsgi.py \
      && cp /build/settings.py /var/www/html/start/settings.py \
      && cp -r /build/media /var/www/html/start/thunderbird.net/media \
      && echo "Done building websites"; \
    fi

# For prod/stage: clone tb-website-builds (includes wsgi.py, settings.py, media)
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

# Set permissions (only log dir needs write access, web files are world-readable)
RUN chown -R apache:apache /var/log/httpd/autoconfig
RUN rm -f /etc/httpd/conf.d/welcome.conf /etc/httpd/conf.d/autoindex.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf -H "Host: www.thunderbird.net" http://localhost/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
