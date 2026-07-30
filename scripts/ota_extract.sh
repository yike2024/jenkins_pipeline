#!/bin/bash
set -e
mkdir -p /data/ota
rm -rf /data/ota/*
tar -xzvf /data/sdcard.tgz -C /data/ota
if [ -d /data/ota/sdcard ]; then
    shopt -s dotglob
    mv /data/ota/sdcard/* /data/ota/
    shopt -u dotglob
    rmdir /data/ota/sdcard 2>/dev/null || rm -rf /data/ota/sdcard
fi
test -f /data/ota/local_update.sh
test -f /data/ota/md5.txt
chmod +x /data/ota/local_update.sh
chown -R linaro:linaro /data/ota /data/sdcard.tgz || true
ls -la /data/ota
