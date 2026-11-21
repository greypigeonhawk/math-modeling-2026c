"""把问题2聚合双槽排程着色为可复核的车辆/人员编号证书。

模型求解阶段只约束聚合容量；本脚本对每个车辆池、人员组池做区间着色，检查
每辆车和每名人员的半槽占用不超过2。它不改变模型结果，只输出后处理证书。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def color_jobs(jobs, capacity, demand_key):
    """区间资源容量为2，返回每个job的资源编号列表；失败返回None。"""
    resources = [[] for _ in range(capacity)]
    assignment = {}
    for job in sorted(jobs, key=lambda x: (x["start_min"], x["end_min"], str(x["job"]))):
        demand = job[demand_key]
        used = [sum(d for end, d, _ in resources[i] if end > job["start_min"] + 1e-8)
                for i in range(capacity)]
        if demand == 4:
            chosen = [i for i, u in enumerate(used) if u + 2 <= 2][:2]
            if len(chosen) != 2:
                return None
        else:
            chosen = next((i for i, u in enumerate(used) if u + demand <= 2), None)
            if chosen is None:
                return None
            chosen = [chosen]
        assignment[tuple(job["job"])] = chosen
        for i in chosen:
            resources[i].append((job["end_min"], 2 if demand == 4 else demand, job["job"]))
    return assignment


def color_joint_double_slots(jobs, data, result):
    """联合着色双槽任务：重叠任务保持同一车辆和同一操作员。"""
    vehicle_ids = {}
    for vehicle, m_count in data["airport_resources"]["M"]["vehicles"].items():
        n_count = result["dispatch_vehicles"].get(vehicle, 0)
        vehicle_ids[vehicle] = [("M", vehicle, i + 1) for i in range(m_count)] + [
            ("N", vehicle, i + 1) for i in range(n_count)]
    person_ids = {}
    for side in ("M", "N"):
        for group, m_count in data["airport_resources"][side]["people"].items():
            count = m_count if side == "M" else result["dispatch_people"].get(group, 0)
            person_ids[(side, group)] = [(side, group, i + 1) for i in range(count)]
    v_active = {key: [] for values in vehicle_ids.values() for key in values}
    p_active = {key: [] for values in person_ids.values() for key in values}
    assignment = {}
    for job in sorted((j for j in jobs if j.get("double_slot")),
                      key=lambda x: (x["start_min"], x["end_min"], str(x["job"]))):
        chosen = None
        for vehicle in vehicle_ids[job["vehicle"]]:
            vnow = [x for x in v_active[vehicle] if x[0] > job["start_min"] + 1e-8]
            if len(vnow) >= 2:
                continue
            for person in person_ids[tuple(job["person_pool"])]:
                pnow = [x for x in p_active[person] if x[0] > job["start_min"] + 1e-8]
                if len(pnow) >= 2:
                    continue
                if vnow and any(x[1] != person for x in vnow):
                    continue
                if pnow and any(x[1] != vehicle for x in pnow):
                    continue
                chosen = (vehicle, person)
                break
            if chosen:
                break
        if chosen is None:
            return None
        vehicle, person = chosen
        assignment[str(job["job"])] = {
            "vehicle": vehicle, "person": person,
            "start_min": job["start_min"], "end_min": job["end_min"]}
        v_active[vehicle].append((job["end_min"], person, job["job"]))
        p_active[person].append((job["end_min"], vehicle, job["job"]))
    return assignment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    data = json.loads((ROOT / "results/q23_normalized.json").read_text(encoding="utf-8"))
    jobs = []
    for row in result["operations"]:
        pairable = row["operation"] in ("power_a", "aircon_a", "power_b", "aircon_b")
        jobs.append({"job": ["operation", row["aircraft"], row["operation"]],
                     "start_min": row["start_min"], "end_min": row["end_min"],
                     "vehicle": row["vehicle"], "person_pool": [row["origin"], row["group"]],
                     "vehicle_demand": 1 if pairable else 2,
                     "person_demand": 1 if pairable else 2 * row["people"],
                     "double_slot": pairable})
    for row in result["batch_operations"]:
        if row["operation"] == "material":
            jobs.append({"job": ["material_vehicle", row["batch"]], "start_min": row["start_min"],
                         "end_min": row["end_min"], "vehicle": "Z9", "person_pool": ["M", "M3"],
                         "vehicle_demand": 2, "person_demand": 2, "double_slot": False})
            jobs.append({"job": ["material_staff", row["batch"]], "start_min": row["start_min"],
                         "end_min": row["end_min"], "vehicle": None, "person_pool": ["M", "M4"],
                         "vehicle_demand": 0, "person_demand": 4, "double_slot": False})
        else:
            jobs.append({"job": ["parachute", row["batch"]], "start_min": row["start_min"],
                         "end_min": row["end_min"], "vehicle": "Z9", "person_pool": ["M", "M4"],
                         "vehicle_demand": 2, "person_demand": 4, "double_slot": False})

    vehicle_assignments, person_assignments = {}, {}
    errors = []
    for vehicle in data["airport_resources"]["M"]["vehicles"]:
        group = [j for j in jobs if j["vehicle"] == vehicle]
        cap = data["airport_resources"]["M"]["vehicles"][vehicle] + result["dispatch_vehicles"].get(vehicle, 0)
        colored = color_jobs(group, cap, "vehicle_demand")
        if colored is None:
            errors.append(f"车辆池{vehicle}无法着色")
        else:
            for job, ids in colored.items():
                vehicle_assignments[str(job)] = [
                    ("M" if i < data["airport_resources"]["M"]["vehicles"][vehicle] else "N",
                     vehicle, i + 1 if i < data["airport_resources"]["M"]["vehicles"][vehicle]
                     else i + 1 - data["airport_resources"]["M"]["vehicles"][vehicle]) for i in ids]
    for side in ("M", "N"):
        for group in data["airport_resources"][side]["people"]:
            pool = [j for j in jobs if j["person_pool"] == [side, group]]
            cap = data["airport_resources"][side]["people"][group] if side == "M" else result["dispatch_people"].get(group, 0)
            colored = color_jobs(pool, cap, "person_demand")
            if colored is None:
                errors.append(f"人员池{side}/{group}无法着色")
            else:
                for job, ids in colored.items():
                    person_assignments[str(job)] = [(side, group, i + 1) for i in ids]
    out = {"status": "PASS" if not errors else "FAIL", "source_result": str(args.result),
           "scope": "聚合双槽排程的区间着色证书；车辆池和人员池独立着色，未证明重叠任务同车同人",
           "errors": errors, "vehicle_assignments": vehicle_assignments,
           "person_assignments": person_assignments,
           "joint_double_slot_assignments": {},
           "joint_double_slot_status": "NOT_PROVEN"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "errors": errors, "vehicle_jobs": len(vehicle_assignments),
                      "person_jobs": len(person_assignments)}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
