#!/bin/sh
set -eu
attempt=0
until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 30 ] || exit 1
  sleep 2
done
mc mb --ignore-existing local/apx240-media >/dev/null
mc anonymous set none local/apx240-media >/dev/null
mc admin user add local "$MINIO_APP_USER" "$MINIO_APP_PASSWORD" >/dev/null
mc admin policy create local apx-media /init/policy.json >/dev/null
mc admin policy attach local apx-media --user "$MINIO_APP_USER" >/dev/null
echo 'Private media bucket and scoped service user initialized.'
