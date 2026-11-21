"""第三问轮转动态规划与单站工序容量搜索。"""
from argparse import ArgumentParser
from collections import Counter
import json
from pathlib import Path
from random import Random

from ortools.sat.python import cp_model

from 问题3_低峰值排程 import batch_rows
from 问题3_排程 import HEADERS, ROOT, SCENARIOS, write_csv
from 问题3_复核 import source_limits, verify_case
from 问题3_迭代 import fill_templates

OUTPUT = ROOT / "results/问题3_扩大搜索版"
HORIZON = 540


def solve(slots, capacity, max_a, parking=24, seconds=1):
    """求一个接收区段的加油开工时刻，按最早规则衔接其余工序。"""
    model = cp_model.CpModel()
    capacities = {
        "fuel": capacity, "gas": 4, "meal": 8, "electrical": 10,
        "A": parking, "B": 12,
    }
    intervals = {resource: [] for resource in capacities}
    fuel_starts = []
    for slot in slots:
        first = 17 * slot
        starts = []
        for position in range(8):
            landing = first + position
            is_b = position < 2
            fuel_time = 30 if is_b else 15
            meal_time = 25 if is_b else 8
            fuel = model.new_int_var(
                landing + (10 if position == 2 else 0),
                landing + (0 if is_b else max_a - 41),
                "",
            )
            gas = fuel + fuel_time
            meal = model.new_int_var(first + 22, landing + (33 if is_b else max_a - 23), "")
            model.add_max_equality(meal, [gas + 3, first + 22])
            electrical = meal + meal_time
            done = electrical + 15
            on_ground = model.new_int_var(41, 73, "")
            model.add(on_ground == done - landing)
            for resource, start, duration in (
                ("fuel", fuel, fuel_time), ("gas", gas, 3),
                ("meal", meal, meal_time), ("electrical", electrical, 15),
            ):
                intervals[resource].append(model.new_fixed_size_interval_var(start, duration, ""))
            intervals["B" if is_b else "A"].append(model.new_interval_var(landing, on_ground, done, ""))
            starts.append(fuel)
        fuel_starts.append(starts)
    for resource, limit in capacities.items():
        model.add_cumulative(intervals[resource], [1] * len(intervals[resource]), limit)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = seconds
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return solver.status_name(status), None
    starts = [[solver.value(var) - slot * 17 for var in row]
              for slot, row in zip(slots, fuel_starts)]
    return solver.status_name(status), starts


def rotations(length, window, limit, seed, cooldown=14):
    """枚举可达状态，保留每个状态的一个可复现前驱。"""
    rng = Random(seed)
    mask = (1 << window) - 1
    levels = [{((0, 0), (0, 0), (0, 0), 0, -1): None}]
    visited = 1
    for _ in range(length):
        next_level = {}
        for state in levels[-1]:
            stations = state[:3]
            history, previous = state[3:]
            for station, (count, hold) in enumerate(stations):
                next_history = ((history << 1) + (station == 0)) & mask
                if hold or (station and station == previous) or next_history.bit_count() > limit:
                    continue
                after = [(n, max(0, d - 1)) for n, d in stations]
                after[station] = (count + 1, 0) if count < 17 else (0, cooldown)
                swap = after[2] < after[1]
                if swap:
                    after[1], after[2] = after[2], after[1]
                new_previous = 3 - station if swap and station else station
                new = (*after, next_history, new_previous)
                if new not in next_level or (seed and rng.random() < 0.25):
                    next_level[new] = (state, station, swap)
        if not next_level:
            return None, visited
        levels.append(next_level)
        visited += len(next_level)
    terminal = min(levels[-1], key=lambda s: (sum(count for count, _ in s[:3]), sum(hold for _, hold in s[:3])))
    actions = []
    for level in reversed(levels[1:]):
        terminal, station, swap = level[terminal]
        actions.append((station, swap))
    labels = [0, 1, 2]
    sequence = []
    for station, swap in reversed(actions):
        sequence.append(labels[station])
        if swap:
            labels[1], labels[2] = labels[2], labels[1]
    return sequence, visited


def assess(sequence, caps, amax, cache):
    fuels = {}
    status_counts = Counter()
    for role in range(3):
        slots = [index for index, value in enumerate(sequence) if value == role]
        for start in range(0, len(slots), 18):
            section = slots[start:start + 18]
            relative = tuple(slot - section[0] for slot in section)
            key = relative, caps[role], amax, 24 if role == 0 else 12
            if key not in cache:
                cache[key] = solve(*key)
            status, starts = cache[key]
            status_counts[status] += 1
            if starts is not None:
                fuels.update(zip(section, starts))
    return fuels if len(fuels) == len(sequence) else None, dict(status_counts)


def export_solution(output, sequence, fuels, caps, excel):
    parking, stock = source_limits()
    schedules = {}
    results = {}
    for case, (_, stations) in SCENARIOS.items():
        schedule = {name: [] for name in HEADERS}
        previous_return = {}
        counts = [0] * 3
        case_stock = {runway: values.copy() for runway, values in stock.items()}
        for number, cap in zip(stations, caps):
            case_stock[f"F{number}"]["Z2"] = cap
        for index, role in enumerate(sequence):
            station = stations[role]
            time = index * 17
            runway, team = f"F{station}", f"C{station}"
            wave, batch = divmod(index, 12)
            landing, tasks = batch_rows(wave + 1, batch + 1, time, runway, team, previous_return, fuels[index])
            done = max(item[6] for item in landing)
            schedule["着陆与放飞"].extend(landing)
            schedule["逐机工序"].extend(tasks)
            schedule["批次与伞勤点"].append(
                (index + 1, wave + 1, batch + 1, runway, team, time, time + 7, time + 12, time + 18, time + 22, done)
            )
            counts[role] += 1
            if counts[role] % 18 == 0:
                schedule["跑道休息"].append(
                    (runway, team, counts[role], index + 1, time + 7, done, done + 180)
                )
        directory = output / case
        directory.mkdir(parents=True, exist_ok=True)
        for field, rows in schedule.items():
            write_csv(directory / f"{field}.csv", HEADERS[field], rows)
        result = verify_case(directory, case, len(sequence) // 12, parking, case_stock)
        if result["完工差距分钟"] != 0 or result["跨跑道调动"] != 0:
            raise ValueError(f"{case} 未保持完工下界和零驰援")
        schedules[case], results[case] = schedule, result
    if excel:
        fill_templates(output, schedules)
    return results


def refine_buffer(output, summary, excel):
    """在已找到的车辆与保障时间上界下，增加本站下一批落地的余量。"""
    caps = tuple(summary["configuration"])
    max_a = summary["objective"][1]
    cache = {}
    tested = []
    for cooldown in range(22, 14, -1):
        for window, limit in ((3, 2), (5, 3), (7, 4)):
            sequence, visited = rotations(HORIZON, window, limit, 0, cooldown)
            entry = {"cooldown": cooldown, "window": window, "limit": limit,
                     "seed": 0, "visited_states": visited}
            tested.append(entry)
            if sequence is None:
                entry["status"] = "unreachable"
                continue
            fuels, statuses = assess(sequence, caps, max_a, cache)
            entry["block_statuses"] = statuses
            entry["status"] = "candidate" if fuels else "failed"
            if fuels is None:
                continue
            for tighter in range(max_a - 1, 50, -1):
                tighter_fuels, tighter_statuses = assess(sequence, caps, tighter, cache)
                entry.setdefault("tighter_A", []).append({"min": tighter, "statuses": tighter_statuses})
                if tighter_fuels is None:
                    break
                max_a, fuels = tighter, tighter_fuels
            summary["initial_rotation_origin"] = summary.get("initial_rotation_origin", summary["rotation_origin"])
            summary["rotation_origin"] = [window, limit, 0, cooldown]
            summary["objective"] = [sum(caps), max_a]
            summary["buffer_refinement"] = {"rounds": tested, "unique_station_block_models": len(cache)}
            summary["scenarios"] = export_solution(output, sequence, fuels, caps, excel)
            print("增加休息余量", cooldown, window, limit, "A 型上界", max_a, flush=True)
            return summary
    summary["buffer_refinement"] = {"rounds": tested, "unique_station_block_models": len(cache)}
    return summary


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--excel", action="store_true")
    parser.add_argument("--slice", action="store_true", help="仅复核6波次的一个候选")
    parser.add_argument("--refine-buffer", action="store_true", help="从已有全量搜索结果继续搜索休息余量")
    args = parser.parse_args()
    result_path = args.output / "搜索与复核.json"
    if args.refine_buffer:
        summary = json.loads(result_path.read_text(encoding="utf-8"))
        summary = refine_buffer(args.output, summary, args.excel)
        result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    length = 72 if args.slice else HORIZON
    limits = [(3, 2)] if args.slice else [(3, 2), (4, 2), (5, 3), (6, 3), (7, 4), (8, 4)]
    seeds = [0] if args.slice else list(range(10))
    caps_options = [(8, 5, 5)] if args.slice else [(7, 4, 5), (8, 4, 4), (7, 5, 5), (8, 4, 5), (8, 5, 5)]
    history = []
    cache = {}
    best = None
    seen = set()
    for window, limit in limits:
        for seed in seeds:
            sequence, visited = rotations(length, window, limit, seed)
            entry = {"window": window, "limit": limit, "seed": seed, "visited_states": visited}
            history.append(entry)
            if sequence is None:
                entry["rotation"] = "unreachable"
                break
            if tuple(sequence) in seen:
                entry["rotation"] = "duplicate"
                continue
            seen.add(tuple(sequence))
            entry["rotation"] = "tested"
            entry["configurations"] = []
            for caps in caps_options:
                for amax in (57,) if args.slice else (57, 56, 55, 54, 53, 52, 51):
                    fuels, statuses = assess(sequence, caps, amax, cache)
                    entry["configurations"].append({"Z2": caps, "max_a": amax, "block_statuses": statuses})
                    if fuels is None:
                        if "UNKNOWN" not in statuses:
                            break
                        continue
                    key = sum(caps), amax
                    if best is None or key < best[0]:
                        best = key, caps, sequence, fuels, (window, limit, seed)
                        print("更新候选", key, caps, window, limit, seed, flush=True)
    if best is None:
        raise ValueError("本次搜索未找到可交付候选")
    key, caps, sequence, fuels, origin = best
    results = export_solution(args.output, sequence, fuels, caps, args.excel)
    summary = {
        "status": "PASS", "rounds": history, "unique_rotations": len(seen),
        "unique_station_block_models": len(cache), "configuration": caps,
        "objective": key, "rotation_origin": origin, "scenarios": results,
    }
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("输出", args.output, "轮转", len(seen), "工序模型", len(cache), flush=True)


if __name__ == "__main__":
    main()
