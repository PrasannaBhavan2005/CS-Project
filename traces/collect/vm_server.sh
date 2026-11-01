#!/usr/bin/env bash
# Run on the cloud VM (as root, for tcpdump). One iperf3 server per phone:
# port 5201 for phone A, 5202 for phone B (an iperf3 server serves one test at a
# time). Every test gets its own JSON log with 100 ms receiver-side bins, plus
# the VM-clock time of its first data packet, so the two phones' traces can be
# aligned on one clock.
#
# Usage: sudo ./vm_server.sh [data dir, default ~/traces_raw]
# Stop with Ctrl+C. Files: <dir>/p<port>_<unix time>.json and .first
set -euo pipefail
dir=${1:-$HOME/traces_raw}
mkdir -p "$dir"
serve() {
    local port=$1
    while true; do
        local stamp; stamp=$(date +%s)
        # Arrival time (VM clock, microseconds) of the first UDP packet to this
        # port; iperf3's own timestamps have 1 s resolution.
        # The line starts with the time; make_site.py reads the first field.
        tcpdump -i any -n -c 1 -tt "udp and dst port $port" > "$dir/p${port}_${stamp}.first" 2>/dev/null &
        local dump=$!
        iperf3 -s -p "$port" -1 -i 0.1 -J --logfile "$dir/p${port}_${stamp}.json" || true
        kill "$dump" 2>/dev/null || true
        echo "port $port: test done, $dir/p${port}_${stamp}.json"
    done
}
serve 5201 &
serve 5202 &
wait
