"""保留已验证的配对和技能分工，仅重排气体作业与餐食。"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model

from 问题1_优化模型 import PEOPLE, VEHICLES, SCALE
from 验证第一问排程 import check

MOVABLE = {"oxygen": "Z3", "nitrogen": "Z4", "meal": "Z8"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    resource_file = args.source.with_name(args.source.stem + "_resources.json")
    allocation = json.loads(resource_file.read_text())
    with args.source.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    aircraft = defaultdict(dict)
    jobs = defaultdict(list)
    for row in rows:
        aid, op = row["aircraft"], row["operation"]
        if aid.isdigit():
            aircraft[int(aid)][op] = row
        key = (op, row["vehicle_pair"] or aid) if aid.isdigit() else (aid, op)
        jobs[key].append(row)
        for field in ("start_min", "end_min"):
            row[field] = round(float(row[field]) * SCALE)

    model = cp_model.CpModel()
    staff = defaultdict(list)
    vehicles = defaultdict(list)
    times = {}
    for key, members in jobs.items():
        row = members[0]
        op = row["operation"]
        start, end = row["start_min"], row["end_min"]
        width = end - start
        if row["aircraft"].isdigit() and op in MOVABLE:
            begin = model.new_int_var(0, 120 * SCALE - width, f"start_{key}")
            model.add_hint(begin, start)
            times[key] = (begin, width)
            interval = model.new_fixed_size_interval_var(begin, width, f"job_{key}")
            vehicles[MOVABLE[op]].append(interval)
        else:
            interval = model.new_fixed_size_interval_var(start, width, f"fixed_{key}")

        if row["aircraft"] == "material":
            staff["M3"].append((interval, 1))
            staff["M4"].append((interval, 2))
        else:
            staff[row["operator_group"]].append((interval, 2 if op == "meal" or row["aircraft"] == "parachute" else 1))

    parachute_ends = {int(row["operation"]): row["end_min"]
                      for row in rows if row["aircraft"] == "parachute"}
    for i, operations in aircraft.items():
        meal, meal_duration = times["meal", str(i)]
        model.add(meal >= parachute_ends[i // 40])
        model.add(meal + meal_duration <= min(operations[op]["start_min"] for op in ("power_b", "aircon_b")))
        for gas in ("oxygen", "nitrogen"):
            start, duration = times[gas, operations[gas]["vehicle_pair"]]
            model.add(start >= max(operations[op]["end_min"] for op in
                                   ("fuel", "power_a", "aircon_a", "oil") if op in operations))
            model.add(meal >= start + duration)

    for group, items in staff.items():
        intervals, amounts = zip(*items)
        model.add_cumulative(intervals, amounts, PEOPLE[group] + allocation["people_additions"][group])
    added = {}
    for kind, intervals in vehicles.items():
        added[kind] = model.new_int_var(0, allocation["vehicle_additions"][kind], f"extra_{kind}")
        model.add_hint(added[kind], allocation["vehicle_additions"][kind])
        model.add_cumulative(intervals, [1] * len(intervals), VEHICLES[kind] + added[kind])
    model.minimize(sum(added.values()))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 4
    solver.parameters.max_time_in_seconds = 45
    status = solver.solve(model)
    print(solver.status_name(status), solver.best_objective_bound)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SystemExit(2)
    for key, (start, duration) in times.items():
        actual = solver.value(start)
        for row in jobs[key]:
            row.update(start_min=actual, end_min=actual + duration)
    for row in rows:
        for field in ("start_min", "end_min"):
            row[field] /= SCALE
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    allocation["vehicle_additions"].update({kind: solver.value(value) for kind, value in added.items()})
    allocation["source_schedule"] = str(args.source)
    allocation["method"] = "local_rescheduling_gases_and_meals"
    allocation["status"] = "FEASIBLE"
    output_resources = args.output.with_name(args.output.stem + "_resources.json")
    output_resources.write_text(json.dumps(allocation, ensure_ascii=False, indent=2) + "\n")
    result = check(args.output, False, 156, 120, output_resources)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
