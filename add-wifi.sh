#!/bin/sh
# Teach Rocky a Wi-Fi network. Run this ON the board, before you need it:
#   ssh -t rocky './rocky-bench/add-wifi.sh'
#
# NetworkManager keeps one profile per network and connects to whichever it
# can see, so adding your home network here does not disturb the current one.
# You do not need to be in range of the network you are adding.
set -eu

printf 'Network name (SSID): '
read -r SSID
[ -n "$SSID" ] || { echo "add-wifi.sh: SSID cannot be empty" >&2; exit 1; }

printf 'Password (hidden, leave blank for an open network): '
stty -echo 2>/dev/null || true
read -r PSK
stty echo 2>/dev/null || true
printf '\n'

if nmcli -t -f NAME connection show | grep -qx "$SSID"; then
  echo "A profile named '$SSID' already exists. Delete it first with:"
  echo "  sudo nmcli connection delete '$SSID'"
  exit 1
fi

sudo nmcli connection add type wifi con-name "$SSID" ifname wlan0 ssid "$SSID" \
  connection.autoconnect yes

if [ -n "$PSK" ]; then
  sudo nmcli connection modify "$SSID" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK"
fi

echo
echo "Saved. Rocky now knows these networks:"
nmcli -t -f NAME,TYPE connection show | grep 802-11-wireless | cut -d: -f1 | sed 's/^/  /'
echo
echo "He will join whichever one he can see, automatically, at boot."
