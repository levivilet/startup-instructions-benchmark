#!/usr/bin/env bash
set -euo pipefail
openbox > /tmp/startup-switch-openbox.log 2>&1 &
desktop_pid=$!
trap 'kill "$desktop_pid" 2>/dev/null || true' EXIT
for attempt in {1..100}; do
  if xprop -root _NET_SUPPORTING_WM_CHECK | grep -q 'window id'; then break; fi
  sleep .05
done

mkdir -p results/electron-switches
for switch_set in baseline disable-background-networking disable-http-cache disable-http2 disable-http-cache+disable-http2; do
  sudo --preserve-env=DISPLAY,XAUTHORITY,BENCHMARK_RUN_URL,BENCHMARK_COMMIT \
    python3 scripts/benchmark.py --editor basic-electron --perf "$1" \
      --repeats 10 --switch-set "$switch_set"
  cp results/results.json "results/electron-switches/$switch_set.json"
  rm results/results.json
done
