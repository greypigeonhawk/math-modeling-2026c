"""问题2：只计算题面车辆数量及车时约束给出的必要下界。

该松弛忽略工序顺序、人员、技能和跨机型效率损失；不能证明可行或最优。
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    data = json.loads((ROOT / 'results/q23_normalized.json').read_text(encoding='utf-8'))
    m = data['airport_resources']['M']['vehicles']
    nstock = data['airport_resources']['N']['vehicles']
    rows = []
    for b in (16, 24, 30):
        total = 32 + b
        tow = math.ceil(total / 10)
        tow_vehicles = math.ceil(tow / 2) if tow <= 4 else (math.ceil(tow / 1.5) if tow <= 8 else math.ceil(tow / 1.2))
        required = {
            'Z1': (tow_vehicles, '牵引数量规则，牵引数量向上取整'),
            # After refueling every aircraft needs at least gas (3 min), meal
            # (A 8 / B 25 min), then power/aircon (15 min). Thus B fueling
            # finishes by minute 77 and A fueling by minute 94. Jobs are
            # nonpreemptive: each vehicle can handle at most 2 B jobs by 77,
            # and at most 6 fifteen-minute units by 94 (B consumes two units).
            'Z2': (max(math.ceil(b / (77 // 30)), math.ceil((32 + 2 * b) / (94 // 15))),
                   '不可中断加油；B截止77分钟，全部截止94分钟，按完整任务数计算'),
            'Z3': (math.ceil(total / 10), '题面按飞机总数向上取整'),
            'Z4': (math.ceil(total / 10), '题面按飞机总数向上取整'),
            'Z5': (math.ceil(total * 2 * 15 / 2 / 120), '两阶段电源总车时/120分钟，每车最多同时两架'),
            'Z6': (math.ceil(total * 2 * 15 / 2 / 120), '两阶段空调总车时/120分钟，每车最多同时两架'),
            'Z7': (math.ceil(tow * 10 / 120), '附油总车时/120分钟，数量向上取整'),
            'Z8': (math.ceil((32 * 8 + b * 25) / 120), '餐食总车时/120分钟'),
            'Z9': (math.ceil((math.ceil(total / 40) * 6 + total * .5) / 120), '仅计必需伞勤车时；航材需求数量未明，予以放宽'),
        }
        for vehicle, (need, basis) in required.items():
            rows.append({'A': 32, 'B': b, 'vehicle': vehicle, 'M_stock': m[vehicle],
                         'N_stock': nstock[vehicle], 'total_required_lb': need,
                         'N_dispatch_lb': max(0, need - m[vehicle]), 'basis': basis})
    out = ROOT / 'results/q2_vehicle_lower_bounds.csv'
    with out.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'source_sha256': data['source_sha256'], 'output': str(out),
                      'total_vehicle_dispatch_lower_bound': {
                          str(b): sum(r['N_dispatch_lb'] for r in rows if r['B'] == b)
                          for b in (16, 24, 30)},
                      'warning': '必要下界，不是可行方案或最优解'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
