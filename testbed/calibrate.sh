#!/usr/bin/env bash
# Emulator calibration for one scenario: does each path deliver the configured
# delay and rate? Results feed docs/calibration.md (analysis/calibration.py).
#
# Usage: testbed/calibrate.sh <scenario> <run_id> [duration_s]   (SITE=... for real_pairs)
#   duration default: 20 s; outage 36 s (covers one outage per path);
#   real_pairs 60 s. Env: OFFSET_MS (replay start in the schedule, default 0).
# Output: results/calibration/<scenario>[_<site>]/<run_id>/ with
#   ping_{A,B}.txt   unloaded ping, 10 Hz for 10 s, client -> server, per path
#   ping_loaded_{A,B}.txt ping during the rate test, 5 Hz for 10 s from its start
#   iperf_{A,B}.json iperf3 server-side report, UDP client -> server, 100 ms bins
#   replay.csv       rate changes (outage, real_pairs)
#   client_{A,B}.txt iperf3 client output (errors)
#   tc_{cli,srv}.txt `tc -s qdisc` after the test (bytes and packets per qdisc)
#   meta.env         scenario state, offered rates, tool versions, git hashes
#
# Rate test: both paths at once, each offered 1.5x its highest configured rate
# so the bottleneck queue stays full and the delivered rate is the link rate.
# Datagrams carry 1200 bytes of payload (QUIC-sized).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
source "$here/common.sh"

scenario=${1:?usage: calibrate.sh <scenario> <run_id> [duration_s]}
run_id=${2:?usage: calibrate.sh <scenario> <run_id> [duration_s]}
case $scenario in
    outage) dflt=36 ;;
    real_pairs) dflt=60 ;;
    *) dflt=20 ;;
esac
dur=${3:-$dflt}
OFFSET_MS=${OFFSET_MS:-0}
PAYLOAD=1200

out=$repo/results/calibration/$scenario${SITE:+_$SITE}/$run_id
[[ -e $out ]] && { echo "calibrate.sh: $out exists; results are never overwritten" >&2; exit 1; }
mkdir -p "$out"

"$here/up.sh" "$scenario"
source "$STATE_FILE"
cleanup() {
    for ns in "$NS_SRV" "$NS_CLI"; do
        for p in $(sudo "$IP" netns pids "$ns" 2>/dev/null); do kill "$p" 2>/dev/null || true; done
    done
}
trap cleanup EXIT

# Unloaded RTT, after one warm-up ping (ARP).
for p in A B; do
    ip_var=CLI_${p}_IP
    nsu "$NS_CLI" ping -q -c 1 -I "${!ip_var}" "$SRV_IP" >/dev/null
    nsu "$NS_CLI" ping -c 100 -i 0.1 -I "${!ip_var}" "$SRV_IP" > "$out/ping_$p.txt" &
done
wait

# Offered rate per path: 1.5x the highest rate the path will be set to.
offered() {
    local p=$1 rate_var=${1}_RATE_KBIT
    if [[ $scenario == real_pairs ]]; then
        python3 -I -c "
import sys; sys.path.insert(0, '$here'); import trace_site
_, paths = trace_site.load('$SITE'); k = paths['$p']['kbit']
n = len(k); s = $OFFSET_MS // 100
print(round(1.5 * max(k[(s + i) % n] for i in range($dur * 10))))"
    else
        echo $(( ${!rate_var} * 3 / 2 ))
    fi
}
off_A=$(offered A); off_B=$(offered B)

nsu "$NS_SRV" iperf3 -s -B "$SRV_IP" -p 5201 -1 -i 0.1 -J --logfile "$out/iperf_A.json" &
nsu "$NS_SRV" iperf3 -s -B "$SRV_IP" -p 5202 -1 -i 0.1 -J --logfile "$out/iperf_B.json" &
sleep 0.5
if [[ $scenario == outage || $scenario == real_pairs ]]; then
    python3 -I "$here/replay.py" "$out/replay.csv" --offset-ms "$OFFSET_MS" --duration-s $(( dur + 2 )) &
    replay_pid=$!
fi
start_us=$(python3 -I -c 'import time; print(round(time.monotonic() * 1e6))')
# iperf3's TCP control connection shares the path; long zero-rate stretches can
# break it, so an iperf3 failure is recorded (meta.env), not fatal.
nsu "$NS_CLI" iperf3 -c "$SRV_IP" -B "$CLI_A_IP" -p 5201 -u -b "${off_A}k" -l $PAYLOAD -t "$dur" > "$out/client_A.txt" 2>&1 &
pid_A=$!
nsu "$NS_CLI" iperf3 -c "$SRV_IP" -B "$CLI_B_IP" -p 5202 -u -b "${off_B}k" -l $PAYLOAD -t "$dur" > "$out/client_B.txt" 2>&1 &
pid_B=$!
# Loaded RTT (queue full): should be about RTT + QUEUE_MS.
for p in A B; do
    ip_var=CLI_${p}_IP
    nsu "$NS_CLI" ping -c 50 -i 0.2 -I "${!ip_var}" "$SRV_IP" > "$out/ping_loaded_$p.txt" &
done
rc_A=0; wait $pid_A || rc_A=$?
rc_B=0; wait $pid_B || rc_B=$?
sleep 1
[[ -n ${replay_pid:-} ]] && { kill "$replay_pid" 2>/dev/null || true; wait "$replay_pid" 2>/dev/null || true; }

nsx "$NS_CLI" tc -s qdisc show > "$out/tc_cli.txt"
nsx "$NS_SRV" tc -s qdisc show > "$out/tc_srv.txt"
{
    cat "$STATE_FILE"
    echo "DURATION_S=$dur"
    echo "OFFSET_MS=$OFFSET_MS"
    echo "PAYLOAD_BYTES=$PAYLOAD"
    echo "OFFERED_A_KBIT=$off_A"
    echo "OFFERED_B_KBIT=$off_B"
    echo "RUN_ID=$run_id"
    echo "IPERF_EXIT_A=$rc_A"
    echo "IPERF_EXIT_B=$rc_B"
    echo "IPERF_START_MONO_US=$start_us"
    echo "REPO_GIT=$(git -C "$repo" rev-parse --short HEAD)$(git -C "$repo" diff --quiet HEAD -- testbed || echo -dirty)"
    echo "KERNEL=$(uname -r)"
    echo "IPERF3=$(iperf3 --version | head -1)"
} > "$out/meta.env"
"$here/down.sh"
echo "calibration data in $out"
