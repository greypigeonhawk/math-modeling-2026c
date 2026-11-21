"""问题3单批约束原型：固定一条跑道、第一技能、任意两机同步配对。

仅用于打通数据和逐机排程；跨跑道调动、45波次和尚未实现的技能替代仍需补全。
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[2]
SCALE = 2  # 0.5 minute


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team', choices=list('甲乙丙丁'), default='甲')
    ap.add_argument('--time-limit', type=float, default=15)
    ap.add_argument('--output', type=Path, default=ROOT / 'results/q3_batch_prototype.json')
    args = ap.parse_args()
    input_path = ROOT / 'results/q23_normalized.json'
    input_bytes = input_path.read_bytes()
    data = json.loads(input_bytes)
    resources = data['runway_team_resources'][args.team]
    model = cp_model.CpModel()
    horizon = 180 * SCALE
    vehicles = {k: [] for k in resources['vehicles']}
    people = {k: [] for k in resources['people']}
    ops = {}
    electrical_assignments = []

    def task(i, name, duration, vehicle, group, staff=1):
        start = model.NewIntVar(0, horizon, f's_{i}_{name}')
        end = model.NewIntVar(0, horizon, f'e_{i}_{name}')
        interval = model.NewIntervalVar(start, int(duration * SCALE), end, f'i_{i}_{name}')
        vehicles[vehicle].append((interval, 1))
        people[group].append((interval, staff))
        ops[(i, name)] = (start, end)
        return start, end

    # Six A then two B; each lands one minute after the preceding aircraft.
    for i in range(8):
        landing = i * SCALE
        if i == 0:
            tow = task(i, 'tow', 10, 'Z1', 'M5')
            model.Add(tow[0] >= landing)
        fuel = task(i, 'fuel', 15 if i < 6 else 30, 'Z2', 'M6')
        model.Add(fuel[0] >= landing)
        if i == 0:
            model.Add(fuel[0] >= ops[(i, 'tow')][1])
        for op, veh in [('oxygen', 'Z3'), ('nitrogen', 'Z4')]:
            start, _ = task(i, op, 3, veh, 'M8')
            model.Add(start >= fuel[1])
        meal = task(i, 'meal', 8 if i < 6 else 25, 'Z8', 'M1', 2)
        for op in ('oxygen', 'nitrogen'):
            model.Add(meal[0] >= ops[(i, op)][1])
    # Each plane is covered once, by a singleton or by any unordered pair.
    # A selected interval consumes one vehicle and one M7 for both planes.
    for op, veh in [('power', 'Z5'), ('aircon', 'Z6')]:
        membership = [[] for _ in range(8)]
        for i in range(8):
            ops[(i, op)] = (model.NewIntVar(0, horizon, f's_{i}_{op}'),
                            model.NewIntVar(0, horizon, f'e_{i}_{op}'))
        for i in range(8):
            for j in range(i, 8):
                members = [i] if i == j else [i, j]
                selected = model.NewBoolVar(f'{op}_{i}_{j}')
                start = model.NewIntVar(0, horizon, f's_{op}_{i}_{j}')
                end = model.NewIntVar(0, horizon, f'e_{op}_{i}_{j}')
                interval = model.NewOptionalIntervalVar(start, 15 * SCALE, end, selected, f'int_{op}_{i}_{j}')
                vehicles[veh].append((interval, 1))
                people['M7'].append((interval, 1))
                electrical_assignments.append((op, members, selected, start, end))
                for k in members:
                    membership[k].append(selected)
                    model.Add(ops[(k, op)][0] == start).OnlyEnforceIf(selected)
                    model.Add(ops[(k, op)][1] == end).OnlyEnforceIf(selected)
        for i in range(8):
            model.AddExactlyOne(membership[i])
            model.Add(ops[(i, op)][0] >= ops[(i, 'meal')][1])
            model.Add(ops[(i, op)][1] <= (i + 80) * SCALE)

    # Conservative common parachute point: all eight wait for completion.
    start, end = task('batch', 'parachute', 6 + 8 * .5, 'Z9', 'M4', 2)
    model.Add(start >= ops[(0, 'tow')][1])
    model.Add(start >= 7 * SCALE)
    for i in range(8):
        model.Add(ops[(i, 'meal')][0] >= end)
    for pool, caps in ((vehicles, resources['vehicles']), (people, resources['people'])):
        for key, intervals in pool.items():
            if intervals:
                model.AddCumulative([x[0] for x in intervals], [x[1] for x in intervals], caps[key])
    makespan = model.NewIntVar(0, horizon, 'makespan')
    model.AddMaxEquality(makespan, [ops[(i, op)][1] for i in range(8) for op in ('power', 'aircon')])
    model.Minimize(makespan)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.time_limit
    solver.parameters.num_search_workers = 2
    status = solver.Solve(model)
    output = {'status': solver.StatusName(status), 'team': args.team,
              'source_sha256': data['source_sha256'], 'normalized_input_sha256': hashlib.sha256(input_bytes).hexdigest(),
              'scope': 'one batch; primary skills; optional arbitrary synchronized pairs',
              'complete_problem3': False, 'wall_time_seconds': solver.WallTime()}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        output['makespan_min'] = solver.Value(makespan) / SCALE
        output['operations'] = [{'aircraft': i, 'operation': name,
                                 'start_min': solver.Value(s) / SCALE, 'end_min': solver.Value(e) / SCALE}
                                for (i, name), (s, e) in ops.items()]
        output['electrical_jobs'] = [{'operation': op, 'aircraft': members,
                                      'start_min': solver.Value(start) / SCALE,
                                      'end_min': solver.Value(end) / SCALE}
                                     for op, members, chosen, start, end in electrical_assignments
                                     if solver.Value(chosen)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in output.items() if k not in ('operations', 'electrical_jobs')}, ensure_ascii=False))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
