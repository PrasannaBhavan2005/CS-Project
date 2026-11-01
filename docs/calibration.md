# Emulator calibration

Does each emulated path deliver the delay, rate and buffer it is configured
for? Checked on 1 Nov 2026, before any experiment, as required by
`docs/proposal.md` section 4. Every number below comes from
`results/calibration/` and is reproduced by:

```bash
analysis/.venv/bin/python analysis/calibration.py results/calibration/<scenario>/<run_id> ...
```

## Method

`testbed/calibrate.sh <scenario> <run_id>` builds the scenario, then for each
path (both paths at the same time):

- **Delay:** 100 unloaded pings at 10 Hz, client -> server, compared with the
  configured RTT.
- **Rate:** iperf3 UDP, client -> server (the data direction), 1200-byte
  payload, offered at 1.5x the path's highest configured rate so the bottleneck
  queue stays full. The receiver's 100 ms bins are converted to wire bytes
  (payload + 42 B per datagram: UDP 8, IPv4 20, Ethernet 14; the shaper counts
  the Ethernet header, checked with `tc -s`: 4,052,986 bytes in 3,373 packets
  on cA in symmetric/2, nearly all of them 1242-byte datagrams). The first 1 s
  (queue filling), the last bin and anything logged after the test's
  duration are left out. For outage and real_pairs the
  configured rate per bin comes from the replay log, and iperf3's clock is
  aligned to it by the shift (searched over -1..+1 s) that minimises the mean
  absolute error; the shift is reported.
- **Buffer:** pings during the rate test (5 Hz), compared with RTT + 200 ms.

Trace replay uses `traces/public_mahimahi/` (public US uplink traces; RTTs 40
and 60 ms are configured, not measured), at three offsets into the traces.
Our own traces will be checked the same way once recorded.

## Result (shaper: netem -> htb -> plug, repo 3b9f8e2)

Error = (measured - configured) / configured, given as p5 / median / p95.

| run | path | RTT cfg | ping min / med | rate cfg (mean) | measured mean | 100 ms bins | 1 s windows | shift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| control/3 | A | 40 ms | 40.1 / 40.3 ms | 4000 kbit/s | 4000 | -2.3 / -0.6 / +1.9% | -0.2 / +0.1 / +0.1% | |
| | B | 40 ms | 40.1 / 40.4 ms | 4000 kbit/s | 4000 | -1.5 / -0.6 / +1.9% | -0.2 / -0.1 / +0.1% | |
| symmetric/4 | A | 40 ms | 40.1 / 40.3 ms | 1600 kbit/s | 1599 | -6.8 / -0.6 / +5.6% | -0.6 / -0.0 / +0.6% | |
| | B | 40 ms | 40.1 / 40.3 ms | 1600 kbit/s | 1600 | -2.5 / -0.6 / +5.6% | -0.0 / -0.0 / +0.6% | |
| rtt_asym/3 | A | 30 ms | 30.1 / 30.3 ms | 1600 kbit/s | 1599 | -0.8 / -0.6 / +5.6% | -0.5 / -0.0 / +0.5% | |
| | B | 150 ms | 150.0 / 150.0 ms | 1600 kbit/s | 1600 | -0.7 / -0.6 / +5.6% | -0.0 / -0.0 / -0.0% | |
| bw_asym/3 | A | 40 ms | 40.1 / 40.4 ms | 2000 kbit/s | 2000 | -0.8 / -0.6 / +4.3% | -0.1 / -0.1 / +0.4% | |
| | B | 60 ms | 60.1 / 60.3 ms | 1200 kbit/s | 1200 | -0.7 / -0.6 / +7.6% | -0.6 / +0.2 / +0.2% | |
| outage/3 | A | 40 ms | 40.1 / 40.3 ms | 1697 kbit/s | 1697 | -0.7 / -0.6 / +4.9% | -0.1 / -0.1 / +0.5% | +149 ms |
| | B | 60 ms | 60.1 / 60.3 ms | 1697 kbit/s | 1698 | -0.7 / -0.6 / +4.9% | -0.1 / -0.1 / +0.5% | +219 ms |
| real_pairs/10 (offset 0 s) | A | 40 ms | 40.1 / 40.3 ms | 938 kbit/s | 937 | -9.1 / -0.5 / +8.0% | -1.9 / -0.3 / +1.4% | +842 ms |
| | B | 60 ms | 60.1 / 60.3 ms | 555 kbit/s | 563 | -17.2 / +0.0 / +41.3% | -3.3 / +0.3 / +19.5% | +662 ms |
| real_pairs/8 (offset 300 s) | A | 40 ms | 40.1 / 40.3 ms | 990 kbit/s | 988 | -12.6 / -0.1 / +7.6% | -1.2 / -0.3 / +2.7% | +112 ms |
| | B | 60 ms | 60.1 / 60.3 ms | 657 kbit/s | 658 | -21.9 / -0.5 / +17.9% | -5.2 / -0.4 / +10.9% | +182 ms |
| real_pairs/9 (offset 600 s) | A | 40 ms | 40.1 / 40.3 ms | 944 kbit/s | 943 | -8.1 / -0.2 / +6.2% | -1.5 / -0.2 / +0.6% | +96 ms |
| | B | 60 ms | 60.1 / 60.3 ms | 1295 kbit/s | 1294 | -5.2 / -0.6 / +5.2% | -0.5 / -0.1 / +0.4% | +166 ms |

Zero-rate bins (configured 0): outage/3, 19 bins per path, measured 0 in every
bin. real_pairs: measured median 0, maximum 298-398 kbit/s (3-4 packets in one
bin; 234 such bins on path B of run 10). These are probably bins next to a
change, where a residual misalignment of a few tens of ms moves packets across
the bin edge; not verified further.

Buffer (runs rtt_asym/4 and bw_asym/4, loaded ping median vs RTT + 200 ms):
rtt_asym A 229.0 ms (230), B 349.0 ms (350); bw_asym A 239.0 ms (240),
B 259.0 ms (260). Rates in those runs: within 0.2% of configured on average.

### Reading

- **Delay:** unloaded RTT is 0.1-0.4 ms above the configured value at the
  median on every path (150 ms path: 0.0 ms).
- **Rate, static paths:** the mean is within 0.2% of configured. Single 100 ms
  bins vary by about one packet (one 1242-byte packet is 6.2% of a 100 ms bin at
  1.6 Mbit/s), 1 s windows by at most 0.6%.
- **Rate, outage:** mean within 0.1%; outage bins carry nothing; full rate in
  1 s windows outside outages.
- **Rate, trace replay:** the mean follows the trace within 1.5% (run 10,
  path B: +1.4%, 563 vs 555 kbit/s; every other path within 0.3%). The 1 s
  spread is wider on path B of runs 8 and 10 (p95 +10.9% and +19.5%): these
  stretches of the T-Mobile trace are mostly zero bins and one- or two-packet
  bins (run 10, B: 234 of 590 bins at zero), so one packet more or less is a
  large relative error. At the rates of the static scenarios (>= 1.2 Mbit/s)
  the 1 s error is within +-0.6%.
- **Buffer:** 200 ms within 1 ms.
- **Overhead:** the shaper counts Ethernet headers. A replayed trace (IP-level
  rate, see `docs/trace_collection.md`) therefore gives QUIC about 1.1% less
  than the phone measured (14 B per ~1250 B packet), the same for every
  scheduler.

Verdict: the emulator delivers the configured delay, rate and buffer closely
enough for the experiments. The remaining limit is trace replay at very low
rates, where per-second capacity is only a few packets.

## What did not work first (kept in results/calibration/)

1. **tbf shaper** (runs symmetric/1-2, control/1, rtt_asym/1, bw_asym/1,
   outage/1, real_pairs/1-3; repo c9fadae + the then-uncommitted
   calibrate.sh). Static scenarios were as accurate as above, but trace replay
   delivered too much: mean 1071 vs 935 kbit/s (A) and 659 vs 570 (B) in
   run 1; 1 s median error +8.5% to +24.9% over the six paths. Cause, from the
   Linux 6.18 source: `tbf_change()` sets `q->tokens = q->buffer`, so every
   rate change (up to 10 per second) hands out a full extra burst. The old
   design's trace replay (archived) used the same method.
2. **htb with 8 kbit/s for zero bins** (runs symmetric/3, control/2,
   rtt_asym/2, bw_asym/2, outage/2, real_pairs/4-6; repo b3ed1f6). Overshoot
   gone, but paths stalled after zero bins: 1 s p5 error -44% to -100% in
   runs 4 and 5, run 4 path B mean 455 vs 563 kbit/s, outage 1 s p5 -10.6% and
   -17.8%. Cause: htb keeps token debt in time; one 1242-byte packet sent at
   8 kbit/s costs 1.24 s of debt, still owed after the rate comes back. Fix:
   rate 0 blocks the plug qdisc, so no packet is sent and htb's tokens stay
   untouched.
3. **Failed runs:** real_pairs/7 (offset 0 s): the path-B iperf3 client
   exited with "control socket has closed unexpectedly" and the script stopped
   before writing meta.env; not analysed. At this offset both traces start with
   zero bins and B is zero most of the time, which starves iperf3's TCP control
   connection on the same path. calibrate.sh now records the exit code
   instead of stopping. real_pairs/10 (same offset) hit the same client error
   (IPERF_EXIT_B=1) but the server-side log is complete and is what the
   analysis uses (after the test, that server logged about 40 s of empty
   intervals, which the analysis leaves out); run 10 was taken with calibrate.sh changed only by that
   exit-code handling (meta.env: 3b9f8e2-dirty).
