#!/usr/bin/env bash
# Verify the running testbed: per path, measure RTT with ping and rate with a
# 5 s iperf3 TCP download, and print them next to the configured values.
# Usage: testbed/check.sh        (after testbed/up.sh)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/common.sh"
[[ -f $STATE_FILE ]] || { echo "check.sh: no testbed; run testbed/up.sh" >&2; exit 1; }
source "$STATE_FILE"

trap 'for p in $(sudo "$IP" netns pids "$NS_SRV"); do kill "$p" 2>/dev/null || true; done' EXIT

printf "%-5s %10s %10s %12s %12s\n" path rtt_cfg rtt_meas rate_cfg rate_meas
for p in A B; do
    ip_var=CLI_${p}_IP; rate_var=${p}_RATE_KBIT; rtt_var=${p}_RTT_MS
    # Warm-up ping first so ARP resolution is not counted in the RTT.
    nsx "$NS_CLI" ping -q -c 1 -I "${!ip_var}" "$SRV_IP" >/dev/null
    rtt=$(nsx "$NS_CLI" ping -q -c 5 -i 0.2 -I "${!ip_var}" "$SRV_IP" | awk -F/ '/^rtt/ {print $5}')
    # Download direction (-R): server -> client, like the file transfer.
    nsu "$NS_SRV" iperf3 -s -B "$SRV_IP" -D --one-off
    sleep 0.3
    mbps=$(nsu "$NS_CLI" iperf3 -c "$SRV_IP" -B "${!ip_var}" -R -t 5 -J \
        | python3 -I -c 'import json,sys; print(round(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e6, 2))')
    printf "%-5s %8sms %8sms %8skbit %7sMbit\n" "$p" "${!rtt_var}" "$rtt" "${!rate_var}" "$mbps"
done
