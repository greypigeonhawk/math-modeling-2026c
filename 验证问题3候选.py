"""独立复核问题3多波次候选排程。

该脚本只验证候选是否满足当前报告中声明的口径，不判断全局最优性，
也不把候选结果提升为官方模板附件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EPS = 1e-6

OPS = {
    "fuel": ("Z2", "M6", 1),
    "oxygen": ("Z3", "M8", 1),
    "nitrogen": ("Z4", "M8", 1),
    "meal": ("Z8", "M1", 2),
    "tow": ("Z1", "M5", 1),
}


def add_event(events, key, start, end, amount):
    events[key].append((float(start), amount))
    events[key].append((float(end), -amount))


def peak(events):
    value = best = 0
    # At an exact boundary, release old work before starting new work.
    for _, delta in sorted(events, key=lambda x: (x[0], x[1])):
        value += delta
        best = max(best, value)
    return best


def err(errors, message):
    errors.append(message)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", type=Path)
    ap.add_argument("--json-output", type=Path)
    args = ap.parse_args()

    result = json.loads(args.result.read_text(encoding="utf-8"))
    normalized_raw = (ROOT / "results/q23_normalized.json").read_bytes()
    data = json.loads(normalized_raw)
    errors = []

    if result.get("complete_problem3") is not False:
        err(errors, "结果文件未明确标记为非完整问题3解")
    if result.get("template_sha256") != hashlib.sha256(
        (ROOT / "results/q3_batch_prototype.json").read_bytes()
    ).hexdigest():
        err(errors, "单批模板哈希不匹配")

    landings = result.get("landings", [])
    operations = result.get("operations", [])
    jobs = result.get("electrical_jobs", [])
    waves = int(result.get("waves", 0))
    expected_batches = waves * 12
    if len(landings) != expected_batches * 8:
        err(errors, f"着陆记录数错误: {len(landings)} != {expected_batches * 8}")

    batches = defaultdict(list)
    for row in landings:
        key = (row.get("wave"), row.get("batch"))
        batches[key].append(row)
    if len(batches) != expected_batches:
        err(errors, f"批次数错误: {len(batches)} != {expected_batches}")

    ordered_batch_rows = []
    for batch_index in range(expected_batches):
        wave = batch_index // 12 + 1
        batch = batch_index % 12 + 1
        rows = batches.get((wave, batch), [])
        if len(rows) != 8:
            err(errors, f"第{wave}波第{batch}批飞机数为 {len(rows)}")
            continue
        runways = {r.get("runway") for r in rows}
        if len(runways) != 1:
            err(errors, f"第{wave}波第{batch}批跨跑道")
        rows = sorted(rows, key=lambda r: r["landing_min"])
        ordered_batch_rows.append(rows)
        if any(rows[i + 1]["landing_min"] - rows[i]["landing_min"] < 1 - EPS for i in range(7)):
            err(errors, f"第{wave}波第{batch}批批内间隔小于1分钟")
        expected_a = set(range(6 * (batch - 1) + 1, 6 * (batch - 1) + 7))
        expected_b = {73 + 2 * (batch - 1), 74 + 2 * (batch - 1)}
        actual_a = {r["aircraft"] for r in rows if r.get("type") == "A"}
        actual_b = {r["aircraft"] for r in rows if r.get("type") == "B"}
        if actual_a != expected_a or actual_b != expected_b:
            err(errors, f"第{wave}波第{batch}批飞机编号/机型错误")

    for previous, current in zip(ordered_batch_rows, ordered_batch_rows[1:]):
        if current[0]["landing_min"] - previous[-1]["landing_min"] < 10 - EPS:
            err(errors, "相邻批次首末机间隔小于10分钟")

    # One record per physical aircraft and operation.
    op_map = {}
    batch_op = {}
    for row in operations:
        context = (row.get("wave"), row.get("batch"))
        key = (*context, row.get("aircraft"), row.get("operation"))
        if row.get("operation") == "parachute":
            if context in batch_op:
                err(errors, "伞勤批次重复记录")
            batch_op[context] = row
        elif key in op_map:
            err(errors, f"工序重复记录: {key}")
        else:
            op_map[key] = row

    landing_map = {(row["wave"], row["batch"], row["aircraft"]): row for row in landings}
    event_map = defaultdict(list)
    for row in operations:
        name = row.get("operation")
        start, end = float(row["start_min"]), float(row["end_min"])
        if end < start - EPS or start < -EPS:
            err(errors, f"工序时刻非法: {row}")
        if name == "parachute":
            if abs(end - start - 10) > EPS:
                err(errors, "伞勤点工时不是10分钟")
            add_event(event_map, (row.get("runway"), "Z9"), start, end, 1)
            add_event(event_map, (row.get("team"), "M4"), start, end, 2)
            continue
        context = (row.get("wave"), row.get("batch"))
        aircraft = row.get("aircraft")
        aircraft_key = (*context, aircraft)
        if aircraft_key not in landing_map:
            err(errors, f"工序找不到着陆记录: {aircraft_key}")
            continue
        landing = landing_map[aircraft_key]
        if row.get("runway") != landing.get("runway"):
            err(errors, f"飞机{aircraft}工序跑道不一致")
        if start < landing["landing_min"] - EPS or end > landing["landing_min"] + 80 + EPS:
            err(errors, f"飞机{aircraft}/{name}超出着陆后80分钟窗口")
        typ = landing["type"]
        expected_duration = {
            "tow": 10,
            "fuel": 15 if typ == "A" else 30,
            "oxygen": 3,
            "nitrogen": 3,
            "meal": 8 if typ == "A" else 25,
            "power": 15,
            "aircon": 15,
        }.get(name)
        if expected_duration is None:
            err(errors, f"未知工序: {name}")
        elif abs(end - start - expected_duration) > EPS:
            err(errors, f"飞机{aircraft}/{name}工时错误")
        if name in OPS:
            vehicle, group, people = OPS[name]
            add_event(event_map, (row.get("runway"), vehicle), start, end, 1)
            add_event(event_map, (row.get("team"), group), start, end, people)

    for aircraft_key, landing in landing_map.items():
        wave, batch, aircraft = aircraft_key
        required = {"fuel", "oxygen", "nitrogen", "meal", "power", "aircon"}
        # The candidate templates tow only the first A aircraft in each batch.
        if landing["type"] == "A" and landing["aircraft"] % 6 == 1:
            required.add("tow")
        present = {name for (w, b, aid, name) in op_map if (w, b, aid) == aircraft_key}
        if present != required:
            err(errors, f"第{wave}波第{batch}批飞机{aircraft}工序集合错误: {sorted(present)}")
            continue
        edges = [("fuel", "oxygen"), ("fuel", "nitrogen"),
                 ("oxygen", "meal"), ("nitrogen", "meal"),
                 ("meal", "power"), ("meal", "aircon")]
        if "tow" in required:
            edges.append(("tow", "fuel"))
        for pred, succ in edges:
            if op_map[(*aircraft_key, pred)]["end_min"] > op_map[(*aircraft_key, succ)]["start_min"] + EPS:
                err(errors, f"飞机{aircraft}: {pred}->{succ} 前置关系错误")

    # Every electrical operation is represented by exactly one synchronized job.
    covered = defaultdict(list)
    for job in jobs:
        name = job.get("operation")
        if name not in ("power", "aircon"):
            err(errors, f"未知配对工序: {name}")
            continue
        aircraft_ids = job.get("aircraft", [])
        if len(aircraft_ids) not in (1, 2) or len(set(aircraft_ids)) != len(aircraft_ids):
            err(errors, f"{name}配对数量错误")
        if abs(job["end_min"] - job["start_min"] - 15) > EPS:
            err(errors, f"{name}配对工时错误")
        add_event(event_map, (job.get("runway"), "Z5" if name == "power" else "Z6"), job["start_min"], job["end_min"], 1)
        add_event(event_map, (job.get("team"), "M7"), job["start_min"], job["end_min"], 1)
        for aircraft in aircraft_ids:
            context = (job.get("wave"), job.get("batch"))
            covered[(*context, aircraft, name)].append(job)
            op = op_map.get((*context, aircraft, name))
            if op is None or abs(op["start_min"] - job["start_min"]) > EPS or abs(op["end_min"] - job["end_min"]) > EPS:
                err(errors, f"飞机{aircraft}/{name}与配对作业时刻不一致")
    for aircraft_key in landing_map:
        wave, batch, aircraft = aircraft_key
        for name in ("power", "aircon"):
            if len(covered[(*aircraft_key, name)]) != 1:
                err(errors, f"第{wave}波第{batch}批飞机{aircraft}/{name}配对覆盖次数为 {len(covered[(*aircraft_key, name)])}")

    # Resource capacities are checked for each runway/team pair.  A missing team
    # in the serial candidate is inferred from the declared runway.
    default_team = {"F3": "丙", "F4": "丁", "F6": "甲"}
    for row in operations:
        if not row.get("team"):
            row["team"] = default_team.get(row.get("runway"))
    # Rebuild events after inference for all rows (the earlier events remain valid
    # because serial candidates have no team field only).
    event_map = defaultdict(list)
    for row in operations:
        name, start, end = row["operation"], row["start_min"], row["end_min"]
        runway, team = row.get("runway"), row.get("team")
        if name == "parachute":
            add_event(event_map, (runway, "Z9"), start, end, 1)
            add_event(event_map, (team, "M4"), start, end, 2)
        elif name in OPS:
            vehicle, group, people = OPS[name]
            add_event(event_map, (runway, vehicle), start, end, 1)
            add_event(event_map, (team, group), start, end, people)
    for job in jobs:
        name = job["operation"]
        add_event(event_map, (job.get("runway"), "Z5" if name == "power" else "Z6"), job["start_min"], job["end_min"], 1)
        add_event(event_map, (job.get("team"), "M7"), job["start_min"], job["end_min"], 1)

    capacities = {}
    for key, values in event_map.items():
        location, resource = key
        if location in data["runway_team_resources"]:
            bucket = "vehicles" if resource.startswith("Z") else "people"
            capacity = data["runway_team_resources"][location][bucket].get(resource)
            if capacity is not None:
                capacities["/".join(key)] = {"peak": peak(values), "capacity": capacity}
                if peak(values) > capacity:
                    err(errors, f"{location}/{resource}峰值{peak(values)}>{capacity}")

    # Parking occupancy: aircraft remain parked until their recorded takeoff.
    park_events = defaultdict(list)
    for row in landings:
        key = (row["runway"], row["type"])
        park_events[key].extend(((row["landing_min"], 1), (row["takeoff_min"], -1)))
    parking = {}
    runway_to_team = {"F1": "甲", "F2": "乙", "F3": "丙", "F4": "丁", "F5": "戊", "F6": "己", "F7": "庚"}
    for (runway, typ), values in park_events.items():
        p = peak(values)
        cap = data["parking_capacity"].get(runway_to_team.get(runway, runway), {}).get(typ)
        parking[f"{runway}/{typ}"] = {"peak": p, "capacity": cap}
        if cap is not None and p > cap:
            err(errors, f"{runway}/{typ}停机容量峰值{p}>{cap}")

    # Rest windows: every completed block of 18 batches on a runway requires a
    # 180-minute interval before the next batch on that runway. A terminal rest
    # record is optional because no later work can violate it.
    rows_by_runway = defaultdict(list)
    for idx, rows in enumerate(ordered_batch_rows, start=1):
        rows_by_runway[rows[0]["runway"]].append((idx, rows))
    rest_by_runway = defaultdict(list)
    sole_runway = next(iter(rows_by_runway), None) if len(rows_by_runway) == 1 else None
    for r in result.get("rest_windows", []):
        runway = r.get("runway") or sole_runway
        rest_by_runway[runway].append(r)
    for runway, rows in rows_by_runway.items():
        for block in range(1, len(rows) // 18 + 1):
            _, completed = rows[block * 18 - 1]
            end = max(x["takeoff_min"] for x in completed)
            following = rows[block * 18][1][0]["landing_min"] if block * 18 < len(rows) else None
            candidates = [r for r in rest_by_runway[runway] if r.get("after_global_batch") == rows[block * 18 - 1][0] or r.get("after_batch") == block * 18]
            if following is not None and not candidates:
                err(errors, f"{runway}第{block}个18批休息记录缺失")
            if candidates:
                rest = candidates[0]
                if rest["start_min"] + EPS < end or rest["end_min"] - rest["start_min"] < 180 - EPS:
                    err(errors, f"{runway}第{block}个休息窗位置/时长错误")
                if following is not None and following < rest["end_min"] - EPS:
                    err(errors, f"{runway}休息窗后批次过早开始")

    # Support move checks for the F6 candidate.
    for move in result.get("support_moves", []):
        # Candidate files use runway labels (F1/F6); normalized input uses
        # team labels (甲/己) for the same road-distance matrix.
        runway_to_team = {"F1": "甲", "F2": "乙", "F3": "丙", "F4": "丁", "F5": "戊", "F6": "己", "F7": "庚"}
        src = runway_to_team.get(move.get("from"), move.get("from"))
        dst = runway_to_team.get(move.get("to"), move.get("to"))
        if src not in data["road_distance_km"] or dst not in data["road_distance_km"][src]:
            err(errors, f"驰援路线未知: {move}")
            continue
        expected = data["road_distance_km"][src][dst] * 0.75
        if abs(move["arrival_min"] - move["departure_min"] - expected) > EPS:
            err(errors, f"驰援用时错误: {move}")
        if move.get("quantity", 0) <= 0:
            err(errors, f"驰援数量非法: {move}")

    summary = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "scope": "问题3多波次候选；不证明全局最优性",
        "result": str(args.result),
        "waves": waves,
        "batch_count": expected_batches,
        "landing_count": len(landings),
        "operation_count": len(operations),
        "electrical_job_count": len(jobs),
        "makespan_min": result.get("makespan_min"),
        "resource_peaks": capacities,
        "parking_peaks": parking,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
