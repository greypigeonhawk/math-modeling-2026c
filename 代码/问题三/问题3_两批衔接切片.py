"""两批排程衔接切片，重用已核验的单批方案；不是45波次求解器。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    path = ROOT / 'results/q3_batch_prototype.json'
    raw = path.read_bytes()
    template = json.loads(raw)
    if template['status'] not in ('FEASIBLE', 'OPTIMAL') or template['team'] != '甲':
        raise ValueError('需要已求解的甲地勤单批方案')
    # Template last completion is 80 min. A 100-min separation prevents
    # resource overlap, and yields 93 min from last touchdown to next first.
    offsets = (0, 100)
    last_end = max(x['end_min'] for x in template['operations'])
    if offsets[1] < last_end:
        raise ValueError('两批资源时段重叠，切片未实现并行资源再调度')
    if offsets[1] - (offsets[0] + 7) < 10:
        raise ValueError('批间着陆间隔不足10分钟')
    tasks = []
    electrical_jobs = []
    for batch, offset in enumerate(offsets, 1):
        for op in template['operations']:
            tasks.append({**op, 'batch': batch, 'start_min': op['start_min'] + offset,
                          'end_min': op['end_min'] + offset})
        for job in template['electrical_jobs']:
            electrical_jobs.append({**job, 'batch': batch, 'start_min': job['start_min'] + offset,
                                    'end_min': job['end_min'] + offset})
    out = {'status': 'CONSTRUCTED', 'complete_problem3': False,
           'scope': '两批、单跑道、无驰援；沿用已核验单批排程，批次不重叠',
           'source_template_sha256': hashlib.sha256(raw).hexdigest(),
           'batch_first_touchdown_min': list(offsets), 'inter_batch_gap_min': offsets[1] - offsets[0] - 7,
           'makespan_min': offsets[-1] + last_end, 'operations': tasks,
           'electrical_jobs': electrical_jobs}
    output = ROOT / 'results/q3_two_batch_slice.json'
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k not in ('operations', 'electrical_jobs')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
