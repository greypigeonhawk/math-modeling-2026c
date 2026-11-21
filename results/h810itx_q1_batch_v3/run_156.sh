#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python 问题1_优化模型.py --limit 120 --fixed-count 156 --time-limit 1200 --workers 14 --output results/q1_corrected_fixed156.csv
printf "RUN_STATUS fixed156=%s\n" "$?"
python 问题1_优化模型.py --limit 120 --reorder --fixed-count 156 --time-limit 1200 --workers 14 --output results/q1_corrected_reordered156.csv
printf "RUN_STATUS reordered156=%s\n" "$?"
