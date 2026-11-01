#!/usr/bin/env bash
# Encode a clip the way a live sender would, and write its per-frame trace.
#
# Usage: workload/encode.sh <clip> <intra|gop2> [bitrate_kbps, default 2600]
#   Env: START (seconds into the source; default: start_s in clips.csv),
#        DURATION (default: duration_s in clips.csv).
#
# Both modes (CLAUDE.md "Workload"): x264 zerolatency (no B-frames, no
# lookahead), CBR-style rate control with vbv-maxrate = bitrate and
# vbv-bufsize = 0.5 s of bitrate, 1280x720, the source's own frame rate (no
# frame duplication), 4 threads (fixed, for repeatable output).
#   intra: periodic intra refresh, one column sweep every 2 s; only frame 0 is
#          an I-frame (checked; scene-cut I-frames off).
#   gop2:  an IDR keyframe every 2 s exactly (no scene-cut keyframes).
# No filler data (nal-hrd is off): a live sender does not transmit padding, so
# frames are as large as the rate control makes them, never padded up.
#
# Writes workload/<clip>_<mode>_<kbps>.mp4 (git-ignored), .csv
# (frame_id,frame_type,size_bytes,pts_ms) and .cmd.txt (exact command, tool
# versions, x264 option string from the stream).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
clip=${1:?usage: encode.sh <clip> <intra|gop2> [kbps]}
mode=${2:?usage: encode.sh <clip> <intra|gop2> [kbps]}
kbps=${3:-2600}

eval "$(python3 -I -c "
import csv, sys
for r in csv.DictReader(open('$here/clips.csv')):
    if r['clip'] == '$clip':
        print(f\"id={r['youtube_id']} csv_start={r['start_s'] or ''} csv_dur={r['duration_s']}\"); break
else: sys.exit('encode.sh: no clip $clip in clips.csv')")"
start=${START:-$csv_start}
dur=${DURATION:-$csv_dur}
[[ -n $start ]] || { echo "encode.sh: no start for $clip (set START or start_s in clips.csv)" >&2; exit 2; }
src=$here/src/$id.mp4
[[ -f $src ]] || { echo "encode.sh: $src missing; run workload/download.sh $clip" >&2; exit 1; }

fps=$(ffprobe -v error -select_streams v -show_entries stream=r_frame_rate -of csv=p=0 "$src")
fps_int=$(python3 -I -c "from fractions import Fraction; f = Fraction('$fps'); assert f.denominator == 1, f; print(f.numerator)")
gop=$(( 2 * fps_int ))
case $mode in
    intra) x264p="intra-refresh=1:keyint=$gop:scenecut=0" ;;
    gop2)  x264p="keyint=$gop:min-keyint=$gop:scenecut=0" ;;
    *) echo "encode.sh: mode must be intra or gop2" >&2; exit 2 ;;
esac

name=${clip}_${mode}_${kbps}
out=$here/$name
cmd=(ffmpeg -hide_banner -loglevel error -y -ss "$start" -t "$dur" -i "$src" -an
     -vf "scale=1280:720:flags=bicubic,fps=$fps_int" -pix_fmt yuv420p
     -c:v libx264 -preset veryfast -tune zerolatency -threads 4
     -b:v "${kbps}k" -maxrate "${kbps}k" -bufsize "$(( kbps / 2 ))k"
     -x264-params "$x264p" "$out.mp4")
"${cmd[@]}"

ffprobe -v error -select_streams v -show_entries frame=pict_type,pkt_size,pts_time -of csv=p=0 "$out.mp4" \
    | awk -F, 'BEGIN { print "frame_id,frame_type,size_bytes,pts_ms" }
               NF >= 3 { printf "%d,%s,%d,%d\n", n++, $3, $2, int($1 * 1000 + 0.5) }' > "$out.csv"

if [[ $mode == intra ]]; then
    n_i=$(awk -F, 'NR > 2 && $2 == "I"' "$out.csv" | wc -l)
    (( n_i == 0 )) || { echo "encode.sh: $n_i I-frames after frame 0 in intra mode" >&2; exit 1; }
fi

{
    printf '%q ' "${cmd[@]}"; echo
    echo "source=$src ($(grep sha256 "$here/src/$id.info.txt" 2>/dev/null || echo 'no info file'))"
    echo "start_s=$start duration_s=$dur fps=$fps_int"
    echo "ffmpeg=$(ffmpeg -version | head -1)"
    echo "x264_options=$(strings "$out.mp4" | grep -m1 -o 'x264 - core.*' | head -c 2000)"
} > "$out.cmd.txt"
python3 -I "$here/frame_stats.py" "$out.csv"
