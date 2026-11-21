#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
mkdir -p results/remote_logs
PYTHON="./.venv/bin/python"
run_case() {
  label="$1"; shift
  echo "[$(date -Is)] START $label"
  "$PYTHON" 问题1_优化模型.py "$@" > "results/remote_logs/${label}.log" 2>&1
  rc=$?
  echo "[$(date -Is)] END $label exit=$rc"
  tail -n 20 "results/remote_logs/${label}.log"
}
# Cap at the reported 52 added vehicles first. An OPTIMAL solution at this cap
# also certifies global vehicle-count optimality because the objective minimizes
# total added vehicles before all tie-breakers.
run_case fixed156_120_cap52 --limit 120 --fixed-count 156 --max-added-vehicles 52 --time-limit 1800 --output results/q1_remote_fixed156_cap52.csv
run_case reordered156_120_cap52 --limit 120 --reorder --fixed-count 156 --max-added-vehicles 52 --time-limit 1800 --output results/q1_remote_reordered156_cap52.csv
run_case max100_fixed --limit 100 --time-limit 900 --output results/q1_remote_fixed_max.csv
run_case max100_reordered --limit 100 --reorder --time-limit 900 --output results/q1_remote_reordered_max.csv
