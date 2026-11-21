"""核对逐机排程，并将固定区间划分为单机或双机服务后分配实体资源。"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from itertools import combinations
from math import ceil
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[2]
PAIRABLE = {"power_a", "aircon_a", "power_b", "aircon_b"}
SCALE = 36


def tick(minutes):
    return round(minutes * SCALE)


def assign(result, data, seconds, allow_extra=False, redispatch=False):
    stock = data["airport_resources"]
    tasks, buckets, pairs = {}, defaultdict(list), {}

    def record(key, row, vehicle, staff):
        tasks[key] = (tick(row["start_min"]), tick(row["end_min"]), vehicle, staff)
        return key

    for row in result["operations"]:
        key = record((row["aircraft"], row["operation"]), row, row["vehicle"],
                     {(row["origin"], row["group"]): row["people"]})
        if row["mode"] == "synchronous_pair":
            pairs[key] = (row["pair_with"], row["operation"])
        elif row["mode"] == "double_slot" and row["operation"] in PAIRABLE:
            buckets[(row["vehicle"], row["origin"], row["group"])].append(key)
    for row in result["batch_operations"]:
        staff = {("M", "M4"): 2}
        if row["operation"] == "material":
            staff["M", "M3"] = 1
        record((row["batch"], row["operation"]), row, "Z9", staff)

    # Assign each task to a single service or a shared service. Overlapping
    # jobs can share a vehicle and operator only within the same staff pool.
    model = cp_model.CpModel()
    choices, services = defaultdict(list), []
    occupancy = defaultdict(list)

    def option(keys):
        start = min(tasks[k][0] for k in keys)
        end = max(tasks[k][1] for k in keys)
        _, _, vehicle, staff = tasks[keys[0]]
        active = model.new_bool_var(f"service_{len(services)}")
        interval = model.new_optional_fixed_size_interval_var(start, end-start, active, str(keys))
        resources = {("vehicle", vehicle): 1, **staff}
        for pool, count in resources.items():
            occupancy[pool].append((interval, count))
        for key in keys:
            choices[key].append(active)
        services.append((keys, start, end, resources, active))

    for key in tasks:
        if key not in pairs:
            option((key,))
        elif key < pairs[key]:
            option((key, pairs[key]))
    for keys in buckets.values():
        for left, right in combinations(keys, 2):
            a, b, *_ = tasks[left]
            c, d, *_ = tasks[right]
            if max(a, c) < min(b, d):
                option((left, right))
    for options in choices.values():
        model.add_exactly_one(options)

    capacities, added_people, added_vehicles = {}, [], []
    if redispatch:
        for group in stock["N"]["people"]:
            occupancy.setdefault(("N", group), [])
        for vehicle in stock["N"]["vehicles"]:
            occupancy.setdefault(("vehicle", vehicle), [])
    for pool, items in occupancy.items():
        side, group = pool
        if side == "vehicle":
            count = stock["M"]["vehicles"][group] + result["dispatch_vehicles"][group]
        elif side == "M":
            count = stock[side]["people"][group]
        else:
            count = result["dispatch_people"][group]
        if (allow_extra or redispatch) and side != "M":
            kind = "vehicles" if side == "vehicle" else "people"
            dispatched = result[f"dispatch_{kind}"][group]
            minimum = -dispatched if redispatch else 0
            if kind == "vehicles" and group in ("Z3", "Z4"):
                fleet = result["aircraft_a"] + result["aircraft_b"]
                minimum = max(minimum, (fleet + 9)//10 - count)
            if kind == "vehicles" and group == "Z1" and redispatch:
                tow = ceil((result["aircraft_a"] + result["aircraft_b"]) / 10)
                ratio = 2 if tow <= 4 else 1.5 if tow <= 8 else 1.2
                minimum = max(minimum, ceil(tow / ratio) - count)
            extra = model.new_int_var(minimum, stock["N"][kind][group] - dispatched,
                                      f"extra_{side}_{group}")
            (added_vehicles if side == "vehicle" else added_people).append(extra)
            count += extra
        capacities[pool] = count
        if items:
            model.add_cumulative([iv for iv, _ in items], [d for _, d in items], count)
    pair_count = sum(active for keys, _, _, _, active in services if len(keys) == 2)
    if allow_extra or redispatch:
        crew = {"Z1": ("M5",), "Z2": ("M6",), "Z3": ("M8",), "Z4": ("M8",),
                "Z5": ("M7",), "Z6": ("M7",), "Z7": ("M2",), "Z8": ("M1",),
                "Z9": ("M3", "M4")}
        for vehicle, groups in crew.items():
            local = stock["M"]["vehicles"][vehicle]
            count = capacities.get(("vehicle", vehicle), local + result["dispatch_vehicles"][vehicle])
            people = sum(capacities.get(("N", group), result["dispatch_people"][group])
                         for group in groups)
            model.add(count - local <= stock["N"]["vehicles"][vehicle] * people)
        # Each coefficient dominates the full range of all later objectives.
        weight = len(tasks) + 1
        model.minimize(weight * ((sum(stock["N"]["vehicles"].values()) + 1) * sum(added_people)
                                + sum(added_vehicles)) - pair_count)
    else:
        model.maximize(pair_count)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 2
    status = solver.solve(model)
    output = {"status": solver.status_name(status),
              "scope": "fixed operation times and staff groups; each shared service contains at most two tasks",
              "services": []}
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return output

    capacities = {pool: solver.value(count) for pool, count in capacities.items()}
    output["dispatch_people"] = {g: capacities.get(("N", g), count)
                                 for g, count in result["dispatch_people"].items()}
    output["dispatch_vehicles"] = {
        v: capacities.get(("vehicle", v), stock["M"]["vehicles"][v] + count)
        - stock["M"]["vehicles"][v] for v, count in result["dispatch_vehicles"].items()}
    free_at = {pool: [0] * count for pool, count in capacities.items()}
    workload = {pool: [0] * count for pool, count in capacities.items() if pool[0] != "vehicle"}
    for keys, start, end, resources, active in sorted(services, key=lambda s: (s[1], s[2], s[0])):
        if not solver.value(active):
            continue
        row = {"tasks": keys, "start_min": start/SCALE, "end_min": end/SCALE, "people": []}
        for pool, demand in resources.items():
            side, group = pool
            available = [i for i, t in enumerate(free_at[pool]) if t <= start]
            if pool in workload:
                available.sort(key=lambda i: (workload[pool][i], i))
            assert len(available) >= demand
            for i in available[:demand]:
                free_at[pool][i] = end
                if side == "vehicle":
                    local = stock["M"]["vehicles"][group]
                    row["vehicle"] = ("M", group, i+1) if i < local else ("N", group, i-local+1)
                else:
                    row["people"].append((side, group, i+1))
                    workload[pool][i] += end-start
        output["services"].append(row)
    output["paired_services"] = sum(len(r["tasks"]) == 2 for r in output["services"])
    output["N_workload_minutes"] = {g: [t/SCALE for t in workload.get(("N", g), [])]
                                    for g, count in output["dispatch_people"].items() if count}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    dispatch_mode = parser.add_mutually_exclusive_group()
    dispatch_mode.add_argument("--allow-extra", action="store_true",
                        help="固定原工序时刻和人员组，允许在库存内追加派遣")
    dispatch_mode.add_argument("--redispatch", action="store_true",
                        help="固定原工序时刻和人员组，重新优化派遣数量")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "验证问题2多技能候选.py"), str(args.result)],
                   check=True, stdout=subprocess.DEVNULL)
    raw = args.result.read_bytes()
    data = json.loads((ROOT / "results/q23_normalized.json").read_bytes())
    certificate = assign(json.loads(raw), data, args.seconds, args.allow_extra, args.redispatch)
    certificate["schedule_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(certificate, ensure_ascii=False, indent=2) + "\n")
    print(certificate["status"], certificate.get("paired_services"),
          certificate.get("N_workload_minutes"))
    if not certificate["services"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
