"""独立检查问题3单批原型输出；不代表45波次和驰援已验证。"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    data_bytes = (ROOT / 'results/q23_normalized.json').read_bytes()
    data = json.loads(data_bytes)
    result = json.loads((ROOT / 'results/q3_batch_prototype.json').read_text(encoding='utf-8'))
    errors = []
    if result['normalized_input_sha256'] != hashlib.sha256(data_bytes).hexdigest():
        errors.append('输入哈希不匹配')
    ops = {(o['aircraft'], o['operation']): o for o in result['operations']}
    resources = data['runway_team_resources'][result['team']]
    events = defaultdict(list)

    def use(kind, start, end, amount):
        events[kind].extend(((start, amount), (end, -amount)))

    expected = {'fuel': ('Z2', 'M6', 1), 'oxygen': ('Z3', 'M8', 1),
                'nitrogen': ('Z4', 'M8', 1), 'meal': ('Z8', 'M1', 2),
                'tow': ('Z1', 'M5', 1), 'parachute': ('Z9', 'M4', 2)}
    for (i, name), op in ops.items():
        if name in expected:
            veh, group, count = expected[name]
            use(veh, op['start_min'], op['end_min'], 1)
            use(group, op['start_min'], op['end_min'], count)
    for name, vehicle in [('power', 'Z5'), ('aircon', 'Z6')]:
        counts = [0] * 8
        for job in (j for j in result['electrical_jobs'] if j['operation'] == name):
            if len(job['aircraft']) not in (1, 2) or len(set(job['aircraft'])) != len(job['aircraft']):
                errors.append(f'{name}: 配对人数异常')
            if abs(job['end_min'] - job['start_min'] - 15) > 1e-9:
                errors.append(f'{name}: 工时异常')
            use(vehicle, job['start_min'], job['end_min'], 1)
            use('M7', job['start_min'], job['end_min'], 1)
            for i in job['aircraft']:
                counts[i] += 1
                op = ops[(i, name)]
                if (op['start_min'], op['end_min']) != (job['start_min'], job['end_min']):
                    errors.append(f'{i}/{name}: 配对时刻不一致')
                if op['start_min'] < ops[(i, 'meal')]['end_min'] or op['end_min'] > i + 80:
                    errors.append(f'{i}/{name}: 工序或80分钟期限错误')
        if counts != [1] * 8:
            errors.append(f'{name}: 覆盖次数{counts}')
    for i in range(8):
        fuel, meal = ops[(i, 'fuel')], ops[(i, 'meal')]
        if fuel['start_min'] < i or fuel['end_min'] - fuel['start_min'] != (15 if i < 6 else 30):
            errors.append(f'{i}: 加油错误')
        for gas in ('oxygen', 'nitrogen'):
            g = ops[(i, gas)]
            if g['start_min'] < fuel['end_min'] or g['end_min'] - g['start_min'] != 3 or meal['start_min'] < g['end_min']:
                errors.append(f'{i}/{gas}: 工时或前置错误')
        if meal['end_min'] - meal['start_min'] != (8 if i < 6 else 25):
            errors.append(f'{i}: 餐食工时错误')
        if meal['start_min'] < ops[('batch', 'parachute')]['end_min']:
            errors.append(f'{i}: 伞勤未完成')
    tow = ops[(0, 'tow')]
    chute = ops[('batch', 'parachute')]
    tow_ids = [i for i in range(8) if (i, 'tow') in ops]
    if (tow_ids != [0] or tow['start_min'] < 0 or
        tow['end_min'] - tow['start_min'] != 10 or
        ops[(0, 'fuel')]['start_min'] < tow['end_min'] or
        chute['start_min'] < max(tow['end_min'], 7) or
        chute['end_min'] - chute['start_min'] != 10):
        errors.append('牵引或保伞点错误')
    peaks = {}
    for key, values in events.items():
        load = peak = 0
        for _, delta in sorted(values, key=lambda x: (x[0], x[1])):
            load += delta
            peak = max(load, peak)
        peaks[key] = peak
        cap = resources['vehicles' if key.startswith('Z') else 'people'][key]
        if peak > cap:
            errors.append(f'{key}: 峰值{peak}超出{cap}')
    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'errors': errors,
                      'peaks': peaks, 'scope': 'Q3单批原型，不覆盖45波次'}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
