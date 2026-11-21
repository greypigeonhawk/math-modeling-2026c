"""按同一时段、同技能重新组批，复核已排定的156架保障时刻。"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from 问题1_优化模型 import GAS_BATCH_CAPACITY, PEOPLE, VEHICLES, ceil_div
from 验证第一问排程 import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("resources", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--horizon", type=int, default=120)
    parser.add_argument("--existing-only", action="store_true")
    args = parser.parse_args()
    with args.schedule.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    old = json.loads(args.resources.read_text(encoding="utf-8"))
    jobs = defaultdict(list)
    for row in rows:
        row.setdefault("vehicle_mode", "")
        row.setdefault("vehicle_pair", "")
        if row["aircraft"] == "parachute" and not row["operator_group"]:
            row.update(skill="伞勤", operator_group="M4", skill_level="1")
        if row["aircraft"].isdigit() and row["operation"] in {
            "oxygen", "nitrogen", "power_a", "power_b", "aircon_a", "aircon_b"
        }:
            key = tuple(row[field] for field in (
                "operation", "start_min", "end_min", "skill", "operator_group", "skill_level"))
            jobs[key].append(row)
    for index, (key, members) in enumerate(jobs.items()):
        gas = key[0] in {"oxygen", "nitrogen"}
        capacity = GAS_BATCH_CAPACITY if gas else 2
        for start in range(0, len(members), capacity):
            batch = members[start:start + capacity]
            if gas:
                mode, label = "batch", f"gas_{index}_{start // capacity}"
            elif len(batch) == 2:
                mode, label = "paired", "-".join(str(i) for i in sorted(
                    int(row["aircraft"]) for row in batch))
            else:
                mode, label = "single", ""
            for row in batch:
                row.update(vehicle_mode=mode, vehicle_pair=label)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    resources = args.output.with_name(f"{args.output.stem}_resources.json")
    allocation = {"promoted_skills": old.get("promoted_skills", []),
                  "vehicle_additions": dict.fromkeys(VEHICLES, 200),
                  "people_additions": dict.fromkeys(PEOPLE, 200)}
    resources.write_text(json.dumps(allocation), encoding="utf-8")
    reordered = old["reordered"]
    count = old["fixed_aircraft_count"]
    audit = check(args.output, reordered, count, args.horizon, resources)
    if audit["errors"]:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    peaks = audit["resource_peaks"]
    allocation["vehicle_additions"] = {
        v: max(0, peaks.get(f"vehicle_{v}", 0) - stock) for v, stock in VEHICLES.items()
    }
    tow = audit["tow_count"]
    tow_vehicles = ceil_div(tow, 2) if tow <= 4 else (
        ceil_div(2 * tow, 3) if tow <= 8 else ceil_div(5 * tow, 6))
    allocation["vehicle_additions"]["Z1"] = max(
        allocation["vehicle_additions"]["Z1"], tow_vehicles - VEHICLES["Z1"])
    allocation["people_additions"] = {
        g: max(0, ceil_div(peaks.get(f"staff_{g}", 0), 2) - stock) for g, stock in PEOPLE.items()
    }
    allocation.update(status="FEASIBLE", method="regroup_existing_schedule",
                      source_schedule=str(args.schedule), fixed_aircraft_count=count,
                      limit_minutes=args.horizon, reordered=reordered)
    if args.existing_only:
        allocation["vehicle_additions"] = dict.fromkeys(VEHICLES, 0)
        allocation["people_additions"] = dict.fromkeys(PEOPLE, 0)
    resources.write_text(json.dumps(allocation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = check(args.output, reordered, count, args.horizon, resources)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if audit["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
