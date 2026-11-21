#!/bin/sh
set -eu
cd "$(dirname "$0")"
output=${1:-"results/问题3专项"}
figures=${2:-"figures/问题3专项"}
export MPLCONFIGDIR=${MPLCONFIGDIR:-"${TMPDIR:-/tmp}/q3-matplotlib"}
python 问题3_排程.py --output "$output" --excel
python 问题3_复核.py --output "$output" --excel
python 问题3_图表.py --source "$output" --output "$figures"
