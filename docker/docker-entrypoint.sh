#!/bin/bash
set -e

echo "Starting Thunderbird Website Container..."

if [ "$PREVIEW" = "true" ] && [ -n "$PREVIEW_HOST" ] && [ -n "$PREVIEW_SITE" ]; then
    # Lambda: read-only root filesystem, copy configs to /tmp for modification
    mkdir -p /tmp/httpd/conf.d
    cp /etc/httpd/conf/httpd.conf /tmp/httpd/httpd.conf
    cp /etc/httpd/conf.d/*.conf /tmp/httpd/conf.d/

    # Lambda's /etc/passwd doesn't have the 'apache' user; use current UID/GID
    sed -i "s/^User apache/User #$(id -u)/" /tmp/httpd/httpd.conf
    sed -i "s/^Group apache/Group #$(id -g)/" /tmp/httpd/httpd.conf
    sed -i 's|IncludeOptional conf.d/\*.conf|IncludeOptional /tmp/httpd/conf.d/*.conf|' /tmp/httpd/httpd.conf

    # PREVIEW_SITE is the canonical domain (e.g. "tb.pro", "www.thunderbird.net")
    # which matches the ServerName directive in ssl.conf
    sed -i "/ServerName https:\/\/${PREVIEW_SITE}$/a\  ServerAlias ${PREVIEW_HOST}" /tmp/httpd/conf.d/ssl.conf

    echo "Preview mode: ${PREVIEW_HOST} -> ${PREVIEW_SITE} site"
    exec /usr/sbin/httpd -f /tmp/httpd/httpd.conf -D FOREGROUND
fi

exec /usr/sbin/httpd -D FOREGROUND
