"""沿用可行排程，重排作业并试配原先独立服务的飞机。"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model

from 问题1_优化模型 import PEOPLE, VEHICLES, SCALE, SKILL_GROUP
from 验证第一问排程 import check, TASK_BASE, VEH_OF

ELECTRIC = {"power_a", "aircon_a", "power_b", "aircon_b"}
HORIZON = 120 * SCALE


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fixed-only", action="store_true", help="仅重排固定配对，不新增配对")
    ap.add_argument("--reorder", action="store_true")
    ap.add_argument("--vehicle-budget", type=int, default=68)
    args = ap.parse_args()
    stock = json.loads(args.source.with_name(args.source.stem + "_resources.json").read_text())
    with args.source.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    source = json.loads((Path(__file__).resolve().parents[2] / "results/q1_source_tables.json").read_text())
    promotions = {tuple(pair) for pair in stock["promoted_skills"]}
    electrical_groups = {}
    for _, primary, second, third in source["multi_skill_table"][1:]:
        group = SKILL_GROUP[primary.strip()]
        if primary.strip() == "电源空调":
            electrical_groups[group] = 1
        elif "电源空调" in second.strip().split("、") or (group, "电源空调") in promotions:
            electrical_groups[group] = 2

    model = cp_model.CpModel()
    people, vehicles = defaultdict(list), defaultdict(list)
    aircraft, jobs = defaultdict(dict), defaultdict(list)
    times, old = {}, {}
    for index, row in enumerate(rows):
        aid, op = row["aircraft"], row["operation"]
        key = (op, row["vehicle_pair"] or aid) if aid.isdigit() else (aid, op)
        jobs[key].append(index)
        if aid.isdigit():
            aircraft[int(aid)][op] = index
        old[index] = tuple(round(float(row[k]) * SCALE) for k in ("start_min", "end_min"))

    candidates = defaultdict(set)
    if not args.fixed_only:
        for op in sorted(ELECTRIC):
            singles = [i for i, r in enumerate(rows) if r["operation"] == op and r["vehicle_mode"] == "single"]
            singles.sort(key=lambda i: (old[i], i))
            for pos, left in enumerate(singles):
                for right in singles[pos+1:pos+4]:
                    candidates[left].add(right)

    for index in range(len(rows)):
        row = rows[index]
        job_key = (row["operation"], row["vehicle_pair"] or row["aircraft"]) if row["aircraft"].isdigit() else (row["aircraft"], row["operation"])
        representative = jobs[job_key][0]
        if representative == index:
            start = model.new_int_var(0, HORIZON, f"s{index}")
            end = model.new_int_var(0, HORIZON, f"e{index}")
            model.add_hint(start, old[index][0])
            model.add_hint(end, old[index][1])
        else:
            start, end = times[representative]
        times[index] = start, end

    choices = defaultdict(list)
    assignments = []

    def electrical_job(members, paired_candidate=False):
        index = members[0]
        base = rows[index]
        operator = base["operator_group"]
        options = dict(electrical_groups)
        options[operator] = int(base["skill_level"])
        start, end = times[index]
        for group, level in options.items():
            duration = round(TASK_BASE[base["operation"]] * SCALE / {1: 1, 2: .8, 3: .4}[level])
            used = model.new_bool_var(f"x{index}_{members[-1]}_{group}")
            interval = model.new_optional_interval_var(start, duration, end, used, f"i{index}_{members[-1]}_{group}")
            model.add_hint(used, int(not paired_candidate and group == operator))
            for member in members:
                choices[member].append(used)
                if paired_candidate and member != index:
                    model.add(times[member][0] == start).only_enforce_if(used)
                    model.add(times[member][1] == end).only_enforce_if(used)
            vehicles[VEH_OF[base["operation"]]].append(interval)
            people[group].append((interval, 1))
            assignments.append((used, members, group, level))

    for key, members in jobs.items():
        index = members[0]
        row = rows[index]
        op, aid = row["operation"], row["aircraft"]
        if op in ELECTRIC:
            electrical_job(members)
            for right in sorted(candidates[index]):
                electrical_job([index, right], paired_candidate=True)
            continue
        start, end = times[index]
        interval = model.new_interval_var(start, old[index][1] - old[index][0], end, f"fixed{index}")
        if aid == "material":
            people["M3"].append((interval, 1))
            people["M4"].append((interval, 2))
        else:
            people[row["operator_group"]].append((interval, 2 if op == "meal" or aid == "parachute" else 1))
        vehicles[VEH_OF[op] if aid.isdigit() else "Z9"].append(interval)

    for index, variables in choices.items():
        if rows[index]["vehicle_mode"] != "paired" or index == min(jobs[rows[index]["operation"], rows[index]["vehicle_pair"]]):
            model.add_exactly_one(variables)

    def precedes(before, after):
        model.add(times[before][1] <= times[after][0])

    def separates(one, other):
        first = model.new_bool_var(f"before_{one}_{other}")
        model.add(times[one][1] <= times[other][0]).only_enforce_if(first)
        model.add(times[other][1] <= times[one][0]).only_enforce_if(first.negated())
        model.add_hint(first, int(old[one][1] <= old[other][0]))

    for i, ops in aircraft.items():
        material = jobs["material", str(i // 20)][0]
        chute = jobs["parachute", str(i // 40)][0]
        precedes(material, chute)
        if "tow" in ops:
            precedes(ops["tow"], material)
            for op in ops.keys() - {"tow"}:
                precedes(ops["tow"], ops[op])
        for gas in ("oxygen", "nitrogen"):
            if not args.reorder:
                for op in ("fuel", "power_a", "aircon_a", "oil"):
                    if op in ops:
                        precedes(ops[op], ops[gas])
            precedes(ops[gas], ops["meal"])
        if args.reorder:
            separates(ops["oxygen"], ops["fuel"])
            separates(ops["oxygen"], ops["power_a"])
            separates(ops["power_a"], ops["meal"])
        else:
            precedes(chute, ops["meal"])
        precedes(ops["fuel"], ops["meal"])
        for name in ("power_b", "aircon_b"):
            for op in ("meal", "power_a", "aircon_a", "oil"):
                if op in ops:
                    precedes(ops[op], ops[name])
            precedes(chute, ops[name])

    new_people = {}
    for group, items in people.items():
        ivals, demands = zip(*items)
        cap = 13 if group == "M7" else 0
        new_people[group] = model.new_int_var(0, cap, f"people_{group}")
        model.add_hint(new_people[group], stock["people_additions"][group])
        model.add_cumulative(ivals, demands, PEOPLE[group] + new_people[group])
    new_vehicles = {}
    for kind, ivals in vehicles.items():
        baseline = stock["vehicle_additions"][kind]
        new_vehicles[kind] = model.new_int_var(6 if kind == "Z1" else 0, baseline, f"vehicles_{kind}")
        model.add_hint(new_vehicles[kind], baseline)
        model.add_cumulative(ivals, [1] * len(ivals), VEHICLES[kind] + new_vehicles[kind])
    model.add(sum(new_vehicles.values()) <= args.vehicle_budget)
    model.minimize(14 * sum(new_vehicles.values()) + sum(new_people.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.seconds
    solver.parameters.num_search_workers = 7
    solver.parameters.random_seed = args.seed
    status = solver.solve(model)
    print(solver.status_name(status), solver.objective_value, solver.best_objective_bound, flush=True)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        raise SystemExit(2)
    for index, (start, end) in times.items():
        rows[index].update(start_min=solver.value(start)/SCALE, end_min=solver.value(end)/SCALE)
    for present, members, group, level in assignments:
        if solver.value(present):
            ids = sorted(int(rows[i]["aircraft"]) for i in members)
            for index in members:
                rows[index].update(operator_group=group, skill_level=level,
                                   vehicle_mode="paired" if len(ids)==2 else "single",
                                   vehicle_pair="-".join(map(str, ids)) if len(ids)==2 else "")
    allocation = {"promoted_skills": stock["promoted_skills"],
                  "people_additions": {g: solver.value(v) for g, v in new_people.items()},
                  "vehicle_additions": {k: solver.value(v) for k, v in new_vehicles.items()},
                  "source_schedule": str(args.source), "reordered": args.reorder,
                  "fixed_aircraft_count": 156, "limit_minutes": 120,
                  "status": solver.status_name(status), "objective": solver.objective_value,
                  "bound": solver.best_objective_bound}
    resource_path = args.output.with_name(args.output.stem + "_resources.json")
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    resource_path.write_text(json.dumps(allocation, ensure_ascii=False, indent=2) + "\n")
    audit = check(args.output, args.reorder, 156, 120, resource_path, b_final=args.reorder)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if audit["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
