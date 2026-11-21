"""对第二题受限候选排程独立复算；不验证原问题最优性。"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result', type=Path)
    args = ap.parse_args()
    raw = (ROOT / 'results/q23_normalized.json').read_bytes()
    data = json.loads(raw)
    res = json.loads(args.result.read_text(encoding='utf-8'))
    errors = []
    if res['status'] not in ('FEASIBLE', 'OPTIMAL'):
        raise ValueError('没有可校验的可行解')
    if res['normalized_input_sha256'] != hashlib.sha256(raw).hexdigest():
        errors.append('规范化数据哈希不匹配')
    source_hash = hashlib.sha256((ROOT / 'data/新2026C.docx').read_bytes()).hexdigest()
    if res['source_sha256'] != source_hash or data['source_sha256'] != source_hash:
        errors.append('原题DOCX哈希链不匹配')
    a, b = res['aircraft_a'], res['aircraft_b']
    n = a + b
    count = math.ceil(n / 10)
    both = math.ceil(count / 5)
    tow_ids = set(range(count))
    oil_ids = set(range(both)) | set(range(count, 2 * count - both))
    ops = {}
    events = defaultdict(list)
    def use(key, start, end, amount):
        events[key].extend(((start, amount), (end, -amount)))
    specs = {'power_a': (15, 'M7', 'Z5', 1), 'aircon_a': (15, 'M7', 'Z6', 1),
             'power_b': (15, 'M7', 'Z5', 1), 'aircon_b': (15, 'M7', 'Z6', 1),
             'oxygen': (3, 'M8', 'Z3', 1), 'nitrogen': (3, 'M8', 'Z4', 1),
             'tow': (10, 'M5', 'Z1', 1), 'oil': (10, 'M2', 'Z7', 1)}
    for row in res['operations']:
        i, name, side = row['aircraft'], row['operation'], row['origin']
        if not 0 <= i < n or side not in ('M', 'N') or (i, name) in ops:
            errors.append(f'飞机、来源或重复工序错误: {i}/{name}')
            continue
        typ = 'A' if i < a else 'B'
        base, group, veh, staff = specs.get(name, ((15 if typ == 'A' else 30), 'M6', 'Z2', 1) if name == 'fuel' else ((8 if typ == 'A' else 25), 'M1', 'Z8', 2))
        if name not in specs and name not in ('fuel', 'meal'):
            errors.append(f'未知工序 {name}')
            continue
        start, end = row['start_min'], row['end_min']
        factor = 1 if ((side == 'M') == (typ == 'A')) else .9
        if abs((end - start) - base / factor) > 1e-6 or start < 0 or end > 120:
            errors.append(f'{i}/{name}: 工时或时限错误')
        if (row['type'], row['group'], row['vehicle'], row['people']) != (typ, group, veh, staff):
            errors.append(f'{i}/{name}: 资源属性错误')
        use(('people', side, group), start, end, staff)
        use(('vehicle', veh), start, end, 1)
        ops[(i, name)] = row
    for i in range(n):
        required = {'power_a', 'aircon_a', 'fuel', 'oxygen', 'nitrogen', 'meal', 'power_b', 'aircon_b'}
        if i in tow_ids: required.add('tow')
        if i in oil_ids: required.add('oil')
        present = {op for (j, op) in ops if j == i}
        if present != required:
            errors.append(f'{i}: 工序集合不匹配')
            continue
        edges = [(p, gas) for gas in ('oxygen', 'nitrogen') for p in ('power_a', 'aircon_a', 'fuel')]
        edges += [(gas, 'meal') for gas in ('oxygen', 'nitrogen')]
        edges += [('meal', p) for p in ('power_b', 'aircon_b')]
        if i in tow_ids:
            edges += [('tow', p) for p in ('power_a', 'aircon_a', 'fuel')]
            if i in oil_ids: edges.append(('tow', 'oil'))
        if i in oil_ids: edges += [('oil', p) for p in ('oxygen', 'nitrogen')]
        for pred, succ in edges:
            if ops[(i, pred)]['end_min'] > ops[(i, succ)]['start_min'] + 1e-6:
                errors.append(f'{i}: {pred}->{succ} 错误')
    batches = {(r['operation'], r['batch']): r for r in res['batch_operations']}
    expected_batch = set()
    for i in range(0, n, 20): expected_batch.add(('material', i))
    for bidx in range(math.ceil(n / 40)): expected_batch.add(('parachute', bidx))
    if set(batches) != expected_batch:
        errors.append('航材/伞勤批次集合错误')
    else:
        for (kind, idx), row in batches.items():
            start, end = row['start_min'], row['end_min']
            size = min(40, n - idx * 40) if kind == 'parachute' else min(20, n - idx)
            duration = 6 + size / 2 if kind == 'parachute' else 10
            if start < 0 or end > 120 or abs(end - start - duration) > 1e-6 or row['origin'] != 'M':
                errors.append(f'{kind}/{idx}: 时长或来源错误')
            use(('vehicle', 'Z9'), start, end, 1)
            use(('people', 'M', 'M4'), start, end, 2)
            if kind == 'material':
                use(('people', 'M', 'M3'), start, end, 1)
                for i in range(idx, min(idx + 20, n)):
                    if i in tow_ids and start + 1e-6 < ops[(i, 'tow')]['end_min']:
                        errors.append(f'material/{idx}: 牵引未完')
            else:
                for k in range(idx * 40, min((idx + 1) * 40, n), 20):
                    if start + 1e-6 < batches[('material', k)]['end_min']:
                        errors.append(f'parachute/{idx}: 航材未完')
                for i in range(idx * 40, min((idx + 1) * 40, n)):
                    if ops[(i, 'meal')]['start_min'] + 1e-6 < end:
                        errors.append(f'{i}: 伞勤未完即餐食')
    peaks = {}
    for key, event_list in events.items():
        load = peak = 0
        for _, delta in sorted(event_list, key=lambda e: (e[0], e[1])):
            load += delta
            peak = max(peak, load)
        peaks['/'.join(key)] = peak
        if key[0] == 'vehicle':
            cap = data['airport_resources']['M']['vehicles'][key[1]] + res['dispatch_vehicles'][key[1]]
        else:
            cap = data['airport_resources'][key[1]]['people'][key[2]] if key[1] == 'M' else res['dispatch_people'][key[2]]
        if peak > cap: errors.append(f'{key}: {peak}>{cap}')
    for veh in ('Z3', 'Z4'):
        if data['airport_resources']['M']['vehicles'][veh] + res['dispatch_vehicles'][veh] < math.ceil(n / 10):
            errors.append(f'{veh}: 数量规则未满足')
    tow_need = math.ceil(count/2) if count <= 4 else (math.ceil(count/1.5) if count <= 8 else math.ceil(count/1.2))
    if data['airport_resources']['M']['vehicles']['Z1'] + res['dispatch_vehicles']['Z1'] < tow_need:
        errors.append('Z1牵引车辆数量规则未满足')
    for group, value in res['dispatch_people'].items():
        if not 0 <= value <= data['airport_resources']['N']['people'][group]:
            errors.append(f'N方人员库存超限: {group}')
    for veh, value in res['dispatch_vehicles'].items():
        if not 0 <= value <= data['airport_resources']['N']['vehicles'][veh]:
            errors.append(f'N方车辆库存超限: {veh}')
    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'errors': errors, 'peaks': peaks,
                      'scope': '受限候选排程，不证明完整题目最优性'}, ensure_ascii=False, indent=2))
    if errors: raise SystemExit(1)


if __name__ == '__main__':
    main()
