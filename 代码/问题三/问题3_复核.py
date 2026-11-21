"""从原题表6/7独立读库存和停机容量，检查第三问排程与附件。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from itertools import accumulate, pairwise, zip_longest
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/新2026C.docx"
DEFAULT_OUTPUT = ROOT / "results/问题3专项"
CASE_NAMES = {"场景1": "机场完好", "场景2": "甲停机坪停用", "场景3": "乙跑道及地勤失能"}
TASKS = {
    # 附录6表5工时（A、B）、车型、小组、人/辆、附录9第一技能。
    "0102": (10, 10, "Z1", "M5", 1, "01"),
    "0203": (0.5, 0.5, "Z9", "M4", 2, "07"),
    "0204": (15, 30, "Z2", "M6", 1, "02"),
    "0405": (3, 3, "Z3", "M8", 1, "05"),
    "0406": (3, 3, "Z4", "M8", 1, "05"),
    "0708": (8, 25, "Z8", "M1", 2, "08"),
    "0809": (15, 15, "Z5", "M7", 1, "04"),
    "0810": (15, 15, "Z6", "M7", 1, "04"),
}
PRECEDENCE = (
    ("0204", "0405"), ("0204", "0406"), ("0405", "0708"), ("0406", "0708"),
    ("0708", "0809"), ("0708", "0810"), ("0203", "0809"), ("0203", "0810"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def table_rows(table):
    return ([cell.text.strip() for cell in row.cells] for row in table.rows)


def source_limits():
    doc = Document(SOURCE)
    parking, stock = defaultdict(dict), defaultdict(dict)
    for number, _, capacity in list(table_rows(doc.tables[5]))[1:]:
        typ, count = re.fullmatch(r"([AB])种飞机(\d+)架", re.sub(r"\s+", "", capacity)).groups()
        parking[f"F{number}"][typ] = int(count)
    for _, resource, *quantities in list(table_rows(doc.tables[6]))[1:]:
        for station, quantity in enumerate(quantities, 1):
            stock[f"F{station}"][resource] = int(quantity)
    require(len(parking) == 7 and all(set(row) == {"A", "B"} for row in parking.values()),
            "表6停机坪数据不完整")
    require(len(stock) == 4 and all(len(row) == 17 for row in stock.values()),
            "表7车人数据不完整")
    return parking, stock


def read_rows(directory, name):
    with (directory / f"{name}.csv").open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def interval(row, start, end):
    a, b = float(row[start]), float(row[end])
    require(math.isfinite(a) and math.isfinite(b) and a >= 0 and a < b, f"非法区间 {row}")
    return a, b


def aircraft_key(row):
    return int(row["波次"]), int(row["批次"]), int(row["飞机编号"])


def batch_key(row):
    return int(row["波次"]), int(row["批次"])


def add(events, key, span, amount=1):
    start, end = span
    events[key].extend(((start, amount), (end, -amount)))


def measure(events):
    return {key: max(accumulate(delta for _, delta in sorted(items)), default=0)
            for key, items in events.items()}


def verify_case(directory, case, waves, parking, stock):
    by_batch, by_plane = defaultdict(list), defaultdict(list)
    occupancy, jobs, duty = defaultdict(list), defaultdict(list), defaultdict(list)
    schedule, tasks = {}, defaultdict(dict)
    rests = read_rows(directory, "跑道休息")
    batch_rows = read_rows(directory, "批次与伞勤点")
    operations = read_rows(directory, "逐机工序")
    landings = read_rows(directory, "着陆与放飞")
    require(not read_rows(directory, "驰援"), f"{case} 声称零驰援但存在调动")
    prohibited = {"场景2": {"F1"}, "场景3": {"F2"}}.get(case, set())

    for row in landings:
        wave, batch, plane = key = aircraft_key(row)
        runway, typ = row["停留跑道"], row["机型"]
        require(runway in stock and runway not in prohibited, f"{case} 在禁用或无驻场保障的跑道停机")
        require(key not in schedule and 1 <= wave <= waves and 1 <= batch <= 12,
                f"{case} 飞机记录重复或索引越界 {key}")
        allowed_ids = range(6 * batch - 5, 6 * batch + 1) if typ == "A" else range(2 * batch + 71, 2 * batch + 73)
        require(typ in {"A", "B"} and plane in allowed_ids, f"机型、编号或批次错误 {key}")
        landing, takeoff = interval(row, "着陆时刻", "起飞时刻")
        finish = float(row["保障完工时刻"])
        over_airport = float(row["飞行返回上空时刻"])
        require(landing < finish <= min(takeoff, landing + 80), f"{key} 保障窗口或起飞错误")
        require(over_airport == takeoff + 120, f"{key} 飞行时长错误")
        schedule[key] = row
        by_batch[(wave, batch)].append(row)
        by_plane[plane].append(row)
        for kind in (typ, "合计"):
            add(occupancy, (runway, kind), (landing, takeoff))

    min_return_slack, max_return_slack = math.inf, 0
    ground_by_type = defaultdict(list)
    require(len(landings) == waves * 96 and len(by_plane) == 96, f"{case} 机队规模错误")
    for plane, rows in by_plane.items():
        rows.sort(key=aircraft_key)
        require([aircraft_key(row)[0] for row in rows] == list(range(1, waves + 1)), f"{plane} 波次缺失")
        require(rows[0]["本波落地前上空等待"] == "", "首波入场等待时刻未知，应留空")
        for row in rows:
            ground_by_type[row["机型"]].append(float(row["保障完工时刻"]) - float(row["着陆时刻"]))
        for previous, current in pairwise(rows):
            slack = float(current["着陆时刻"]) - float(previous["飞行返回上空时刻"])
            require(slack >= 0 and slack == float(current["本波落地前上空等待"]), f"{plane} 提前落地")
            min_return_slack = min(min_return_slack, slack)
            max_return_slack = max(max_return_slack, slack)

    order = [(aircraft_key(row), float(row["工序开始时刻"]), row["再次出动保障工序"])
             for row in operations]
    require(order == sorted(order), "工序记录未按波次、批次、飞机、工序时刻排序")
    for row in operations:
        key = aircraft_key(row)
        code = row["再次出动保障工序"]
        require(code in TASKS and code not in tasks[key] and key in schedule, f"工序重复、未知或无对应飞机 {key}")
        ref = schedule[key]
        runway, typ = row["停留跑道"], row["机型"]
        require((runway, typ) == (ref["停留跑道"], ref["机型"]), f"工序站点或机型错配 {key}")
        require(row["人员隶属地勤"] == runway.replace("F", "C"), f"未驰援却使用异地地勤 {key}")
        start, end = interval(row, "工序开始时刻", "工序结束时刻")
        a_dur, b_dur, vehicle, staff_group, people, skill = TASKS[code]
        require((row["车辆类型"], row["车辆数量"], row["人员数量"], row["人员第一技能"])
                == (vehicle, "1", str(people), skill), f"车人配给错误 {key} {code}")
        require(end - start == (a_dur if typ == "A" else b_dur), f"工时错误 {key} {code}")
        require(float(ref["着陆时刻"]) <= start and end <= float(ref["保障完工时刻"]),
                f"工序超出在场和完工范围 {key} {code}")
        tasks[key][code] = start, end
        # Z9及两名送伞员从开点起占用，整批在下方按一个连续区间计入。
        if code != "0203":
            add(jobs, (runway, vehicle), (start, end))
            add(jobs, (runway, staff_group), (start, end), people)
            duty[runway].append((start, end))
    for key, row in schedule.items():
        timings = tasks[key]
        tow = "0102" in timings
        required = set(TASKS) if tow else set(TASKS) - {"0102"}
        require(set(timings) == required and (not tow or row["机型"] == "A"), f"工序缺失或牵引对象错误 {key}")
        edges = (*PRECEDENCE, ("0102", "0203"), ("0102", "0204")) if tow else PRECEDENCE
        require(all(timings[before][1] <= timings[after][0] for before, after in edges),
                f"工序前置次序错误 {key}")
        require(max(end for _, end in timings.values()) == float(row["保障完工时刻"]),
                f"保障完工时刻未按工序求取 {key}")

    by_runway = defaultdict(list)
    batch_slack, aircraft_slack = math.inf, math.inf
    previous_last = -math.inf
    require(len(batch_rows) == waves * 12, f"{case} 批次记录数错误")
    for index, batch in enumerate(batch_rows):
        w, q = divmod(index, 12)
        bkey = (w + 1, q + 1)
        require(batch_key(batch) == bkey and int(batch["全局批次"]) == index + 1, f"批次顺序错误 {bkey}")
        rows = sorted(by_batch[bkey], key=lambda r: float(r["着陆时刻"]))
        times = [float(row["着陆时刻"]) for row in rows]
        require(Counter(row["机型"] for row in rows) == {"A": 6, "B": 2}, f"批次构成错误 {bkey}")
        r = batch["停留跑道"]
        require({row["停留跑道"] for row in rows} == {r} and batch["人员隶属地勤"] == r.replace("F", "C"),
                f"批次分配、保障地勤或跑道错误 {bkey}")
        inner = min(b - a for a, b in pairwise(times))
        require(times[0] - previous_last >= 10 and inner >= 1, f"着陆间隔错误 {bkey}")
        batch_slack, aircraft_slack = min(batch_slack, times[0] - previous_last), min(aircraft_slack, inner)
        previous_last = times[-1]
        done = max(float(row["保障完工时刻"]) for row in rows)
        require([times[0], times[-1], done] == [float(batch[name]) for name in ("首机着陆", "末机着陆", "该批完工")],
                f"批次时刻与逐机记录不一致 {bkey}")
        timings = [tasks[aircraft_key(row)] for row in rows]
        require(sum("0102" in item for item in timings) == 1, f"牵引架数错误 {bkey}")
        site_start, site_end = interval(batch, "开设保伞点开始", "发伞结束")
        site_ready = float(batch["开设完成"])
        handouts = sorted(item["0203"] for item in timings)
        require(site_start >= times[0] and site_ready == site_start + 6 and len(handouts) <= 40
                and handouts[0][0] >= site_ready and handouts[-1][1] == site_end
                and all(a[1] <= b[0] for a, b in pairwise(handouts)), f"保伞点规则错误 {bkey}")
        require(all(item["0102"][1] <= site_start for item in timings if "0102" in item),
                f"保伞点未等待牵引完成 {bkey}")
        duty[r].append((site_start, site_end))
        add(jobs, (r, "Z9"), (site_start, site_end))
        add(jobs, (r, "M4"), (site_start, site_end), 2)
        by_runway[r].append((index + 1, times[0], times[-1], done))

    rest_map = {(row["停留跑道"], int(row["累计批次"])): row for row in rests}
    require(len(rest_map) == len(rests), "重复休息记录")
    margins = []
    for runway, batches in by_runway.items():
        for count in range(18, len(batches) + 1, 18):
            row = rest_map.pop((runway, count), None)
            require(row is not None, f"{runway} 第{count}批缺失休息记录")
            number, _, last, _ = batches[count - 1]
            start, end = interval(row, "休息开始", "休息结束")
            last_done = max(batch[3] for batch in batches[count - 18:count])
            require(row["人员隶属地勤"] == runway.replace("F", "C") and int(row["触发全局批次"]) == number
                    and float(row["停止接收时刻"]) == last and start >= last_done and end - start == 180,
                    f"{runway} 第{count}批休息窗错误")
            require(all(not (a < end and b > start) for a, b in duty[runway]), f"{runway} 休息中有工序")
            if count < len(batches):
                following = batches[count][1]
                require(following >= end, f"{runway} 未完成休息即接收新批")
                margins.append(following - end)
    require(not rest_map, "休息记录未与18批触发事件匹配")

    park_peak, task_peak = measure(occupancy), measure(jobs)
    for (runway, typ), count in park_peak.items():
        if typ == "合计":
            require(all(stock[runway][resource] >= math.ceil(count / 10) for resource in ("Z3", "Z4")),
                    f"{runway} 充气车辆配给下限不足")
        else:
            require(count <= parking[runway][typ], f"{runway} {typ}机停机容量不足")
    for (runway, resource), count in task_peak.items():
        require(count <= stock[runway][resource], f"{runway} {resource}库存不足")

    first_plane = min(landings, key=lambda row: float(row["着陆时刻"]))
    first_start = min(start for start, _ in tasks[aircraft_key(first_plane)].values())
    require(float(first_plane["着陆时刻"]) == first_start == 0 and order[0][0][0] == 1, "K时刻不一致")
    makespan = max(float(row["保障完工时刻"]) for row in landings if int(row["波次"]) == waves)
    require(makespan == max(float(row["保障完工时刻"]) for row in landings), "第45波并非最后完成")
    bound = (waves * 12 - 1) * 17 + 1 + TASKS["0204"][1] + TASKS["0405"][1] + TASKS["0708"][1] + TASKS["0809"][1]
    require(makespan >= bound, "证书完工早于解析下界")
    return {
        "场景": CASE_NAMES[case], "波次": waves, "批次": len(batch_rows), "保障架次": len(landings),
        "逐机工序记录": len(operations), "休息次数": len(rests), "跨跑道调动": 0,
        "完工分钟": makespan, "解析下界分钟": bound, "完工差距分钟": makespan - bound,
        "末架飞行返回上空分钟": max(float(row["飞行返回上空时刻"]) for row in landings),
        "最小批间距": batch_slack, "最小机间距": aircraft_slack,
        "A机最长保障": max(ground_by_type["A"]), "B机最长保障": max(ground_by_type["B"]),
        "最长保障": max(max(values) for values in ground_by_type.values()),
        "最短上空等待": min_return_slack if waves > 1 else None,
        "最长上空等待": max_return_slack if waves > 1 else None,
        "休息后最小余量": min(margins, default=None),
        "各站批次数": {r: len(rows) for r, rows in sorted(by_runway.items())},
        "停机峰值": {f"{r}/{k}": n for (r, k), n in sorted(park_peak.items())},
        "车人峰值": {f"{r}/{k}": n for (r, k), n in sorted(task_peak.items())},
    }


def verify_excel(output):
    from openpyxl import load_workbook

    for table, suffix in (("驰援", "2-1"), ("逐机工序", "2-2")):
        file = output / f"C_Solution{suffix}_按附录9重建.xlsx"
        book = load_workbook(file, read_only=True)
        try:
            require(book.sheetnames == list(CASE_NAMES), f"{file.name} 情景表不全")
            for case in CASE_NAMES:
                with (output / case / f"{table}.csv").open(encoding="utf-8-sig", newline="") as stream:
                    rows = csv.reader(stream)
                    xs = book[case].iter_rows()
                    require([cell.value for cell in next(xs)] == next(rows), f"{file.name} {case} 表头错配")
                    for line, (cells, row) in enumerate(zip_longest(xs, rows), 2):
                        require(cells is not None and row is not None and len(cells) == len(row),
                                f"{file.name} {case} 行或列数错配")
                        for idx, (cell, field) in enumerate(zip(cells, row)):
                            numeric = idx in {0, 1, 3, 6, 7, 11, 12}
                            require(cell.value == (float(field) if numeric else field),
                                    f"{file.name} {case} 第{line}行字段不一致")
                            if idx in (11, 12):
                                require(cell.number_format == "0.0", f"{file.name} 时刻格式不符")
        finally:
            book.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--waves", type=int, default=45, choices=range(1, 46), metavar="1–45")
    parser.add_argument("--excel", action="store_true")
    args = parser.parse_args()
    parking, stock = source_limits()
    summary = {case: verify_case(args.output / case, case, args.waves, parking, stock)
               for case in CASE_NAMES}
    if args.excel:
        verify_excel(args.output)
    result = {
        "status": "PASS", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "reconstructed_excel_checked": args.excel, "scenarios": summary,
    }
    (args.output / "复核结果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    for case, info in summary.items():
        print(f"{case} PASS | 完工={info['完工分钟']:.0f} 下界={info['解析下界分钟']} min | "
              f"架次={info['保障架次']} 工序={info['逐机工序记录']} | "
              f"休息={info['休息次数']} 驰援={info['跨跑道调动']}")


if __name__ == "__main__":
    main()
