"""按可周转的充气容量计算第一题156架增援车辆的必要下界。"""
import csv
import json
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
N = 156
WINDOW = 120


def vehicle_bounds(stock, flow, all_aircraft_material=True):
    fixed = flow == "fixed"
    tow = ceil(N / 10)
    meal_window = WINDOW - 15 - (18 if fixed else 15)
    gas_work = 3 * ceil(N / 10)
    parachute_work = 6 * ceil(N / 40) + N / 2
    material_work = 10 * ceil(N / 20) if all_aircraft_material else 0
    z9_deadline = WINDOW - (23 if fixed else 15)
    bounds = {
        "Z1": (ceil(tow * 5 / 6), "16架牵引，按1:1.2配置"),
        "Z2": (ceil(N / ((WINDOW - 23 - (3 if fixed else 0)) // 15)),
               "加油必须在餐食与B段之前，固定流程还须留出充气时间"),
        "Z3": (ceil(gas_work / WINDOW), "每车每批至多10架，充氧需3分钟，可周转"),
        "Z4": (ceil(gas_work / WINDOW), "每车每批至多10架，充氮需3分钟，可周转"),
        "Z5": (ceil(2 * N * 15 / (2 * WINDOW)), "每架两段作业，每辆同时至多服务2架"),
        "Z6": (ceil(2 * N * 15 / (2 * WINDOW)), "每架两段作业，每辆同时至多服务2架"),
        "Z7": (ceil(tow / (WINDOW // 10)), "16架附油，每架需10分钟"),
        "Z8": (ceil(N / (meal_window // 8)), "以最早餐食开始至最晚餐食结束计算单车作业数"),
        "Z9": (ceil((parachute_work + material_work) / z9_deadline),
               "伞勤及其前置航材均占用Z9，固定流程须在餐食前结束，可调流程须在B段前结束"),
    }
    return [dict(flow=flow, all_aircraft_material=all_aircraft_material,
                 vehicle=vehicle, stock=stock[vehicle], required_lower_bound=required,
                 added_lower_bound=max(0, required - stock[vehicle]), basis=basis)
            for vehicle, (required, basis) in bounds.items()]


def main():
    source = json.loads((ROOT / "results/q1_source_tables.json").read_text(encoding="utf-8"))
    stock = {row[0]: int(row[1]) for row in source["m_ground_resources"][2:] if row[0].startswith("Z")}
    rows = []
    for flow in ("fixed", "reordered"):
        for material in (True, False):
            bounds = vehicle_bounds(stock, flow, material)
            rows.extend(bounds)
            print(flow, material, sum(row["added_lower_bound"] for row in bounds))
    output = ROOT / "results/q1_156_vehicle_lower_bounds.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
