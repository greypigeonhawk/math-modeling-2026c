"""第三题45波次完工时刻的解析下界，依模型合同的全局批次顺序。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    waves, batches_per_wave, aircraft_per_batch = 45, 12, 8
    batches = waves * batches_per_wave
    # Previous batch's last touchdown to next first >=10; 8 touchdowns
    # spaced >=1 imply adjacent first touchdowns differ >=7+10 minutes.
    last_batch_first = (batches - 1) * ((aircraft_per_batch - 1) + 10)
    # Two B planes have separate touchdowns; the later B cannot land before
    # batch-first+1. Minimum B path fuel(30), gas(3), meal(25), power(15).
    last_b_landing = last_batch_first + 1
    lower_bound = last_b_landing + 30 + 3 + 25 + 15
    out = {
        'metric': '第45波次最后完工时刻，相对K=0（分钟）',
        'lower_bound_minutes': lower_bound,
        'total_batches': batches,
        'last_batch_first_touchdown_lower_bound': last_batch_first,
        'later_B_touchdown_lower_bound': last_b_landing,
        'B_minimum_path_minutes': 73,
        'assumptions': ['全局批次按题面顺序相邻衔接，前批末机到下批首机至少10分钟',
                        '首架着陆与首道保障同时发生，K=0',
                        'B型飞机由第一技能人员完成再次保障的工序时间为下界',
                        '忽略资源冲突、跑道休息、返航限制，故只是必要下界'],
        'feasible_schedule_proved': False,
    }
    path = ROOT / 'results/q3_global_makespan_lower_bound.json'
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
