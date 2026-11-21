"""构造三种机场状态的第三问可行证书，并按附录9重建结果工作簿。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "results/问题3专项"
SOURCE = ROOT / "data/新2026C.docx"
NORMALIZED = ROOT / "results/q23_normalized.json"

SCENARIOS = {
    "场景1": ("机场完好", (3, 2, 4)),
    "场景2": ("甲停机坪停用", (3, 2, 4)),
    "场景3": ("乙跑道及地勤失能", (3, 1, 4)),
}
# 工序、车型、车数、人数、第一技能。施工区间使用半开区间。
OPERATIONS = {
    "tow": ("0102", "Z1", 1, 1, "01"),
    "parachute": ("0203", "Z9", 1, 2, "07"),
    "fuel": ("0204", "Z2", 1, 1, "02"),
    "oxygen": ("0405", "Z3", 1, 1, "05"),
    "nitrogen": ("0406", "Z4", 1, 1, "05"),
    "meal": ("0708", "Z8", 1, 2, "08"),
    "power": ("0809", "Z5", 1, 1, "04"),
    "aircon": ("0810", "Z6", 1, 1, "04"),
}
HEADERS = {
    "着陆与放飞": ("波次", "批次", "机型", "飞机编号", "停留跑道", "着陆时刻",
                 "保障完工时刻", "起飞时刻", "飞行返回上空时刻", "本波落地前上空等待"),
    "逐机工序": ("波次", "批次", "机型", "飞机编号", "停留跑道", "车辆类型", "车辆数量",
                 "人员数量", "人员隶属地勤", "人员第一技能", "再次出动保障工序",
                 "工序开始时刻", "工序结束时刻"),
    "批次与伞勤点": ("全局批次", "波次", "批次", "停留跑道", "人员隶属地勤", "首机着陆",
                  "末机着陆", "开设保伞点开始", "开设完成", "发伞结束", "该批完工"),
    "跑道休息": ("停留跑道", "人员隶属地勤", "累计批次", "触发全局批次", "停止接收时刻",
                 "休息开始", "休息结束"),
    "驰援": ("保障力量类型", "人员所属小组/车辆类型", "人员数量/装备数量",
             "起点机场", "终点机场", "出发时刻", "到达时刻"),
}


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def plan_batch(wave, batch, first, station, previous_return):
    """批内编号遵循附录9，实际落地顺序由机型关键路径决定。"""
    a_ids = range((batch - 1) * 6 + 1, batch * 6 + 1)
    b_ids = range(73 + (batch - 1) * 2, 73 + batch * 2)
    runway, team = f"F{station}", f"C{station}"
    landings, task_rows = [], []
    for position, aircraft in enumerate([*b_ids, *a_ids]):
        typ = "B" if aircraft >= 73 else "A"
        touchdown = first + position
        towed = position == 2
        oil_start = touchdown + (10 if towed else 0)
        gas_start = oil_start + (30 if typ == "B" else 15)
        meal_start = max(first + 22, gas_start + 3)
        electrical_start = meal_start + (25 if typ == "B" else 8)
        finish = electrical_start + 15
        parachute_start = first + 18 + position / 2
        times = {
            "fuel": (oil_start, gas_start),
            "oxygen": (gas_start, gas_start + 3),
            "nitrogen": (gas_start, gas_start + 3),
            "parachute": (parachute_start, parachute_start + 0.5),
            "meal": (meal_start, electrical_start),
            "power": (electrical_start, finish),
            "aircon": (electrical_start, finish),
        }
        if towed:
            times["tow"] = (touchdown, oil_start)
        key = (wave, batch, typ, aircraft, runway)
        waiting = "" if wave == 1 else touchdown - previous_return[aircraft]
        previous_return[aircraft] = finish + 120
        landings.append((*key, touchdown, finish, finish, finish + 120, waiting))
        for name, (start, end) in times.items():
            code, vehicle, count, staff, skill = OPERATIONS[name]
            task_rows.append((*key, vehicle, count, staff, team, skill, code, start, end))
    return sorted(landings, key=lambda row: row[3]), sorted(
        task_rows, key=lambda row: (row[3], row[11], row[10])
    )


def construct(waves, stations):
    schedule = {name: [] for name in HEADERS}
    received = {station: 0 for station in stations}
    previous_return = {}
    for number in range(waves * 12):
        wave, batch_index = divmod(number, 12)
        wave, batch = wave + 1, batch_index + 1
        index = number % 54
        station = stations[0] if index < 18 else stations[1 + (index - 18) % 2]
        runway, team = f"F{station}", f"C{station}"
        first = number * 17
        landings, tasks = plan_batch(wave, batch, first, station, previous_return)
        finish = max(row[6] for row in landings)
        schedule["着陆与放飞"].extend(landings)
        schedule["逐机工序"].extend(tasks)
        schedule["批次与伞勤点"].append(
            (number + 1, wave, batch, runway, team, first, first + 7,
             first + 12, first + 18, first + 22, finish)
        )
        received[station] += 1
        if received[station] % 18 == 0:
            schedule["跑道休息"].append(
                (runway, team, received[station], number + 1, first + 7, finish, finish + 180)
            )
    return schedule


def write_excel(output, schedules):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    for name, suffix, time_start in (("驰援", "2-1", 5), ("逐机工序", "2-2", 11)):
        workbook = Workbook(write_only=True)
        workbook.properties.title = f"第三问{name}（依据附录9重建）"
        for code, schedule in schedules.items():
            sheet = workbook.create_sheet(code)
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS[name]))}{len(schedule[name]) + 1}"
            header = []
            for column, label in enumerate(HEADERS[name], 1):
                sheet.column_dimensions[get_column_letter(column)].width = max(10, len(label) * 2 + 3)
                cell = WriteOnlyCell(sheet, value=label)
                cell.fill = PatternFill("solid", fgColor="234968")
                cell.font = Font(bold=True, color="FFFFFF")
                cell.alignment = Alignment(vertical="center")
                header.append(cell)
            sheet.append(header)
            for row in schedule[name]:
                cells = list(row[:time_start])
                for minute in row[time_start:]:
                    cell = WriteOnlyCell(sheet, value=minute)
                    cell.number_format = "0.0"
                    cells.append(cell)
                sheet.append(cells)
        workbook.save(output / f"C_Solution{suffix}_按附录9重建.xlsx")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--waves", type=int, default=45, choices=range(1, 46), metavar="1–45")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--excel", action="store_true")
    args = parser.parse_args()
    data = json.loads(NORMALIZED.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if data["source_sha256"] != source_hash:
        raise ValueError("归一化资源表与源题面不匹配")
    results = {}
    for code, (label, stations) in SCENARIOS.items():
        paths = args.output / code
        paths.mkdir(parents=True, exist_ok=True)
        schedule = construct(args.waves, stations)
        results[code] = schedule
        for name, rows in schedule.items():
            write_csv(paths / f"{name}.csv", HEADERS[name], rows)
        print(f"{code} {label} {len(schedule['着陆与放飞'])} 次保障，"
              f"最后保障完工 K+{max(row[6] for row in schedule['着陆与放飞'])} 分钟")
    if args.excel:
        write_excel(args.output, results)


if __name__ == "__main__":
    main()
