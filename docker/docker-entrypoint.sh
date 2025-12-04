#!/bin/bash
set -e

# Thunderbird Website Container Entrypoint
echo "Starting Thunderbird Website Container..."

# Redirect Apache logs to stdout/stderr for container logging
ln -sf /dev/stdout /var/log/httpd/access_log
ln -sf /dev/stderr /var/log/httpd/error_log

# Configure broker API key if provided via environment variable
if [ -n "$MAILFENCE_APIKEY" ]; then
    echo "Configuring broker with Mailfence API key..."
    sed -i "s/^apikey = .*/apikey = '\&api-key=$MAILFENCE_APIKEY'/" /var/www/services/broker/settings.py
fi

# Remove stale Apache pid file if it exists (from previous run)
rm -f /var/run/httpd/httpd.pid

echo "Starting Apache..."

# Start Apache in the foreground
exec /usr/sbin/httpd -D FOREGROUND

