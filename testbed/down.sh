#!/usr/bin/env bash
# Remove the testbed: stop anything running in the namespaces, then delete
# them (deleting a namespace also deletes its veth ends). Safe to rerun.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/common.sh"

for ns in "$NS_CLI" "$NS_SRV"; do
    if ns_exists "$ns"; then
        for pid in $(sudo "$IP" netns pids "$ns"); do
            kill "$pid" 2>/dev/null || true
        done
        sudo "$IP" netns del "$ns"
    fi
done
rm -f "$STATE_FILE"
