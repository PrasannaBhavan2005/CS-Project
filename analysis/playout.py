"""Playout model and per-run metrics (CLAUDE.md "Measurement definitions").

Frames are in send order. Frame i depends on: every earlier frame
(intra-refresh), or every frame since the last I-frame (periodic keyframes,
gop2). Its lag is

    lag_i = max(complete_j for j in deps(i) and i) - capture_i

(infinite if any of them never completed). With playout delay D, frame i is
on time, and shown, iff lag_i <= D. Everything else follows from the lags:

- on-time ratio at D: share of frames with lag <= D;
- freeze: on the display timeline (capture times), a gap between consecutive
  shown frames of at least max(3 * interval, interval + 150 ms) (190 ms at
  25 fps) is a freeze; freeze time = sum of those gaps. The timeline starts one
  interval before the first frame and ends one interval after the last, so
  missing frames at either end count too;
- required playout delay: the smallest D with >= 99% of frames on time.
"""

import math

FREEZE_EXTRA_US = 150_000


def lags_us(frames, encoding):
    """frames: list of dicts with frame_type, capture_ts_us, complete_ts_us
    (None if never completed), in send order. Returns lag per frame (us,
    math.inf if not decodable)."""
    out = []
    worst = -math.inf  # latest completion among the current dependencies
    for f in frames:
        c = math.inf if f["complete_ts_us"] is None else f["complete_ts_us"]
        if encoding == "gop2" and f["frame_type"] == "I":
            worst = c  # a keyframe resets the dependency chain
        elif encoding in ("gop2", "intra"):
            worst = max(worst, c)
        else:
            raise ValueError(f"unknown encoding {encoding}")
        out.append(worst - f["capture_ts_us"])
    return out


def interval_us(frames):
    t = [f["capture_ts_us"] for f in frames]
    return round((t[-1] - t[0]) / (len(t) - 1))


def freeze_threshold_us(interval):
    return max(3 * interval, interval + FREEZE_EXTRA_US)


def on_time_ratio(lags, d_us):
    return sum(l <= d_us for l in lags) / len(lags)


def freezes(frames, lags, d_us):
    """(freeze count, freeze time in us) at playout delay d_us."""
    iv = interval_us(frames)
    thr = freeze_threshold_us(iv)
    shown = [f["capture_ts_us"] for f, l in zip(frames, lags) if l <= d_us]
    times = [frames[0]["capture_ts_us"] - iv] + shown + [frames[-1]["capture_ts_us"] + iv]
    gaps = [b - a for a, b in zip(times, times[1:])]
    big = [g for g in gaps if g >= thr]
    return len(big), sum(big)


def required_delay_us(lags, share=0.99):
    """Smallest D with at least `share` of frames on time (inf if none)."""
    s = sorted(lags)
    k = math.ceil(share * len(s)) - 1
    return s[k]


def run_metrics(frames, encoding, deadlines_ms=(150, 250, 400)):
    lags = lags_us(frames, encoding)
    dur_us = len(frames) * interval_us(frames)
    m = {"frames": len(frames),
         "complete": sum(f["complete_ts_us"] is not None for f in frames),
         "required_delay_ms": required_delay_us(lags) / 1000}
    for d in deadlines_ms:
        n, t = freezes(frames, lags, d * 1000)
        m[f"on_time_{d}"] = on_time_ratio(lags, d * 1000)
        m[f"freeze_count_{d}"] = n
        m[f"freeze_ms_{d}"] = t / 1000
        m[f"freeze_frac_{d}"] = t / dur_us
    return m, lags
