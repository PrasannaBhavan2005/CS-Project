#!/usr/bin/env bash
# Run a batch of scripts/run.sh calls with one fixed build.
#
# Usage: scripts/batch.sh <tag>
#   Env (space-separated lists): SCENARIOS, CONFIGS, RUN_IDS; and BITRATE
#   (default 2600), ENCODING (default intra), CLIP (default stochastic), SITE.
#
# The streamer binaries are copied to .cache/bin/<tag>/ first (with the repo
# and TQUIC commits), so a rebuild during the batch changes nothing. Runs are
# ordered run_id first, then scenario, then config, so slow drift affects all
# configs alike. Existing run directories are skipped (resume by rerunning).
# A run above 80% CPU (run.sh exit 4) is moved to results/_discarded/ and run
# again once; a stalled run (exit 3) is kept and logged. Log:
# results/batches/<tag>.log (one line per run).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
tag=${1:?usage: batch.sh <tag>}
: "${SCENARIOS:?}" "${CONFIGS:?}" "${RUN_IDS:?}"
BITRATE=${BITRATE:-2600}; ENCODING=${ENCODING:-intra}; CLIP=${CLIP:-stochastic}

bin=$repo/.cache/bin/$tag
if [[ ! -d $bin ]]; then
    if [[ -n $(git -C "$repo" status --porcelain -- streamer scripts testbed analysis workload) ||
          -n $(git -C "$repo/third_party/tquic" status --porcelain -- src) ]]; then
        echo "batch.sh: commit first (the build must match a commit)" >&2; exit 1
    fi
    (cd "$repo/streamer" && cargo build --release 2>&1 | tail -1)
    mkdir -p "$bin"
    cp "$repo/streamer/target/release/mpq_sender" "$repo/streamer/target/release/mpq_receiver" "$bin/"
    { echo "repo=$(git -C "$repo" rev-parse --short HEAD)"
      echo "tquic=$(git -C "$repo/third_party/tquic" rev-parse --short HEAD)"
      echo "built=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > "$bin/BUILD_INFO"
fi
log=$repo/results/batches/$tag.log
mkdir -p "$(dirname "$log")"
echo "# $(date -u +%FT%TZ) start: SCENARIOS='$SCENARIOS' CONFIGS='$CONFIGS' RUN_IDS='$RUN_IDS' $BITRATE $ENCODING $CLIP $(tr '\n' ' ' < "$bin/BUILD_INFO")" >> "$log"

for run_id in $RUN_IDS; do
    for scenario in $SCENARIOS; do
        for config in $CONFIGS; do
            d=results/$scenario${SITE:+_$SITE}/$config/${BITRATE}_${ENCODING}_${CLIP}/$run_id
            [[ -e $repo/$d ]] && { echo "skip $d (exists)" >> "$log"; continue; }
            for attempt in 1 2; do
                t0=$(date +%s)
                BIN=$bin "$here/run.sh" "$scenario" "$config" "$BITRATE" "$ENCODING" "$CLIP" "$run_id" \
                    > "$repo/results/batches/$tag.last.txt" 2>&1
                rc=$?
                echo "$(date -u +%FT%TZ) $d rc=$rc $(( $(date +%s) - t0 ))s $(tail -1 "$repo/results/batches/$tag.last.txt")" >> "$log"
                if (( rc == 4 )); then
                    dst=$repo/results/_discarded/$d.cpu.$(date +%s)
                    mkdir -p "$(dirname "$dst")" && mv "$repo/$d" "$dst"
                    echo "  CPU above 80%: moved to ${dst#$repo/}, rerunning" >> "$log"
                    continue
                fi
                break
            done
        done
    done
done
echo "# $(date -u +%FT%TZ) done" >> "$log"
