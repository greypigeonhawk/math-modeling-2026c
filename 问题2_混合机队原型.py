"""问题2最小排程切片：M/N来源、混合机型、第一技能及保守单机用车。

只验证从输入到资源调度的链路，不包含全部题面约束，不是正式问题2求解器。
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
SCALE = 36  # 0.9跨机型熟练度：分钟乘36可表示15/0.9、8/0.9等


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--time-limit', type=float, default=15)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/q2_mixed_prototype.json')
    args = parser.parse_args()
    source = (ROOT / 'results/q23_normalized.json').read_bytes()
    data = json.loads(source)
    stock = data['airport_resources']
    model = cp_model.CpModel()
    horizon = 120 * SCALE
    intervals = {(s, g): [] for s in ('M', 'N') for g in stock[s]['people']}
    vehicles = {v: [] for v in stock['M']['vehicles']}
    operations, choices = {}, {}

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

    # One A and one B, both requiring all nonoptional single-aircraft work.
    for i, plane in enumerate(('A', 'B')):
        for name, base, group, veh, count in (
            ('power_a', 15, 'M7', 'Z5', 1), ('aircon_a', 15, 'M7', 'Z6', 1),
            ('fuel', 15 if plane == 'A' else 30, 'M6', 'Z2', 1),
            ('oxygen', 3, 'M8', 'Z3', 1), ('nitrogen', 3, 'M8', 'Z4', 1),
            ('meal', 8 if plane == 'A' else 25, 'M1', 'Z8', 2),
            ('power_b', 15, 'M7', 'Z5', 1), ('aircon_b', 15, 'M7', 'Z6', 1)):
            task(i, plane, name, base, group, veh, count)
        for gas in ('oxygen', 'nitrogen'):
            for pred in ('fuel', 'power_a', 'aircon_a'):
                model.Add(operations[(i, gas)][0] >= operations[(i, pred)][1])
            model.Add(operations[(i, 'meal')][0] >= operations[(i, gas)][1])
        for op in ('power_b', 'aircon_b'):
            model.Add(operations[(i, op)][0] >= operations[(i, 'meal')][1])
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
    model.Minimize(sum(dispatch.values()) + sum(vehicle_dispatch.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.time_limit
    solver.parameters.num_search_workers = 2
    status = solver.Solve(model)
    result = {'status': solver.StatusName(status), 'complete_problem2': False,
              'scope': 'two aircraft; partial tasks; primary skills; singleton vehicles',
              'source_sha256': data['source_sha256'], 'normalized_input_sha256': hashlib.sha256(source).hexdigest()}
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        result['dispatch_people'] = {k: solver.Value(v) for k, v in dispatch.items()}
        result['dispatch_vehicles'] = {k: solver.Value(v) for k, v in vehicle_dispatch.items()}
        result['operations'] = [{'aircraft': i, 'type': ('A', 'B')[i], 'operation': op,
                                 'start_min': solver.Value(v[0]) / SCALE, 'end_min': solver.Value(v[1]) / SCALE,
                                 'vehicle': v[2], 'group': v[3], 'people': v[4],
                                 'origin': next(s for s in ('M', 'N') if solver.Value(choices[(i, op, s)]))}
                                for (i, op), v in operations.items()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'operations'}, ensure_ascii=False))
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
