"""单跑道串行批次与第18批后的休息切片；用于验证模型机制。"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batches', type=int, default=19)
    ap.add_argument('--output', type=Path, default=ROOT / 'results/q3_rest_slice.json')
    args = ap.parse_args()
    if not 1 <= args.batches <= 24:
        ap.error('切片上限24批；完整45波次模型尚未实现')
    raw = (ROOT / 'results/q3_batch_prototype.json').read_bytes()
    t = json.loads(raw)
    if t['status'] not in ('FEASIBLE', 'OPTIMAL') or t['team'] != '甲':
        raise ValueError('需要有效的甲地勤单批模板')
    duration = max(x['end_min'] for x in t['operations'])
    offsets, rest = [], []
    time = 0
    for idx in range(args.batches):
        if idx and idx % 18 == 0:
            # Assumption: finish batch 18 before resting;
            # no work or landing occurs during the ensuing 180 minutes.
            rest_start = offsets[-1] + duration
            rest.append({'after_batch': idx, 'start_min': rest_start, 'end_min': rest_start + 180})
            time = max(time, rest_start + 180)
        offsets.append(time)
        time += 100
    # Same 96 planes recur every 12 batches; preserve IDs A1..72, B73..96.
    batches = []
    for i, start in enumerate(offsets):
        within_wave = i % 12
        ids = list(range(6*within_wave+1, 6*within_wave+7)) + [73+2*within_wave, 74+2*within_wave]
        batches.append({'batch': i+1, 'wave': i//12+1, 'start_min': start,
                        'last_landing_min': start+7, 'last_finish_min': start+duration, 'aircraft_ids': ids})
    result = {'scope': '单跑道串行切片，无驰援；休息从第18批保障完毕起算',
              'complete_problem3': False, 'template_sha256': hashlib.sha256(raw).hexdigest(),
              'batches': batches, 'rest_windows': rest}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'batch_count': len(batches), 'rest_windows': rest,
                      'last_finish_min': batches[-1]['last_finish_min'],
                      'complete_problem3': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
