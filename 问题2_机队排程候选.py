"""问题2两机工序切片：M/N来源、混合机型、第一技能及保守单机用车。

只验证从输入到资源调度的链路，不包含全部题面约束，不是正式问题2求解器。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
SCALE = 36  # 0.9跨机型熟练度：分钟乘36可表示15/0.9、8/0.9等


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--time-limit', type=float, default=15)
    parser.add_argument('--a', type=int, default=1)
    parser.add_argument('--b', type=int, default=1)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/q2_fleet_candidate.json')
    args = parser.parse_args()
    source = (ROOT / 'results/q23_normalized.json').read_bytes()
    data = json.loads(source)
    stock = data['airport_resources']
    model = cp_model.CpModel()
    horizon = 120 * SCALE
    intervals = {(s, g): [] for s in ('M', 'N') for g in stock[s]['people']}
    vehicles = {v: [] for v in stock['M']['vehicles']}
    operations, choices = {}, {}
    aircraft = ['A'] * args.a + ['B'] * args.b
    n = len(aircraft)
    if args.a < 1 or args.b < 0 or n < 2:
        parser.error('需要至少一架A机及至少两架飞机')
    count = math.ceil(n / 10)
    intersection = math.ceil(count / 5)
    # Fixed assignment is conservative, and therefore not a proof of optimality.
    tow_ids = set(range(count))
    oil_ids = set(range(intersection)) | set(range(count, count + count - intersection))

    def task(i, plane, name, base, group, vehicle, count=1):
        start = model.NewIntVar(0, horizon, f's_{i}_{name}')
        end = model.NewIntVar(0, horizon, f'e_{i}_{name}')
        alternatives = []
        for side in ('M', 'N'):
            choice = model.NewBoolVar(f'{i}_{name}_{side}')
            same_type = (side == 'M') == (plane == 'A')
            duration = round(base * SCALE / (1 if same_type else .9))
            option = model.NewOptionalIntervalVar(start, duration, end, choice, f'i_{i}_{name}_{side}')
            intervals[(side, group)].append((option, count))
            vehicles[vehicle].append(option)
            alternatives.append(choice)
            choices[(i, name, side)] = choice
        model.AddExactlyOne(alternatives)
        operations[(i, name)] = (start, end, vehicle, group, count)
        return start, end

    for i, plane in enumerate(aircraft):
        for name, base, group, veh, count in (
            ('power_a', 15, 'M7', 'Z5', 1), ('aircon_a', 15, 'M7', 'Z6', 1),
            ('fuel', 15 if plane == 'A' else 30, 'M6', 'Z2', 1),
            ('oxygen', 3, 'M8', 'Z3', 1), ('nitrogen', 3, 'M8', 'Z4', 1),
            ('meal', 8 if plane == 'A' else 25, 'M1', 'Z8', 2),
            ('power_b', 15, 'M7', 'Z5', 1), ('aircon_b', 15, 'M7', 'Z6', 1)):
            task(i, plane, name, base, group, veh, count)
        if i in tow_ids:
            task(i, plane, 'tow', 10, 'M5', 'Z1')
        if i in oil_ids:
            task(i, plane, 'oil', 10, 'M2', 'Z7')
        if i in tow_ids:
            for op in ('power_a', 'aircon_a', 'fuel'):
                model.Add(operations[(i, op)][0] >= operations[(i, 'tow')][1])
            if i in oil_ids:
                model.Add(operations[(i, 'oil')][0] >= operations[(i, 'tow')][1])
        for gas in ('oxygen', 'nitrogen'):
            for pred in ('fuel', 'power_a', 'aircon_a'):
                model.Add(operations[(i, gas)][0] >= operations[(i, pred)][1])
            model.Add(operations[(i, 'meal')][0] >= operations[(i, gas)][1])
            if i in oil_ids:
                model.Add(operations[(i, gas)][0] >= operations[(i, 'oil')][1])
        for op in ('power_b', 'aircon_b'):
            model.Add(operations[(i, op)][0] >= operations[(i, 'meal')][1])
    # 固定M方人员组织单个航材作业：1名M3、2名M4和1辆Z9。
    # 全机航材需求是保守假设，非题目明确规定。
    batches = []
    for b in range(math.ceil(n / 40)):
        members = range(40*b, min(40*(b+1), n))
        mat_ends = []
        for k in range(40*b, min(40*(b+1), n), 20):
            ms = model.NewIntVar(0, horizon, f'material_s_{k}')
            me = model.NewIntVar(0, horizon, f'material_e_{k}')
            mi = model.NewIntervalVar(ms, 10*SCALE, me, f'material_{k}')
            intervals[('M', 'M3')].append((mi, 1))
            intervals[('M', 'M4')].append((mi, 2))
            vehicles['Z9'].append(mi)
            for i in range(k, min(k+20, n)):
                if i in tow_ids:
                    model.Add(ms >= operations[(i, 'tow')][1])
            mat_ends.append(me)
            batches.append(('material', k, ms, me))
        cs = model.NewIntVar(0, horizon, f'chute_s_{b}')
        ce = model.NewIntVar(0, horizon, f'chute_e_{b}')
        ci = model.NewIntervalVar(cs, (6*SCALE + len(members)*SCALE//2), ce, f'chute_{b}')
        intervals[('M', 'M4')].append((ci, 2))
        vehicles['Z9'].append(ci)
        for me in mat_ends:
            model.Add(cs >= me)
        for i in members:
            model.Add(operations[(i, 'meal')][0] >= ce)
        batches.append(('parachute', b, cs, ce))
    dispatch = {}
    for (side, group), items in intervals.items():
        cap = stock[side]['people'][group]
        if side == 'N':
            dispatch[group] = model.NewIntVar(0, cap, f'dispatch_{group}')
            cap = dispatch[group]
        if items:
            model.AddCumulative([x[0] for x in items], [x[1] for x in items], cap)
    vehicle_dispatch = {}
    for vehicle, items in vehicles.items():
        vehicle_dispatch[vehicle] = model.NewIntVar(0, stock['N']['vehicles'][vehicle], f'dispatch_{vehicle}')
        if items:
            model.AddCumulative(items, [1] * len(items), stock['M']['vehicles'][vehicle] + vehicle_dispatch[vehicle])
    for vehicle in ('Z3', 'Z4'):
        model.Add(stock['M']['vehicles'][vehicle] + vehicle_dispatch[vehicle] >= math.ceil(n/10))
    tow_vehicle_need = math.ceil(count/2) if count <= 4 else (math.ceil(count/1.5) if count <= 8 else math.ceil(count/1.2))
    model.Add(stock['M']['vehicles']['Z1'] + vehicle_dispatch['Z1'] >= tow_vehicle_need)
    model.Minimize(sum(dispatch.values()) + sum(vehicle_dispatch.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.time_limit
    solver.parameters.num_search_workers = 2
    status = solver.Solve(model)
    result = {'status': solver.StatusName(status), 'complete_problem2': False,
              'scope': 'restricted candidate: fixed tow/oil IDs, primary skills, singleton vehicles, all material, M batch staff',
              'aircraft_a': args.a, 'aircraft_b': args.b,
              'source_sha256': data['source_sha256'], 'normalized_input_sha256': hashlib.sha256(source).hexdigest()}
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        result['dispatch_people'] = {k: solver.Value(v) for k, v in dispatch.items()}
        result['dispatch_vehicles'] = {k: solver.Value(v) for k, v in vehicle_dispatch.items()}
        result['operations'] = [{'aircraft': i, 'type': aircraft[i], 'operation': op,
                                 'start_min': solver.Value(v[0]) / SCALE, 'end_min': solver.Value(v[1]) / SCALE,
                                 'vehicle': v[2], 'group': v[3], 'people': v[4],
                                 'origin': next(s for s in ('M', 'N') if solver.Value(choices[(i, op, s)]))}
                                for (i, op), v in operations.items()]
        result['batch_operations'] = [{'operation': kind, 'batch': b, 'start_min': solver.Value(start) / SCALE,
                                       'end_min': solver.Value(end) / SCALE, 'origin': 'M'}
                                      for kind, b, start, end in batches]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('operations', 'batch_operations')}, ensure_ascii=False))
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
