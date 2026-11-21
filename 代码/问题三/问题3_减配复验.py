"""逐情景施加减配库存，复验低峰值排程并比较旧版指标。"""
import argparse
import json
from pathlib import Path

from 问题3_低峰值排程 import OUTPUT
from 问题3_排程 import DEFAULT_OUTPUT, SCENARIOS
from 问题3_复核 import read_rows, source_limits, verify_case

BASELINE = DEFAULT_OUTPUT / "复核结果.json"


def fleet_peaks(case_result, resource):
    return {
        runway: values
        for key, values in sorted(case_result["车人峰值"].items())
        for runway, kind in [key.split("/")]
        if kind == resource
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"]
    parking, original_stock = source_limits()
    rows = {}
    for scene, (_, stations) in SCENARIOS.items():
        stock = {station: vehicles.copy() for station, vehicles in original_stock.items()}
        caps = dict(zip((f"F{station}" for station in stations), (9, 5, 5)))
        for runway, cap in caps.items():
            stock[runway]["Z2"] = cap
        low = verify_case(args.output / scene, scene, 45, parking, stock)
        for metric in ("完工分钟", "跨跑道调动", "最长保障", "休息后最小余量", "停机峰值"):
            if low[metric] != baseline[scene][metric]:
                raise ValueError(f"{scene} {metric} 与基线不一致")
        old = fleet_peaks(baseline[scene], "Z2")
        new = fleet_peaks(low, "Z2")
        b_fuel_wait = []
        # 充足的B机开工余量通过原题时限与73分钟关键路径获得。
        landing_rows = read_rows(args.output / scene, "着陆与放飞")
        touchdown = {(row["波次"], row["批次"], row["飞机编号"]): float(row["着陆时刻"])
                     for row in landing_rows}
        for row in read_rows(args.output / scene, "逐机工序"):
            if row["再次出动保障工序"] != "0204" or row["机型"] != "B":
                continue
            key = (row["波次"], row["批次"], row["飞机编号"])
            b_fuel_wait.append(
                float(row["工序开始时刻"]) - touchdown[key])
        if max(b_fuel_wait) != 0:
            raise ValueError(f"{scene} B型机加油开工被延后")
        rows[scene] = {
            "方案": low["场景"], "减配条件复验": "PASS", "完工分钟": low["完工分钟"],
            "跨跑道调动": low["跨跑道调动"], "基线Z2峰值": old, "减配Z2库存": caps, "新版Z2峰值": new,
            "旧各站Z2峰值之和": sum(old.values()), "新各站Z2峰值之和": sum(new.values()),
            "最少保障余量": 80 - low["最长保障"], "旧A机最长保障": baseline[scene]["A机最长保障"],
            "新A机最长保障": low["A机最长保障"], "B机最长保障": low["B机最长保障"],
            "B机最迟加油开工余量": 7 - max(b_fuel_wait),
            "起飞到下波着陆最少额外余量": low["最短上空等待"], "休息后最小余量": low["休息后最小余量"],
        }
        print(f"{scene} PASS | {old} → {new} | 完工 K+{low['完工分钟']:.0f} 分钟")
    (args.output / "减配对照.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")


if __name__ == "__main__":
    main()
