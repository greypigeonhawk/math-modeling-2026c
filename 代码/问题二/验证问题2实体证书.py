"""不调用求解器，复核第二问联合排班中的实体资源和实际工时。"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from math import ceil, isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOUBLE = {"power_a", "aircon_a", "power_b", "aircon_b"}
CREW = {"Z1": ("M5",), "Z2": ("M6",), "Z3": ("M8",), "Z4": ("M8",),
        "Z5": ("M7",), "Z6": ("M7",), "Z7": ("M2",), "Z8": ("M1",),
        "Z9": ("M3", "M4")}


def verify(raw, certificate, stock):
    if hashlib.sha256(raw).hexdigest() != certificate["schedule_sha256"]:
        raise ValueError("证书所对应的排程哈希不一致")
    schedule = json.loads(raw)
    visits, requests, partners = Counter(), {}, {}
    for row in schedule["operations"]:
        key = (row["aircraft"], row["operation"])
        requests[key] = (
            row["start_min"], row["end_min"], row["vehicle"],
            Counter({(row["origin"], row["group"]): row["people"]}))
        if row["mode"] == "synchronous_pair":
            partners[key] = (row["pair_with"], row["operation"])
    for row in schedule["batch_operations"]:
        staff = Counter({("M", "M4"): 2})
        if row["operation"] == "material":
            staff["M", "M3"] = 1
        requests[row["batch"], row["operation"]] = (
            row["start_min"], row["end_min"], "Z9", staff)

    dispatch = {k: certificate[f"dispatch_{k}"] for k in ("people", "vehicles")}
    for kind, amounts in dispatch.items():
        if amounts.keys() != stock["N"][kind].keys() or any(
            type(n) is not int or not 0 <= n <= stock["N"][kind][g] for g, n in amounts.items()
        ):
            raise ValueError(f"{kind} 派遣数量超过库存或缺字段")
    for vehicle, groups in CREW.items():
        if dispatch["vehicles"][vehicle] and not any(dispatch["people"][g] for g in groups):
            raise ValueError(f"{vehicle} 缺少对应的随队人员")
    fleet = schedule["aircraft_a"] + schedule["aircraft_b"]
    tow = ceil(fleet/10)
    tow_need = ceil(tow / (2 if tow <= 4 else 1.5 if tow <= 8 else 1.2))
    for vehicle, need in {"Z1": tow_need, "Z3": ceil(fleet/10), "Z4": ceil(fleet/10)}.items():
        if stock["M"]["vehicles"][vehicle] + dispatch["vehicles"][vehicle] < need:
            raise ValueError(f"{vehicle} 未达题面数量下限")

    occupation = defaultdict(list)
    actual = {g: [0.0]*n for g, n in dispatch["people"].items() if n}
    for service in certificate["services"]:
        keys = [tuple(row) for row in service["tasks"]]
        actual_vehicle = tuple(service["vehicle"])
        actual_staff = [tuple(person) for person in service["people"]]
        intervals = [requests[key] for key in keys]
        start, end = service["start_min"], service["end_min"]
        if (not 1 <= len(keys) <= 2 or len(set(keys)) != len(keys)
                or not 0 <= start < end <= 120
                or start != min(row[0] for row in intervals)
                or end != max(row[1] for row in intervals)
                or len(set(actual_staff)) != len(actual_staff)):
            raise ValueError(f"{keys} 服务区间或人数异常")
        if len(keys) == 2 and (
            any(k[1] not in DOUBLE for k in keys)
            or max(row[0] for row in intervals) >= min(row[1] for row in intervals)
        ):
            raise ValueError(f"{keys} 未形成有效双机重叠")
        for key, (_, _, vehicle, staff) in zip(keys, intervals):
            if vehicle != actual_vehicle[1] or staff != Counter(p[:2] for p in actual_staff):
                raise ValueError(f"{key} 的车型或人员组不匹配")
            if key in partners and partners[key] not in keys:
                raise ValueError(f"{key} 的同步搭档未在同一服务中")
            visits[key] += 1
        for kind, identifiers in (("vehicles", [actual_vehicle]), ("people", actual_staff)):
            for side, group, number in identifiers:
                limit = {"M": stock["M"][kind], "N": dispatch[kind]}[side][group]
                if type(number) is not int or not 1 <= number <= limit:
                    raise ValueError(f"{kind} 编号超限")
                occupation[kind, side, group, number].append((start, end))
                if kind == "people" and side == "N":
                    actual[group][number-1] += end-start
    if (visits.keys() != requests.keys() or any(count != 1 for count in visits.values())
            or sum(len(s["tasks"]) == 2 for s in certificate["services"]) != certificate["paired_services"]):
        raise ValueError("工序覆盖或双机服务计数错误")
    for key, intervals in occupation.items():
        ordered = sorted(intervals)
        if any(left[1] > right[0] + 1e-8 for left, right in zip(ordered, ordered[1:])):
            raise ValueError(f"{key} 占用冲突")
    reported = certificate["N_workload_minutes"]
    if reported.keys() != actual.keys() or any(
        len(values) != len(reported[g]) or any(
            not isclose(x, y, abs_tol=1e-7) for x, y in zip(values, reported[g])
        ) for g, values in actual.items()
    ):
        raise ValueError("N 方个人时长与证书不一致")
    rates = [sum(values)/len(values)/120 for values in actual.values()]
    return {"status": "PASS", "dispatch_people": sum(dispatch["people"].values()),
            "dispatch_vehicles": sum(dispatch["vehicles"].values()),
            "paired_services": certificate["paired_services"],
            "group_range_percentage_points": 100*(max(rates)-min(rates)) if rates else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    stock = json.loads((ROOT / "results/q23_normalized.json").read_bytes())["airport_resources"]
    result = verify(args.schedule.read_bytes(), json.loads(args.certificate.read_bytes()), stock)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
