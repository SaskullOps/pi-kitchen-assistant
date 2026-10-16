#!/usr/bin/env bash
# usage: build.sh [out_dir]   (default: ./build)
# Generates every workflow JSON from the environment (.env) into out_dir.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
out="${1:-$ROOT/build}"
mkdir -p "$out"
cd "$ROOT/generator"
python3 build_kitchen_router.py > "$out/kitchen-router.json"
python3 build_kitchen_jobs.py "$out"
python3 - "$out" <<'PY'
import glob, json, sys
for f in sorted(glob.glob(sys.argv[1] + "/kitchen-*.json")):
    wf = json.load(open(f))[0]
    print(f"ok {f.split('/')[-1]}: id={wf['id']} nodes={len(wf['nodes'])}")
PY
