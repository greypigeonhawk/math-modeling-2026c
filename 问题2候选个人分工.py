"""将候选方案的N方组级人力分配到个人，核算个人负荷。"""
import argparse
import heapq
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    result = json.loads(args.result.read_text(encoding='utf-8'))
    groups = defaultdict(list)
    for task in result['operations']:
        if task['origin'] == 'N':
            groups[task['group']].append(task)
    output = {'source_result': str(args.result), 'scope': '候选排程固定时刻下的贪心个人分工；不声称负荷最优',
              'groups': {}}
    for group, tasks in groups.items():
        count = result['dispatch_people'][group]
        available = [(0.0, i) for i in range(count)]
        heapq.heapify(available)
        busy = []
        loads = [0.0] * count
        assignments = []
        for task in sorted(tasks, key=lambda t: (t['start_min'], t['end_min'], t['aircraft'], t['operation'])):
            start, end = task['start_min'], task['end_min']
            while busy and busy[0][0] <= start + 1e-8:
                _, i = heapq.heappop(busy)
                heapq.heappush(available, (loads[i], i))
            if len(available) < task['people']:
                raise ValueError(f'{group} 在 {start} 分钟人员不足')
            selected = [heapq.heappop(available)[1] for _ in range(task['people'])]
            for i in selected:
                loads[i] += end - start
                heapq.heappush(busy, (end, i))
            assignments.append({'aircraft': task['aircraft'], 'operation': task['operation'],
                                'start_min': start, 'end_min': end,
                                'people': [f'{group}-{i+1}' for i in selected]})
        output['groups'][group] = {'individual_workload_minutes': {f'{group}-{i+1}': round(v, 4)
                                                                     for i, v in enumerate(loads)},
                                    'assignments': assignments}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({g: v['individual_workload_minutes'] for g, v in output['groups'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
