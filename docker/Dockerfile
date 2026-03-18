# Thunderbird Website Apache Container
#
# All environments build from source (including translation compilation).
# BUILD_ENV controls post-build cleanup:
#   local (default): keeps /build so pytest can run inside the container
#   stage/prod:      removes /build to shrink the image
#
# Build modes:
#   Local/Dev:   docker build -t thunderbird-web .
#   Staging:     docker build --build-arg BUILD_ENV=stage -t thunderbird-web .
#   Production:  docker build --build-arg BUILD_ENV=prod -t thunderbird-web .

FROM quay.io/centos/centos:stream9

ARG BUILD_ENV=local
ARG REPO_BRANCH=master

# Install packages (python3.11 for building, python3 for mod_wsgi runtime)
RUN dnf install -y epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf module enable nodejs:22 -y \
    && dnf install -y httpd mod_ssl python3 python3-pip python3-mod_wsgi python3-libs python3.11 python3.11-pip git npm gettext \
    && dnf clean all

# Create directories
RUN mkdir -p /var/www/html/start /var/www/html/live.momo /var/www/autoconfig.momo \
    /var/www/html/autoconfig.momo /var/www/html/autoconfig-temp \
    /var/www/services/mx /var/www/tbservices /var/log/httpd/autoconfig \
    /var/www/html/tbstats /var/www/html/statictest/www /etc/httpd/conf

# Python virtual environment
RUN python3 -m venv /var/www/tbservices \
    && /var/www/tbservices/bin/pip install --no-cache-dir webob dnspython lxml

# Clone external repos (branch is passed via --build-arg REPO_BRANCH)
RUN git clone --depth 1 --branch $REPO_BRANCH https://github.com/thunderbird/live-redirects.git /var/www/html/live.momo

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
# Build websites from source (all environments)
# =============================================================================

COPY . /build/

RUN cd /build \
    && uv sync --frozen \
    && uv run pull-libs.py --skip-sync --notes-branch $REPO_BRANCH \
    && bash l10n_tools/compile.sh \
    && uv run build-site.py --all --debug \
    && cp -r dist/* wsgi.py settings.py /var/www/html/start/ \
    && cp -r media /var/www/html/start/www.thunderbird.net/media

# Stage/prod: clean up build dir to shrink the image
# Local: keep /build so container-test.yml can run pytest
RUN if [ "$BUILD_ENV" != "local" ]; then rm -rf /build; fi

# Set permissions (only log dir needs write access, web files are world-readable)
RUN chown -R apache:apache /var/log/httpd/autoconfig
RUN rm -f /etc/httpd/conf.d/welcome.conf /etc/httpd/conf.d/autoindex.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf -H "Host: www.thunderbird.net" http://localhost/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
