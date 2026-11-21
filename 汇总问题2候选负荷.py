"""计算受限候选排程中N方各组人·分钟与人均负荷率。"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result', type=Path)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    res = json.loads(args.result.read_text(encoding='utf-8'))
    if res['status'] not in ('FEASIBLE', 'OPTIMAL'):
        raise ValueError('没有可汇总的候选排程')
    workload = defaultdict(float)
    for row in res['operations']:
        if row['origin'] == 'N':
            workload[row['group']] += (row['end_min'] - row['start_min']) * row['people']
    rows = []
    for group, count in res['dispatch_people'].items():
        if count:
            minutes = workload[group]
            rows.append({'group': group, 'dispatched_people': count,
                         'workload_person_minutes': round(minutes, 4),
                         'utilization': round(minutes / (120 * count), 6)})
    values = [r['utilization'] for r in rows]
    result = {'source_result': str(args.result), 'status': res['status'],
              'aircraft_a': res['aircraft_a'], 'aircraft_b': res['aircraft_b'],
              'scope': '受限候选方案；组均利用率不代表个人负荷均衡',
              'groups': rows, 'group_utilization_range': round(max(values) - min(values), 6) if values else None}
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
