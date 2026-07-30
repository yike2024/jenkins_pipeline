#!/bin/bash
set -e
mkdir -p /data/ota
rm -rf /data/ota/*
echo "解压 /data/sdcard.tgz -> /data/ota"
tar -xzf /data/sdcard.tgz -C /data/ota
if [ -d /data/ota/sdcard ]; then
    echo "检测到 /data/ota/sdcard，移动其中文件到 /data/ota"
    shopt -s dotglob
    mv /data/ota/sdcard/* /data/ota/
    shopt -u dotglob
    rmdir /data/ota/sdcard 2>/dev/null || rm -rf /data/ota/sdcard
fi
test -f /data/ota/local_update.sh || { echo "缺少 /data/ota/local_update.sh"; ls -la /data/ota; exit 1; }
test -f /data/ota/md5.txt || { echo "缺少 /data/ota/md5.txt"; ls -la /data/ota; exit 1; }
chmod +x /data/ota/local_update.sh
chown -R linaro:linaro /data/ota /data/sdcard.tgz || true
echo "OTA 目录内容:"
ls -la /data/ota
