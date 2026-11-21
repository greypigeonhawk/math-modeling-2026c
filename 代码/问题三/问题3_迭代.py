"""复验第三问固定轮转的车数下界，并导出改进排程与题目工作簿。"""
from argparse import ArgumentParser
import json
from pathlib import Path

from openpyxl import load_workbook
from ortools.sat.python import cp_model

from 问题3_低峰值排程 import batch_rows
from 问题3_排程 import HEADERS, ROOT, SCENARIOS, write_csv
from 问题3_复核 import read_rows, source_limits, verify_case

BASE = ROOT / "results/问题3_低峰值版"
OUTPUT = ROOT / "results/问题3_迭代版"


def solve(model):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 5
    return solver, solver.solve(model)


def dense_boundary(capacity):
    """仅保留加油和由80分钟倒推的结束时限，放宽其余限制。"""
    model = cp_model.CpModel()
    intervals = []
    for batch in range(18):
        for position in range(8):
            landing = 17 * batch + position
            is_b = position < 2
            duration = 30 if is_b else 15
            slack = 7 if is_b else 39
            start = model.new_int_var(landing, landing + slack, "")
            intervals.append(model.new_fixed_size_interval_var(start, duration, ""))
    model.add_cumulative(intervals, [1] * len(intervals), capacity)
    solver, status = solve(model)
    return solver.status_name(status)


def optimize_alternating():
    """固定34分钟重复模板、5辆Z2及上一版其余峰值，最小化A型最长保障。"""
    model = cp_model.CpModel()
    caps = {"fuel": 5, "gas": 2, "meal": 5, "electrical": 5, "A": 12, "B": 6}
    intervals = {resource: [] for resource in caps}
    fuel_starts = []
    max_a = model.new_int_var(41, 59, "max_a")
    for j in range(8):
        is_b = j < 2
        fuel_time = 30 if is_b else 15
        meal_time = 25 if is_b else 8
        fuel = model.new_int_var(j + (10 if j == 2 else 0), j + (0 if is_b else 18), "")
        fuel_starts.append(fuel)
        gas = fuel + fuel_time
        meal = model.new_int_var(22, 55, "")
        model.add_max_equality(meal, [gas + 3, 22])
        electrical = meal + meal_time
        finished = electrical + 15
        parked = model.new_int_var(41, 73, "")
        model.add(parked == finished - j)
        if not is_b:
            model.add(parked <= max_a)
        for offset in (-68, -34, 0, 34, 68):
            for resource, start, length in (
                ("fuel", fuel, fuel_time), ("gas", gas, 3),
                ("meal", meal, meal_time), ("electrical", electrical, 15),
            ):
                intervals[resource].append(model.new_fixed_size_interval_var(start + offset, length, ""))
            intervals["B" if is_b else "A"].append(model.new_interval_var(j + offset, parked, finished + offset, ""))
    for resource, cap in caps.items():
        model.add_cumulative(intervals[resource], [1] * len(intervals[resource]), cap)
    model.minimize(max_a)
    solver, status = solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(f"五辆加油车模板：{solver.status_name(status)}")
    return {
        "status": solver.status_name(status), "best_bound": solver.best_objective_bound,
        "max_a": solver.value(max_a), "starts": [solver.value(item) for item in fuel_starts],
    }


def schedule_case(output, case, dense_runway, starts, waves):
    original = BASE / case
    schedule = {name: [] for name in HEADERS}
    previous_return = {}
    for row in read_rows(original, "批次与伞勤点")[:waves * 12]:
        wave, batch = int(row["波次"]), int(row["批次"])
        runway, team = row["停留跑道"], row["人员隶属地勤"]
        first = int(row["首机着陆"])
        landing, tasks = batch_rows(wave, batch, first, runway, team, previous_return,
                                    starts["dense" if runway == dense_runway else "alternating"])
        if max(item[6] for item in landing) != int(row["该批完工"]):
            raise ValueError(f"{case} {wave}/{batch} 的批次完工时刻已经变化")
        schedule["着陆与放飞"].extend(landing)
        schedule["逐机工序"].extend(tasks)
        schedule["批次与伞勤点"].append(tuple(row.values()))
    schedule["跑道休息"] = [
        tuple(row.values()) for row in read_rows(original, "跑道休息")
        if int(row["触发全局批次"]) <= waves * 12
    ]
    directory = output / case
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in schedule.items():
        write_csv(directory / f"{name}.csv", HEADERS[name], rows)
    return schedule


def fill_templates(output, schedules):
    templates = {
        "驰援": ("附件2  C_Solution2-1.xlsx", "C_Solution2-1.xlsx"),
        "逐机工序": ("附件3  C_Solution2-2.xlsx", "C_Solution2-2.xlsx"),
    }
    for field, (template, target) in templates.items():
        book = load_workbook(ROOT / "附件模版" / template)
        for index, schedule in enumerate(schedules.values(), 1):
            sheet = book[f"问题3（{index}）"]
            for row in sheet.iter_rows(min_row=2, max_col=len(HEADERS[field])):
                for cell in row:
                    cell.value = None
            for row_index, row in enumerate(schedule[field], 2):
                for column, value in enumerate(row, 1):
                    cell = sheet.cell(row_index, column, value)
                    if column >= 12:
                        cell.number_format = "0.0"
        path = output / target
        book.save(path)
        book.close()
        check = load_workbook(path, read_only=True)
        template_book = load_workbook(ROOT / "附件模版" / template, read_only=True)
        try:
            if check.sheetnames != template_book.sheetnames:
                raise ValueError(f"{target} 工作表名变化")
            for index, (produced, source) in enumerate(zip(check, template_book), 1):
                expected = schedules[f"场景{index}"][field]
                rows = produced.iter_rows(values_only=True)
                if next(rows) != next(source.iter_rows(values_only=True)):
                    raise ValueError(f"{target} 第{index}张表表头变化")
                values = [row for row in rows if any(value is not None for value in row)]
                if values != expected:
                    raise ValueError(f"{target} 第{index}张表与排程不同")
                if field == "逐机工序" and any(
                    cell.number_format != "0.0" for row in produced.iter_rows(min_row=2, min_col=12, max_col=13)
                    for cell in row if cell.value is not None
                ):
                    raise ValueError(f"{target} 第{index}张表时刻格式错误")
        finally:
            check.close()
            template_book.close()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--waves", type=int, default=45, choices=range(1, 46), metavar="1–45")
    parser.add_argument("--excel", action="store_true")
    args = parser.parse_args()
    from 问题3_低峰值排程 import FUEL_DENSE

    forced_8 = dense_boundary(8)
    optimum = optimize_alternating()
    starts = {"dense": FUEL_DENSE, "alternating": optimum["starts"]}
    parking, stock = source_limits()
    schedules = {}
    checks = {}
    for case, (_, stations) in SCENARIOS.items():
        case_stock = {runway: values.copy() for runway, values in stock.items()}
        for station, count in zip(stations, (9, 5, 5)):
            case_stock[f"F{station}"]["Z2"] = count
        schedules[case] = schedule_case(args.output, case, f"F{stations[0]}", starts, args.waves)
        checks[case] = verify_case(args.output / case, case, args.waves, parking, case_stock)
    if args.excel:
        fill_templates(args.output, schedules)
    result = {
        "dense_Z2_8_relaxation": forced_8,
        "alternating_template": optimum,
        "scenarios": checks,
        "source_template_verified": args.excel,
    }
    (args.output / "复核结果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dense_Z2_8": forced_8, "alternating": optimum}, ensure_ascii=False))
    for case, info in checks.items():
        print(case, "PASS", info["完工分钟"], "A max", info["A机最长保障"], "驰援", info["跨跑道调动"])


if __name__ == "__main__":
    main()
