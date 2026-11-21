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

ROOT = Path(__file__).resolve().parents[2]
SCALE = 36  # 0.9跨机型熟练度：分钟乘36可表示15/0.9、8/0.9等


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--time-limit', type=float, default=15)
    parser.add_argument('--a', type=int, default=1)
    parser.add_argument('--b', type=int, default=1)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/q2_fair_candidate.json')
    parser.add_argument('--max-people', type=int, default=10)
    parser.add_argument('--max-vehicles', type=int, default=7)
    parser.add_argument('--fixed-dispatch', type=Path, help='固定某候选方案的人车配置以公平比较负荷')
    args = parser.parse_args()
    if args.a + args.b > 2 and not args.fixed_dispatch:
        parser.error('实际规模必须固定已存在的人车配置，避免改变参与组别导致极差退化')
    source = (ROOT / 'results/q23_normalized.json').read_bytes()
    data = json.loads(source)
    stock = data['airport_resources']
    model = cp_model.CpModel()
    horizon = 120 * SCALE
    intervals = {(s, g): [] for s in ('M', 'N') for g in stock[s]['people']}
    vehicles = {v: [] for v in stock['M']['vehicles']}
    operations, choices = {}, {}
    n_workload_terms = {g: [] for g in stock['N']['people']}
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
            if side == 'N':
                n_workload_terms[group].append(choice * duration * count)
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
    baseline = None
    if args.fixed_dispatch:
        baseline = json.loads(args.fixed_dispatch.read_text(encoding='utf-8'))
        if baseline['aircraft_a'] != args.a or baseline['aircraft_b'] != args.b:
            parser.error('固定配置所属机队与当前机队不一致')
        for group, variable in dispatch.items():
            model.Add(variable == baseline['dispatch_people'][group])
        for vehicle, variable in vehicle_dispatch.items():
            model.Add(variable == baseline['dispatch_vehicles'][vehicle])
    # 在给定派遣上限内优化组级人均负荷率的极差；不涉及个人均衡。
    model.Add(sum(dispatch.values()) <= args.max_people)
    model.Add(sum(vehicle_dispatch.values()) <= args.max_vehicles)
    utilization = {}
    workloads = {}
    active_groups = []
    hi = model.NewIntVar(0, 1000, 'max_utilization')
    lo = model.NewIntVar(0, 1000, 'min_utilization')
    for group, count_var in dispatch.items():
        workload = model.NewIntVar(0, 120*SCALE*stock['N']['people'][group], f'work_{group}')
        model.Add(workload == sum(n_workload_terms[group]))
        workloads[group] = workload
        active = model.NewBoolVar(f'active_{group}')
        active_groups.append(active)
        model.Add(count_var >= 1).OnlyEnforceIf(active)
        model.Add(count_var == 0).OnlyEnforceIf(active.Not())
        # A dispatched group must actually work, avoiding fictitious idle groups.
        model.Add(workload >= 1).OnlyEnforceIf(active)
        divisor = model.NewIntVar(1, max(1, stock['N']['people'][group]), f'divisor_{group}')
        model.AddMaxEquality(divisor, [count_var, 1])
        normalized = model.NewIntVar(0, 1000, f'util_{group}')
        numerator = model.NewIntVar(0, 1000*120*SCALE*stock['N']['people'][group], f'numerator_{group}')
        model.Add(numerator == workload * 1000)
        denominator = model.NewIntVar(120*SCALE, 120*SCALE*max(1, stock['N']['people'][group]), f'denom_{group}')
        model.Add(denominator == divisor * 120*SCALE)
        model.AddDivisionEquality(normalized, numerator, denominator)
        model.Add(hi >= normalized).OnlyEnforceIf(active)
        model.Add(lo <= normalized).OnlyEnforceIf(active)
        utilization[group] = normalized
    any_active = model.NewBoolVar('any_active')
    model.AddMaxEquality(any_active, active_groups)
    model.Add(hi == 0).OnlyEnforceIf(any_active.Not())
    model.Add(lo == 0).OnlyEnforceIf(any_active.Not())
    model.Minimize(hi - lo)
    if baseline is not None:
        # 固定配置的原排程是有效热启动，减少寻找首个可行解的时间。
        for row in baseline['operations']:
            key = (row['aircraft'], row['operation'])
            if key not in operations:
                raise ValueError(f'热启动包含模型不存在的工序: {key}')
            model.AddHint(operations[key][0], round(row['start_min'] * SCALE))
            model.AddHint(operations[key][1], round(row['end_min'] * SCALE))
            for side in ('M', 'N'):
                model.AddHint(choices[(key[0], key[1], side)], int(row['origin'] == side))
        batch_lookup = {(kind, b): (start, end) for kind, b, start, end in batches}
        for row in baseline['batch_operations']:
            start, end = batch_lookup[(row['operation'], row['batch'])]
            model.AddHint(start, round(row['start_min'] * SCALE))
            model.AddHint(end, round(row['end_min'] * SCALE))
        for group, variable in dispatch.items():
            model.AddHint(variable, baseline['dispatch_people'][group])
        for vehicle, variable in vehicle_dispatch.items():
            model.AddHint(variable, baseline['dispatch_vehicles'][vehicle])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.time_limit
    solver.parameters.num_search_workers = 2
    status = solver.Solve(model)
    result = {'status': solver.StatusName(status), 'complete_problem2': False,
              'scope': 'restricted fairness candidate; fixed tow/oil, primary skills, singleton vehicles, all material, M batch staff',
              'aircraft_a': args.a, 'aircraft_b': args.b,
              'fixed_dispatch_source': str(args.fixed_dispatch) if args.fixed_dispatch else None,
              'source_sha256': data['source_sha256'], 'normalized_input_sha256': hashlib.sha256(source).hexdigest()}
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        result['group_utilization_range_thousandths'] = solver.Value(hi) - solver.Value(lo)
        result['group_utilization_thousandths'] = {g: solver.Value(v) for g, v in utilization.items()}
        result['active_groups'] = [g for g, v in dispatch.items() if solver.Value(v) > 0]
        result['group_workload_person_minutes'] = {g: solver.Value(v) / SCALE for g, v in workloads.items()}
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
