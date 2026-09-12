#!/bin/sh
# Open a shell on Rocky over the USB cable. Needs no network at all, so this is
# the recovery path when Wi-Fi is wrong, missing, or the board took a new
# address you do not know.
#
# Works only while the USB-C port is in device mode. Once the ReSpeaker dongle
# claims that port for USB host mode, this channel is gone and Wi-Fi is the
# only way in. Provision Wi-Fi before that day.
#
# Pass a command to run it and exit; pass nothing for an interactive shell.
set -eu

ROCKY_ADB=${ROCKY_ADB:-/home/ansh/.arduino15/packages/arduino/tools/adb/32.0.0/adb}
ROCKY_ADB_SERIAL=${ROCKY_ADB_SERIAL:-1141166421}

if ! "$ROCKY_ADB" devices | grep -q "^$ROCKY_ADB_SERIAL[[:space:]]*device$"; then
  echo "usb-shell.sh: board not found over USB." >&2
  echo "  Check the cable, then run: $ROCKY_ADB devices" >&2
  echo "  'unauthorized' means confirm the prompt on the board." >&2
  echo "  Nothing listed means the port may be in host mode, or the cable is" >&2
  echo "  charge-only. Try a different USB-C cable." >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  exec "$ROCKY_ADB" -s "$ROCKY_ADB_SERIAL" shell
fi
exec "$ROCKY_ADB" -s "$ROCKY_ADB_SERIAL" shell -t "$*"
