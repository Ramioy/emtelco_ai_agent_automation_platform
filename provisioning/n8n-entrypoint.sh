#!/bin/sh
# Provisions the instance, then hands over to n8n's own entrypoint. Provisioning has to happen
# before n8n starts, because n8n registers production webhooks at boot.
set -e

/bin/sh /provisioning/provision-n8n.sh

exec /docker-entrypoint.sh "$@"
