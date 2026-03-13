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
ARG REPO_BRANCH=master

# Install packages (python3.11 for building, python3 for mod_wsgi runtime)
RUN dnf install -y epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf module enable nodejs:22 -y \
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

# Clone external repos (branch is passed via --build-arg REPO_BRANCH)
RUN git clone --depth 1 --branch $REPO_BRANCH https://github.com/thunderbird/live-redirects.git /var/www/html/live.momo

RUN git clone --recurse-submodules --branch $REPO_BRANCH https://github.com/thunderbird/broker.git /var/www/services/broker \
    && cp /var/www/services/broker/settings.py.dist /var/www/services/broker/settings.py \
    && cd /var/www/services/broker/lib/pygeoip && /var/www/tbservices/bin/pip install --no-cache-dir .

RUN git clone --depth 1 --branch $REPO_BRANCH https://github.com/thunderbird/http-mx.git /var/www/services/mx \
    && /var/www/tbservices/bin/pip install --no-cache-dir -r /var/www/services/mx/requirements.txt

RUN git clone --depth 1 --branch $REPO_BRANCH https://github.com/thunderbird/stats.git /var/www/html/tbstats

RUN git clone --depth 1 --branch $REPO_BRANCH https://github.com/thunderbird/autoconfig.git /var/www/autoconfig.momo

# Copy config files
COPY docker/scripts/update-autoconfig.sh /var/www/autoconfig.momo/update.sh
RUN chmod +x /var/www/autoconfig.momo/update.sh && /var/www/autoconfig.momo/update.sh

COPY --from=ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 /uv /usr/local/bin/uv

COPY docker/conf/ssl.conf /etc/httpd/conf.d/ssl.conf
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# =============================================================================
# Static files: source depends on BUILD_ENV
# =============================================================================

# Copy source files (needed for local builds)
COPY . /build/

# For local builds: build the websites from source using uv
RUN if [ "$BUILD_ENV" = "local" ]; then \
      echo "BUILD_ENV=local - building websites from source..." \
      && cd /build \
      && uv sync --frozen \
      && uv run pull-libs.py --skip-sync \
      && uv run build-site.py \
      && uv run build-site.py --startpage \
      && uv run build-site.py --updates \
      && uv run build-site.py --tbpro \
      && uv run build-site.py --roadmaps \
      && cp -r /build/dist/www.thunderbird.net  /var/www/html/start/thunderbird.net \
      && cp -r /build/dist/start.thunderbird.net /var/www/html/start/site \
      && cp -r /build/dist/updates.thunderbird.net /build/dist/tb.pro /build/dist/roadmaps.thunderbird.net /var/www/html/start/ \
      && cp /build/wsgi.py /build/settings.py /var/www/html/start/ \
      && cp -r /build/media /var/www/html/start/thunderbird.net/media \
      && echo "Done building websites"; \
    fi

# For prod/stage: clone tb-website-builds (includes wsgi.py, settings.py, media)
RUN if [ "$BUILD_ENV" != "local" ]; then \
      echo "BUILD_ENV=$BUILD_ENV - cloning tb-website-builds branch $REPO_BRANCH..." \
      && rm -rf /var/www/html/start/* \
      && git clone --depth 1 --branch $REPO_BRANCH \
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
