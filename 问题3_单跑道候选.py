"""在丙跑道重复单批模板的可行候选构造；无驰援，不证明最优。"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--waves', type=int, default=1)
    ap.add_argument('--spacing', type=float, default=100, help='相邻批首机着陆基础间隔，分钟')
    ap.add_argument('--output', type=Path, default=ROOT / 'results/q3_serial_candidate.json')
    args = ap.parse_args()
    if not 1 <= args.waves <= 45:
        ap.error('波次需在1至45之间')
    raw = (ROOT / 'results/q3_batch_prototype.json').read_bytes()
    template = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != '7626dd49fea46f2debce81238bc4b144546ea0463aec1256ceebdcd80088d502':
        raise ValueError('单批模板与已核验资源峰值不匹配，须重新验证')
    data = json.loads((ROOT / 'results/q23_normalized.json').read_text(encoding='utf-8'))
    if template['status'] not in ('FEASIBLE', 'OPTIMAL'):
        raise ValueError('单批模板无可行排程')
    # 运行前需用单批校验器独立检查模板；此处再核对目标丙地勤的资源。
    # 峰值为逐工序模板校验器输出，变更模板后必须重新核验。
    required = {'Z1':1, 'Z2':8, 'Z3':3, 'Z4':3, 'Z5':2, 'Z6':2,
                'Z8':5, 'Z9':1, 'M1':10, 'M4':2, 'M5':1, 'M6':8, 'M7':4, 'M8':6}
    cteam = data['runway_team_resources']['丙']
    for key, need in required.items():
        stock = cteam['vehicles' if key.startswith('Z') else 'people'][key]
        if need > stock:
            raise ValueError(f'丙地勤 {key} 不足：{need}>{stock}')
    n_batches = args.waves * 12
    duration = max(o['end_min'] for o in template['operations'])
    if args.spacing < max(duration, 17):
        ap.error('此构造要求批次不重叠且批间着陆满足10分钟')
    offsets, rest = [], []
    time = 0
    for i in range(n_batches):
        if i and i % 18 == 0:
            start = offsets[-1] + duration
            rest.append({'after_batch': i, 'start_min': start, 'end_min': start+180})
            time = max(time, start+180)
        offsets.append(time)
        time += args.spacing
    schedule, jobs, landings = [], [], []
    for idx, offset in enumerate(offsets):
        q = idx % 12
        ids = list(range(6*q+1, 6*q+7)) + [73+2*q, 74+2*q]
        for j, aircraft in enumerate(ids):
            relevant = [op['end_min'] for op in template['operations'] if op['aircraft'] == j]
            end = offset + max(relevant)
            landings.append({'wave': idx//12+1, 'batch': q+1, 'aircraft': aircraft,
                             'type': 'A' if j < 6 else 'B', 'runway': 'F3',
                             'landing_min': offset+j, 'takeoff_min': end})
        for op in template['operations']:
            ac = op['aircraft']
            schedule.append({**op, 'aircraft': ids[ac] if isinstance(ac, int) else ac,
                             'wave': idx//12+1, 'batch': q+1, 'runway': 'F3',
                             'start_min': op['start_min']+offset, 'end_min': op['end_min']+offset})
        for job in template['electrical_jobs']:
            jobs.append({**job, 'aircraft': [ids[j] for j in job['aircraft']], 'wave': idx//12+1,
                         'batch': q+1, 'runway': 'F3', 'start_min': job['start_min']+offset,
                         'end_min': job['end_min']+offset})
    out = {'scope': 'F3串行、丙地勤、无驰援，第一技能；不证明最优', 'waves': args.waves,
           'batch_spacing_min': args.spacing,
           'scenario_applicability': '假设F3及丙地勤三情景均可用，且休息从第18批保障完成后起算',
           'complete_problem3': False, 'template_sha256': hashlib.sha256(raw).hexdigest(),
           'makespan_min': max(x['takeoff_min'] for x in landings), 'rest_windows': rest,
           'landings': landings, 'operations': schedule, 'electrical_jobs': jobs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'waves': args.waves, 'batch_count': n_batches, 'aircraft_events': len(landings),
                      'makespan_min': out['makespan_min'], 'rests': len(rest),
                      'complete_problem3': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
