#!/bin/sh
# Run on the laptop; Python and the model execute on Rocky.
#
# ROCKY_TRANSPORT chooses how we reach the board:
#   ssh (default)  log in over Wi-Fi as $ROCKY_SSH_HOST
#   adb            use the USB debug bridge to $ROCKY_ADB_SERIAL
#
# Use adb only while the USB-C port is free. Once the ReSpeaker occupies that
# port the board runs as a USB host, and the debug bridge is no longer there.
set -eu

ROCKY_TRANSPORT=${ROCKY_TRANSPORT:-ssh}
ROCKY_SSH_HOST=${ROCKY_SSH_HOST:-rocky}
ROCKY_ADB_SERIAL=${ROCKY_ADB_SERIAL:-1141166421}
ROCKY_ADB=${ROCKY_ADB:-/home/ansh/.arduino15/packages/arduino/tools/adb/32.0.0/adb}
ROCKY_DIR=${ROCKY_DIR:-/home/arduino/rocky-bench}
ROCKY_MODEL=${ROCKY_MODEL:-qwen2.5:0.5b}

remote="cd $ROCKY_DIR && python3 rocky.py --model $ROCKY_MODEL"

case "$ROCKY_TRANSPORT" in
  ssh) exec ssh -t "$ROCKY_SSH_HOST" "$remote" ;;
  adb) exec "$ROCKY_ADB" -s "$ROCKY_ADB_SERIAL" shell -t "$remote" ;;
  *)
    echo "chat.sh: ROCKY_TRANSPORT must be 'ssh' or 'adb', got '$ROCKY_TRANSPORT'" >&2
    exit 2
    ;;
esac
