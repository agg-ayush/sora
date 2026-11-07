#!/bin/bash
export PATH="/usr/sbin:/usr/bin:/bin:/sbin"

# Wait up to 3 seconds if DHCP lease is mid-renewal after a location/Wi-Fi switch
PKT=""
for _ in 1 2 3 4 5 6; do
    PKT="$(ipconfig getpacket en0 2>/dev/null)"
    [ -n "$PKT" ] && break
    sleep 0.5
done

# If still mid-transition or no packet yet, only revert if en0 has no IPv4 after waiting
if [ -z "$PKT" ]; then
    exit 0
fi

CUR_LOC="$(networksetup -getcurrentlocation 2>/dev/null)"

if echo "$PKT" | grep -q "NXS62802029"; then
    if [ "$CUR_LOC" != "Home-Excitel" ]; then
        networksetup -switchtolocation "Home-Excitel" >/dev/null 2>&1
        logger -t excitel-location-watcher "Switched to Home-Excitel (MTU 1480, DNS 1.1.1.1)"
    fi
else
    if [ "$CUR_LOC" = "Home-Excitel" ]; then
        networksetup -switchtolocation "Automatic" >/dev/null 2>&1
        logger -t excitel-location-watcher "Switched back to Automatic (MTU 1500, DHCP DNS)"
    fi
fi
