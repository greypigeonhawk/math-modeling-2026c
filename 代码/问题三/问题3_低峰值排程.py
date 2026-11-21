"""第三问减配证书。保留落地分配及完工节拍，压低加油车并发峰值。"""
from argparse import ArgumentParser
from pathlib import Path

from 问题3_排程 import HEADERS, OPERATIONS, ROOT, SCENARIOS, write_csv, write_excel

OUTPUT = ROOT / "results/问题3_低峰值版"
# B型机两项加油即时开始，以达到关键路径下界。
# 首架A机先牵引10分钟。其余A机按本站的34或17分钟批距布置加油。
FUEL_DENSE = (0, 1, 13, 3, 5, 7, 9, 11)
FUEL_ALTERNATING = (0, 1, 20, 9, 5, 23, 24, 8)


def batch_rows(wave, batch, time, runway, team, previous_return, fuel_starts):
    # 附录9规定A型1–72、B型73–96。批内落地先B后A。
    start_a, start_b = 6 * (batch - 1) + 1, 2 * (batch - 1) + 73
    aircraft_ids = [start_b, start_b + 1, *range(start_a, start_a + 6)]
    landings, operations = [], []
    for p, aircraft in enumerate(aircraft_ids):
        b_type = p < 2
        fuel = fuel_starts[p]
        gas = fuel + (30 if b_type else 15)
        meal = max(gas + 3, 22)
        electrical = meal + (25 if b_type else 8)
        done = time + electrical + 15
        chute = 18 + p / 2
        times = {
            "fuel": (fuel, gas),
            "oxygen": (gas, gas + 3),
            "nitrogen": (gas, gas + 3),
            "parachute": (chute, chute + 0.5),
            "meal": (meal, electrical),
            "power": (electrical, electrical + 15),
            "aircon": (electrical, electrical + 15),
        }
        if p == 2:
            times["tow"] = (p, p + 10)
        key = (wave, batch, "B" if b_type else "A", aircraft, runway)
        landing = time + p
        waiting = landing - previous_return[aircraft] if wave > 1 else ""
        previous_return[aircraft] = done + 120
        landings.append((*key, landing, done, done, done + 120, waiting))
        for task, (begin, end) in times.items():
            code, vehicle, count, staff, skill = OPERATIONS[task]
            operations.append((*key, vehicle, count, staff, team, skill, code, time + begin, time + end))
    landings.sort(key=lambda row: row[3])
    operations.sort(key=lambda row: (row[3], row[11], row[10]))
    return landings, operations


def construct(waves, stations):
    schedule = {field: [] for field in HEADERS}
    counts = dict.fromkeys(stations, 0)
    previous_return = {}
    for index in range(waves * 12):
        wave, batch = index // 12 + 1, index % 12 + 1
        slot = index % 54
        dense = slot < 18
        station = stations[0] if dense else stations[1 + (slot - 18) % 2]
        fuel_starts = FUEL_DENSE if dense else FUEL_ALTERNATING
        time = 17 * index
        runway, team = f"F{station}", f"C{station}"
        landings, operations = batch_rows(wave, batch, time, runway, team, previous_return, fuel_starts)
        done = max(row[6] for row in landings)
        schedule["着陆与放飞"].extend(landings)
        schedule["逐机工序"].extend(operations)
        schedule["批次与伞勤点"].append(
            (index + 1, wave, batch, runway, team, time, time + 7, time + 12, time + 18, time + 22, done)
        )
        counts[station] += 1
        if counts[station] % 18 == 0:
            schedule["跑道休息"].append(
                (runway, team, counts[station], index + 1, time + 7, done, done + 180)
            )
    return schedule


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--waves", type=int, default=45, choices=range(1, 46), metavar="1–45")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--excel", action="store_true")
    args = parser.parse_args()
    schedules = {case: construct(args.waves, stations) for case, (_, stations) in SCENARIOS.items()}
    for case, schedule in schedules.items():
        directory = args.output / case
        directory.mkdir(parents=True, exist_ok=True)
        for name, rows in schedule.items():
            write_csv(directory / f"{name}.csv", HEADERS[name], rows)
    if args.excel:
        write_excel(args.output, schedules)


if __name__ == "__main__":
    main()
