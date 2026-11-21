"""独立核验问题2多技能双容量候选。

核验的是代码声明的聚合口径：工序时长、流程前置、M/N库存、半槽容量、
Z1/Z3/Z4数量和航材/伞勤批次。它不把聚合双槽自动升级为逐车逐人编号证书。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCALE = 36
GROUP_TO_SKILL = {"M5": "牵引", "M6": "加油", "M2": "附油", "M7": "电源空调",
                  "M8": "充气", "M3": "航材", "M4": "伞勤", "M1": "餐食"}
SKILL_TO_GROUP = {v: k for k, v in GROUP_TO_SKILL.items()}


def skill_factor(data, home, required, level):
    if level == 1 and home == required:
        return 1.0
    rows = {f"M{int(r[0])}": r for r in data["skills"]}
    name = GROUP_TO_SKILL[required]
    if level == 2 and name in rows[home][2].split("、"):
        return 0.8
    if level == 3 and name in rows[home][3].split("、"):
        return 0.4
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", type=Path)
    args = ap.parse_args()
    raw = (ROOT / "results/q23_normalized.json").read_bytes()
    data = json.loads(raw)
    res = json.loads(args.result.read_text(encoding="utf-8"))
    errors = []
    if res.get("status") not in ("FEASIBLE", "OPTIMAL"):
        errors.append(f"结果状态不可核验: {res.get('status')}")
    if res.get("normalized_input_sha256") != hashlib.sha256(raw).hexdigest():
        errors.append("规范化输入哈希不匹配")
    source_hash = hashlib.sha256((ROOT / "data/新2026C.docx").read_bytes()).hexdigest()
    if res.get("source_sha256") != source_hash or data.get("source_sha256") != source_hash:
        errors.append("原题DOCX哈希链不匹配")
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    a, b = int(res["aircraft_a"]), int(res["aircraft_b"])
    aircraft = ["A"] * a + ["B"] * b
    n = len(aircraft)
    tow_ids = set(range(min(math.ceil(n / 10), a)))
    count = math.ceil(n / 10)
    inter = math.ceil(count / 5)
    oil_ids = set(range(min(inter, a))) | set(range(min(count, a), min(count + count - inter, a)))
    specs = {
        "power_a": (15, "M7", "Z5", 1), "aircon_a": (15, "M7", "Z6", 1),
        "power_b": (15, "M7", "Z5", 1), "aircon_b": (15, "M7", "Z6", 1),
        "oxygen": (3, "M8", "Z3", 1), "nitrogen": (3, "M8", "Z4", 1),
        "tow": (10, "M5", "Z1", 1), "oil": (10, "M2", "Z7", 1),
    }
    ops = {}
    events = defaultdict(list)
    def use(key, start, end, demand):
        events[key].append((start, demand)); events[key].append((end, -demand))
    for row in res.get("operations", []):
        i, name = int(row["aircraft"]), row["operation"]
        key = (i, name)
        if i < 0 or i >= n or key in ops:
            errors.append(f"飞机/工序重复或越界: {key}")
            continue
        plane = aircraft[i]
        if name == "fuel": base, required, vehicle, people = (15 if plane == "A" else 30), "M6", "Z2", 1
        elif name == "meal": base, required, vehicle, people = (8 if plane == "A" else 25), "M1", "Z8", 2
        elif name in specs: base, required, vehicle, people = specs[name]
        else:
            errors.append(f"未知工序: {key}"); continue
        start, end = float(row["start_min"]), float(row["end_min"])
        side, home, level = row.get("origin"), row.get("group"), int(row.get("skill_level", 1))
        factor = skill_factor(data, home, required, level)
        cross = 1.0 if ((side == "M") == (plane == "A")) else 0.9
        expected = base / (cross * factor) if factor is not None and side in ("M", "N") else None
        if expected is None or abs((end - start) - expected) > 1.0 / SCALE + 1e-6:
            errors.append(f"{key}: 技能/跨机型折减或时长错误")
        if start < -1e-6 or end > 120 + 1e-6 or end < start:
            errors.append(f"{key}: 时限错误")
        pairable = name in ("power_a", "aircon_a", "power_b", "aircon_b")
        if row.get("mode") != ("double_slot" if pairable else "single"):
            errors.append(f"{key}: 双槽标识错误")
        if row.get("vehicle") != vehicle or row.get("required_group") != required:
            errors.append(f"{key}: 功能包属性错误")
        if int(row.get("people", people)) != people:
            errors.append(f"{key}: 人数配置错误")
        if side not in ("M", "N") or home not in data["airport_resources"].get(side, {}).get("people", {}):
            errors.append(f"{key}: 来源或人员组错误")
        person_demand = 1 if pairable else 2 * people
        vehicle_demand = 1 if pairable else 2
        use(("people", side, home), start, end, person_demand)
        use(("vehicle", vehicle), start, end, vehicle_demand)
        ops[key] = row

    for i in range(n):
        required = {"power_a", "aircon_a", "fuel", "oxygen", "nitrogen", "meal", "power_b", "aircon_b"}
        if i in tow_ids: required.add("tow")
        if i in oil_ids: required.add("oil")
        present = {name for (j, name) in ops if j == i}
        if present != required:
            errors.append(f"飞机{i}工序集合错误: {sorted(present)} != {sorted(required)}")
            continue
        edges = [(p, gas) for gas in ("oxygen", "nitrogen") for p in ("power_a", "aircon_a", "fuel")]
        edges += [(gas, "meal") for gas in ("oxygen", "nitrogen")]
        edges += [("meal", p) for p in ("power_b", "aircon_b")]
        if i in tow_ids:
            edges += [("tow", p) for p in ("power_a", "aircon_a", "fuel")]
            if i in oil_ids: edges.append(("tow", "oil"))
        if i in oil_ids: edges += [("oil", gas) for gas in ("oxygen", "nitrogen")]
        for pred, succ in edges:
            if ops[(i, pred)]["end_min"] > ops[(i, succ)]["start_min"] + 1e-6:
                errors.append(f"飞机{i}: {pred}->{succ}前置错误")

    batches = {(r["operation"], int(r["batch"])): r for r in res.get("batch_operations", [])}
    expected = {("material", k) for k in range(0, n, 20)} | {("parachute", k) for k in range(math.ceil(n / 40))}
    if set(batches) != expected:
        errors.append("航材/伞勤批次集合错误")
    for (kind, idx), row in batches.items():
        start, end = float(row["start_min"]), float(row["end_min"])
        size = min(40, n - idx * 40) if kind == "parachute" else min(20, n - idx)
        duration = 6 + size / 2 if kind == "parachute" else 10
        if abs(end - start - duration) > 1.0 / SCALE + 1e-6 or start < -1e-6 or end > 120 + 1e-6 or row.get("origin") != "M":
            errors.append(f"{kind}/{idx}: 批次时长、时限或来源错误")
        use(("vehicle", "Z9"), start, end, 2)
        if kind == "material":
            use(("people", "M", "M3"), start, end, 2)
            use(("people", "M", "M4"), start, end, 4)
            for i in range(idx, min(idx + 20, n)):
                if i in tow_ids and start + 1e-6 < ops[(i, "tow")]["end_min"]:
                    errors.append(f"material/{idx}: 牵引未完")
        else:
            use(("people", "M", "M4"), start, end, 4)
            for k in range(idx * 40, min((idx + 1) * 40, n), 20):
                if start + 1e-6 < batches[("material", k)]["end_min"]:
                    errors.append(f"parachute/{idx}: 航材未完")
            for i in range(idx * 40, min((idx + 1) * 40, n)):
                if ops[(i, "meal")]["start_min"] + 1e-6 < end:
                    errors.append(f"飞机{i}: 伞勤未完即餐食")

    peaks = {}
    for key, ev in events.items():
        level = peak = 0
        for t, delta in sorted(ev, key=lambda x: (x[0], x[1])):
            level += delta; peak = max(peak, level)
        peaks["/".join(map(str, key))] = peak
        if key[0] == "vehicle":
            cap = 2 * (data["airport_resources"]["M"]["vehicles"][key[1]] + res["dispatch_vehicles"].get(key[1], 0))
        else:
            cap = 2 * (data["airport_resources"][key[1]]["people"][key[2]] if key[1] == "M" else res["dispatch_people"].get(key[2], 0))
        if peak > cap + 1e-6:
            errors.append(f"{key}: 聚合容量{peak}>{cap}")
    for vehicle, value in res["dispatch_vehicles"].items():
        if not 0 <= value <= data["airport_resources"]["N"]["vehicles"][vehicle]:
            errors.append(f"N方车辆库存超限: {vehicle}")
    for group, value in res["dispatch_people"].items():
        if not 0 <= value <= data["airport_resources"]["N"]["people"][group]:
            errors.append(f"N方人员库存超限: {group}")
    crew = {"Z1": ("M5",), "Z2": ("M6",), "Z3": ("M8",), "Z4": ("M8",),
            "Z5": ("M7",), "Z6": ("M7",), "Z7": ("M2",), "Z8": ("M1",), "Z9": ("M3", "M4")}
    for v, groups in crew.items():
        max_per_person = data["airport_resources"]["N"]["vehicles"][v]
        if res["dispatch_vehicles"].get(v, 0) > max_per_person * sum(res["dispatch_people"].get(g, 0) for g in groups):
            errors.append(f"{v}: N车没有对应N方模块人员")
    total = math.ceil(n / 10)
    for v in ("Z3", "Z4"):
        if data["airport_resources"]["M"]["vehicles"][v] + res["dispatch_vehicles"].get(v, 0) < total:
            errors.append(f"{v}: 数量规则未满足")
    if total <= 4: tow_need = math.ceil(total / 2)
    elif total <= 8: tow_need = math.ceil(total / 1.5)
    else: tow_need = math.ceil(total / 1.2)
    if data["airport_resources"]["M"]["vehicles"]["Z1"] + res["dispatch_vehicles"].get("Z1", 0) < tow_need:
        errors.append("Z1: 数量规则未满足")
    out = {"status": "PASS" if not errors else "FAIL", "errors": errors,
           "peaks": peaks, "scope": "多技能双槽聚合候选；不证明完整问题2全局最优，不替代逐车逐人编号证书"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
