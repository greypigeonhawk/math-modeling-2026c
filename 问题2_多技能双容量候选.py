"""问题2改进候选：多技能补位 + 电源/空调一车一人同时服务两架。

这是问题2的可复核候选求解器，不把 FEASIBLE 结果写成全局最优证明。

建模口径：
* Z5/Z6 的容量按题面“1车同时最多2架”建成双槽容量；每项电源/空调任务占
  1个槽，其他车辆任务占2个槽，因此同一辆车最多并行两项电源/空调任务。
* 每个来源和专业组均可选择第一、第二或第三技能，技能熟练度为1、0.8、0.4；
  跨机型0.9与技能熟练度相乘。
* 电源/空调的双槽是聚合容量表示，模型不强行指定车辆编号。输出同时给出峰值
  和重叠任务清单，后续可据此生成逐车配对证书。
* 航材与伞勤按当前项目的保守口径由M方Z9及M3/M4承担；N方Z9只作为联合
  车辆池的可选增援。牵引、附油对象先按附录3的总量比例固定为A机集合，以避免
  B机关键路径被附油拉长；这是可替换的敏感性口径。

求解采用三阶段字典序：先最小化N方车辆总数，再固定车辆数最小化N方人数，
最后固定人车数最小化N方专业组归一化负荷极差。每一阶段的状态、目标界和输入
哈希都写入JSON。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
SCALE = 36  # 1/0.9、1/0.8 和 1/(0.9*0.8) 均可用整数刻度表达
HORIZON = 120 * SCALE

GROUP_TO_SKILL = {
    "M5": "牵引", "M6": "加油", "M2": "附油", "M7": "电源空调",
    "M8": "充气", "M3": "航材", "M4": "伞勤", "M1": "餐食",
}
SKILL_TO_GROUP = {v: k for k, v in GROUP_TO_SKILL.items()}


def parse_skill_options(data: dict) -> dict[str, list[tuple[str, int, float]]]:
    """返回每个需求组可由哪些本组人员以何种技能等级承担。"""
    options: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    name_to_group = SKILL_TO_GROUP
    for row in data["skills"]:
        home = f"M{int(row[0])}"
        options[home].append((home, 1, 1.0))
        for level, text, factor in ((2, row[2], 0.8), (3, row[3], 0.4)):
            for name in text.split("、"):
                if name in name_to_group:
                    options[name_to_group[name]].append((home, level, factor))
    # options currently indexed by required group; duplicate rows are impossible,
    # but sorting keeps model names and output deterministic.
    return {g: sorted(v, key=lambda x: (x[0], x[1])) for g, v in options.items()}


def duration_ticks(base: int, plane: str, side: str, skill_factor: float) -> int:
    cross = 1.0 if ((side == "M") == (plane == "A")) else 0.9
    return round(base * SCALE / (cross * skill_factor))


def load_inputs():
    raw_path = ROOT / "results/q23_normalized.json"
    raw = raw_path.read_bytes()
    data = json.loads(raw)
    return raw_path, raw, data


class Q2Model:
    def __init__(self, a: int, b: int, data: dict, fixed_vehicles: int | None = None,
                 fixed_people: int | None = None):
        if a < 1 or b < 1:
            raise ValueError("问题2至少需要一架A机和一架B机")
        self.a, self.b = a, b
        self.aircraft = ["A"] * a + ["B"] * b
        self.n = len(self.aircraft)
        self.data = data
        self.stock = data["airport_resources"]
        self.model = cp_model.CpModel()
        self.skill_options = parse_skill_options(data)
        self.intervals: dict[tuple[str, str], list[tuple[cp_model.IntervalVar, int]]] = {
            (side, group): [] for side in ("M", "N") for group in self.stock[side]["people"]
        }
        self.vehicles: dict[str, list[tuple[cp_model.IntervalVar, int]]] = {
            v: [] for v in self.stock["M"]["vehicles"]
        }
        self.operations: dict[tuple[int, str], dict] = {}
        self.dispatch_people = {
            g: self.model.NewIntVar(0, self.stock["N"]["people"][g], f"dispatch_{g}")
            for g in self.stock["N"]["people"]
        }
        self.dispatch_vehicles = {
            v: self.model.NewIntVar(0, self.stock["N"]["vehicles"][v], f"dispatch_{v}")
            for v in self.stock["N"]["vehicles"]
        }
        self.work_terms = {g: [] for g in self.stock["N"]["people"]}
        self._build_operations()
        self._build_batches()
        self._add_capacities()
        self._add_quantity_rules()
        self._add_fixed_resource_bounds(fixed_vehicles, fixed_people)
        self._build_fairness_vars()

    def _add_resource_option(self, key, base, required, vehicle, people, pairable,
                             start, end):
        """Create source/home-group/skill alternatives for one aircraft operation."""
        op = self.operations[key]
        plane = self.aircraft[key[0]]
        choices = []
        for side in ("M", "N"):
            for home, level, factor in self.skill_options[required]:
                choice = self.model.NewBoolVar(
                    f"choose_{key[0]}_{key[1]}_{side}_{home}_s{level}"
                )
                dur = duration_ticks(base, plane, side, factor)
                # Power/aircon uses one slot of a two-slot vehicle and personnel pool;
                # all other work uses both slots for the stated staff count.
                demand = 1 if pairable else 2 * people
                interval = self.model.NewOptionalIntervalVar(
                    start, dur, end, choice,
                    f"int_{key[0]}_{key[1]}_{side}_{home}_s{level}",
                )
                self.intervals[(side, home)].append((interval, demand))
                vehicle_demand = 1 if pairable else 2
                self.vehicles[vehicle].append((interval, vehicle_demand))
                if side == "N":
                    self.work_terms[home].append((dur * (1 if pairable else people), choice))
                meta = {
                    "choice": choice, "origin": side, "home_group": home,
                    "skill_level": level, "skill_factor": factor,
                    "duration_ticks": dur, "mode": "double_slot" if pairable else "single",
                    "pair_with": None,
                }
                op["choices"].append(meta)
                choices.append(choice)
        self.model.AddExactlyOne(choices)

    def _build_operations(self):
        n = self.n
        count = math.ceil(n / 10)
        intersection = math.ceil(count / 5)
        # Conservative but reproducible Appendix-3 object selection: all selected
        # tow/oil aircraft are A aircraft; counts are still based on total fleet.
        self.tow_ids = set(range(min(count, self.a)))
        oil_ids = set(range(min(intersection, self.a)))
        oil_ids |= set(range(min(count, self.a), min(count + count - intersection, self.a)))
        self.oil_ids = oil_ids
        specs = [
            ("power_a", 15, "M7", "Z5", 1, True),
            ("aircon_a", 15, "M7", "Z6", 1, True),
            ("fuel", None, "M6", "Z2", 1, False),
            ("oxygen", 3, "M8", "Z3", 1, False),
            ("nitrogen", 3, "M8", "Z4", 1, False),
            ("meal", None, "M1", "Z8", 2, False),
            ("power_b", 15, "M7", "Z5", 1, True),
            ("aircon_b", 15, "M7", "Z6", 1, True),
        ]
        for i, plane in enumerate(self.aircraft):
            for name, base, required, vehicle, people, pairable in specs:
                if name == "meal":
                    base = 8 if plane == "A" else 25
                elif name == "fuel":
                    base = 15 if plane == "A" else 30
                key = (i, name)
                s = self.model.NewIntVar(0, HORIZON, f"s_{i}_{name}")
                e = self.model.NewIntVar(0, HORIZON, f"e_{i}_{name}")
                self.operations[key] = {
                    "start": s, "end": e, "base": base, "required": required,
                    "vehicle": vehicle, "people": people, "pairable": pairable,
                    "choices": [],
                }
                self._add_resource_option(key, base, required, vehicle, people, pairable, s, e)
            if i in self.tow_ids:
                key = (i, "tow")
                s = self.model.NewIntVar(0, HORIZON, f"s_{i}_tow")
                e = self.model.NewIntVar(0, HORIZON, f"e_{i}_tow")
                self.operations[key] = {"start": s, "end": e, "base": 10,
                                        "required": "M5", "vehicle": "Z1", "people": 1,
                                        "pairable": False, "choices": []}
                self._add_resource_option(key, 10, "M5", "Z1", 1, False, s, e)
            if i in oil_ids:
                key = (i, "oil")
                s = self.model.NewIntVar(0, HORIZON, f"s_{i}_oil")
                e = self.model.NewIntVar(0, HORIZON, f"e_{i}_oil")
                self.operations[key] = {"start": s, "end": e, "base": 10,
                                        "required": "M2", "vehicle": "Z7", "people": 1,
                                        "pairable": False, "choices": []}
                self._add_resource_option(key, 10, "M2", "Z7", 1, False, s, e)
            # Figure 1 precedence. The two A-side services, fuel and oil all feed gas;
            # gas then feeds meal; meal feeds the two B-side services.
            if i in self.tow_ids:
                for op in ("power_a", "aircon_a", "fuel"):
                    self.model.Add(self.operations[(i, op)]["start"] >= self.operations[(i, "tow")]["end"])
                if i in oil_ids:
                    self.model.Add(self.operations[(i, "oil")]["start"] >= self.operations[(i, "tow")]["end"])
            for gas in ("oxygen", "nitrogen"):
                for pred in ("fuel", "power_a", "aircon_a"):
                    self.model.Add(self.operations[(i, gas)]["start"] >= self.operations[(i, pred)]["end"])
                if i in oil_ids:
                    self.model.Add(self.operations[(i, gas)]["start"] >= self.operations[(i, "oil")]["end"])
                self.model.Add(self.operations[(i, "meal")]["start"] >= self.operations[(i, gas)]["end"])
            for op in ("power_b", "aircon_b"):
                self.model.Add(self.operations[(i, op)]["start"] >= self.operations[(i, "meal")]["end"])

    def _build_batches(self):
        """保守地把航材/伞勤保留为M方批次，但与联合Z9车辆池共享容量。"""
        self.batches = []
        for batch in range(math.ceil(self.n / 40)):
            members = range(40 * batch, min(40 * (batch + 1), self.n))
            material_ends = []
            for k in range(40 * batch, min(40 * (batch + 1), self.n), 20):
                s = self.model.NewIntVar(0, HORIZON, f"material_s_{k}")
                e = self.model.NewIntVar(0, HORIZON, f"material_e_{k}")
                iv = self.model.NewIntervalVar(s, 10 * SCALE, e, f"material_{k}")
                self.intervals[("M", "M3")].append((iv, 2))
                self.intervals[("M", "M4")].append((iv, 4))
                self.vehicles["Z9"].append((iv, 2))
                for i in range(k, min(k + 20, self.n)):
                    if i in self.tow_ids:
                        self.model.Add(s >= self.operations[(i, "tow")]["end"])
                material_ends.append(e)
                self.batches.append(("material", k, s, e, 10 * SCALE))
            s = self.model.NewIntVar(0, HORIZON, f"chute_s_{batch}")
            duration = (6 * SCALE) + len(list(members)) * SCALE // 2
            e = self.model.NewIntVar(0, HORIZON, f"chute_e_{batch}")
            iv = self.model.NewIntervalVar(s, duration, e, f"chute_{batch}")
            self.intervals[("M", "M4")].append((iv, 4))
            self.vehicles["Z9"].append((iv, 2))
            for material_end in material_ends:
                self.model.Add(s >= material_end)
            for i in members:
                self.model.Add(self.operations[(i, "meal")]["start"] >= e)
            self.batches.append(("parachute", batch, s, e, duration))

    def _add_capacities(self):
        # All resource pools are represented in half-slot units. A non-pairable task
        # consumes both slots of one worker/vehicle; a power/aircon task consumes one.
        for (side, group), items in self.intervals.items():
            if not items:
                continue
            cap = 2 * self.stock[side]["people"][group]
            if side == "N":
                cap = 2 * self.dispatch_people[group]
            self.model.AddCumulative([iv for iv, _ in items], [d for _, d in items], cap)
        for vehicle, items in self.vehicles.items():
            if not items:
                continue
            cap = 2 * (self.stock["M"]["vehicles"][vehicle] + self.dispatch_vehicles[vehicle])
            self.model.AddCumulative([iv for iv, _ in items], [d for _, d in items], cap)

    def _add_quantity_rules(self):
        n = self.n
        count = math.ceil(n / 10)
        for vehicle in ("Z3", "Z4"):
            self.model.Add(self.stock["M"]["vehicles"][vehicle] + self.dispatch_vehicles[vehicle] >= count)
        if count <= 4:
            tow_need = math.ceil(count / 2)
        elif count <= 8:
            tow_need = math.ceil(count / 1.5)
        else:
            tow_need = math.ceil(count / 1.2)
        self.model.Add(self.stock["M"]["vehicles"]["Z1"] + self.dispatch_vehicles["Z1"] >= tow_need)
        # A dispatched N vehicle must enter with at least one N-side module
        # member who can operate that vehicle class. This prevents the degenerate
        # solution “N sends vehicles but no accompanying personnel”; M/N resources
        # may still be jointly scheduled after arrival.
        crew_groups = {
            "Z1": ("M5",), "Z2": ("M6",), "Z3": ("M8",), "Z4": ("M8",),
            "Z5": ("M7",), "Z6": ("M7",), "Z7": ("M2",), "Z8": ("M1",),
            "Z9": ("M3", "M4"),
        }
        for vehicle, groups in crew_groups.items():
            available = sum(self.dispatch_people[g] for g in groups)
            self.model.Add(self.dispatch_vehicles[vehicle] <= self.stock["N"]["vehicles"][vehicle] * available)

    def _add_fixed_resource_bounds(self, fixed_vehicles, fixed_people):
        if fixed_vehicles is not None:
            self.model.Add(sum(self.dispatch_vehicles.values()) == fixed_vehicles)
        if fixed_people is not None:
            self.model.Add(sum(self.dispatch_people.values()) == fixed_people)

    def _build_fairness_vars(self):
        self.workload = {}
        self.utilization = {}
        self.active = {}
        self.hi = self.model.NewIntVar(0, 10000, "max_utilization")
        self.lo = self.model.NewIntVar(0, 10000, "min_utilization")
        active_flags = []
        for group, count in self.dispatch_people.items():
            work = self.model.NewIntVar(0, 10_000_000, f"work_{group}")
            self.model.Add(work == sum(d * c for d, c in self.work_terms[group]))
            self.workload[group] = work
            active = self.model.NewBoolVar(f"active_{group}")
            self.active[group] = active
            active_flags.append(active)
            self.model.Add(count >= 1).OnlyEnforceIf(active)
            self.model.Add(count == 0).OnlyEnforceIf(active.Not())
            self.model.Add(work >= 1).OnlyEnforceIf(active)
            self.model.Add(work == 0).OnlyEnforceIf(active.Not())
            numerator = self.model.NewIntVar(0, 10000 * 10_000_000, f"numerator_{group}")
            divisor = self.model.NewIntVar(1, max(1, self.stock["N"]["people"][group]), f"divisor_{group}")
            self.model.AddMaxEquality(divisor, [count, 1])
            denominator = self.model.NewIntVar(120 * SCALE, 120 * SCALE * self.stock["N"]["people"][group], f"denominator_{group}")
            self.model.Add(numerator == work * 10000)
            denominator_scale = 120 * SCALE
            self.model.Add(denominator == denominator_scale * divisor)
            util = self.model.NewIntVar(0, 10000, f"utilization_{group}")
            self.model.AddDivisionEquality(util, numerator, denominator)
            self.utilization[group] = util
            self.model.Add(self.hi >= util).OnlyEnforceIf(active)
            self.model.Add(self.lo <= util).OnlyEnforceIf(active)
        any_active = self.model.NewBoolVar("any_active")
        self.model.AddMaxEquality(any_active, active_flags)
        self.model.Add(self.hi == 0).OnlyEnforceIf(any_active.Not())
        self.model.Add(self.lo == 0).OnlyEnforceIf(any_active.Not())

    def set_objective(self, kind: str):
        if kind == "vehicles":
            self.model.Minimize(sum(self.dispatch_vehicles.values()))
        elif kind == "people":
            self.model.Minimize(sum(self.dispatch_people.values()))
        elif kind == "fairness":
            self.model.Minimize(self.hi - self.lo)
        else:
            raise ValueError(kind)

    def solve(self, time_limit: float, workers: int):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = 20261121
        status = solver.Solve(self.model)
        return solver, status

    def add_hints(self, solver):
        """把上一阶段可行排程作为下一阶段热启动，减少多技能对称搜索。"""
        self.model.ClearHints()
        for var in self.dispatch_people.values():
            self.model.AddHint(var, solver.Value(var))
        for var in self.dispatch_vehicles.values():
            self.model.AddHint(var, solver.Value(var))
        for op in self.operations.values():
            self.model.AddHint(op["start"], solver.Value(op["start"]))
            self.model.AddHint(op["end"], solver.Value(op["end"]))
            for meta in op["choices"]:
                self.model.AddHint(meta["choice"], solver.Value(meta["choice"]))

    def add_json_hints(self, baseline: dict):
        """把旧的受限候选作为合法热启动，减少多技能对称搜索。"""
        for group, value in baseline.get("dispatch_people", {}).items():
            if group in self.dispatch_people:
                self.model.AddHint(self.dispatch_people[group], int(value))
        for vehicle, value in baseline.get("dispatch_vehicles", {}).items():
            if vehicle in self.dispatch_vehicles:
                self.model.AddHint(self.dispatch_vehicles[vehicle], int(value))
        for row in baseline.get("operations", []):
            key = (int(row["aircraft"]), row["operation"])
            if key not in self.operations:
                continue
            op = self.operations[key]
            self.model.AddHint(op["start"], round(float(row["start_min"]) * SCALE))
            self.model.AddHint(op["end"], round(float(row["end_min"]) * SCALE))
            for meta in op["choices"]:
                selected = (meta["origin"] == row.get("origin") and
                            meta["home_group"] == row.get("group", row.get("required_group")) and
                            meta["skill_level"] == int(row.get("skill_level", 1)))
                self.model.AddHint(meta["choice"], int(selected))

    def extract(self, solver, status, stage_results):
        has_solution = status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
        result = {
            "status": solver.StatusName(status),
            "complete_problem2": False,
            "scope": "improved aggregate two-slot model: Z5/Z6 one vehicle+one person can serve up to 2 concurrent aircraft; first/second/third skills; cross-type 0.9 multiplied by skill factor",
            "aggregation_warning": "vehicle/person IDs are not assigned; double-slot capacity and overlap certificate are required before declaring a final module roster",
            "aircraft_a": self.a, "aircraft_b": self.b,
            "stage_results": stage_results,
            "dispatch_people": {g: solver.Value(v) for g, v in self.dispatch_people.items()} if has_solution else {},
            "dispatch_vehicles": {v: solver.Value(x) for v, x in self.dispatch_vehicles.items()} if has_solution else {},
            "group_workload_person_minutes": {g: solver.Value(x) / SCALE for g, x in self.workload.items()} if has_solution else {},
            "group_utilization_thousandths": {g: solver.Value(x) / 10 for g, x in self.utilization.items()} if has_solution else {},
            "group_utilization_range_thousandths": (solver.Value(self.hi) - solver.Value(self.lo)) / 10 if has_solution else None,
            "operations": [], "batch_operations": [], "pairable_overlaps": [],
        }
        if not has_solution:
            return result
        selected = {}
        for key, op in self.operations.items():
            chosen = [m for m in op["choices"] if solver.Value(m["choice"])]
            if len(chosen) != 1:
                raise RuntimeError(f"{key} selected alternatives={len(chosen)}")
            meta = chosen[0]
            start = solver.Value(op["start"]) / SCALE
            end = solver.Value(op["end"]) / SCALE
            row = {
                "aircraft": key[0], "type": self.aircraft[key[0]], "operation": key[1],
                "start_min": start, "end_min": end, "duration_min": end - start,
                "vehicle": op["vehicle"], "group": meta["home_group"],
                "required_group": op["required"], "people": op["people"],
                "origin": meta["origin"], "skill_level": meta["skill_level"],
                "skill_factor": meta["skill_factor"], "mode": meta["mode"],
                "pair_with": meta["pair_with"],
            }
            selected[key] = row
            result["operations"].append(row)
        # Mark overlaps in the aggregate model. These are the places where a single
        # Z5/Z6 plus one operator is intended to serve two aircraft concurrently.
        for op_name in ("power_a", "aircon_a", "power_b", "aircon_b"):
            rows = [r for r in result["operations"] if r["operation"] == op_name]
            for i, left in enumerate(rows):
                for right in rows[i + 1:]:
                    overlap = min(left["end_min"], right["end_min"]) - max(left["start_min"], right["start_min"])
                    if overlap > 1e-9:
                        result["pairable_overlaps"].append({
                            "operation": op_name, "aircraft": [left["aircraft"], right["aircraft"]],
                            "start_min": max(left["start_min"], right["start_min"]),
                            "end_min": min(left["end_min"], right["end_min"]),
                            "overlap_min": overlap,
                        })
        for kind, batch, s, e, dur in self.batches:
            result["batch_operations"].append({
                "operation": kind, "batch": batch,
                "start_min": solver.Value(s) / SCALE, "end_min": solver.Value(e) / SCALE,
                "duration_min": dur / SCALE, "origin": "M",
            })
        return result


def run_case(a: int, b: int, data: dict, time_limit: float, workers: int,
             baseline: dict | None = None, order: str = "vehicles",
             refinement_time_limit: float | None = None):
    stage_results = []
    model = Q2Model(a, b, data)
    if baseline:
        model.add_json_hints(baseline)
    first, second = ("vehicles", "people") if order == "vehicles" else ("people", "vehicles")
    model.set_objective(first)
    solver, status = model.solve(time_limit, workers)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return model.extract(solver, status, stage_results)
    previous_solver, previous_status = solver, status
    first_value = (sum(solver.Value(v) for v in model.dispatch_vehicles.values())
                   if first == "vehicles" else sum(solver.Value(v) for v in model.dispatch_people.values()))
    stage_results.append({"stage": first, "status": solver.StatusName(status),
                          "objective": first_value, "best_bound": solver.BestObjectiveBound()})
    model.add_hints(solver)
    if first == "vehicles":
        model.model.Add(sum(model.dispatch_vehicles.values()) == first_value)
    else:
        model.model.Add(sum(model.dispatch_people.values()) == first_value)
    model.set_objective(second)
    solver, status = model.solve(time_limit, workers)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        # Preserve the stage-1 feasible solution; an UNKNOWN second stage does not
        # invalidate it and should never be serialized as arbitrary solver memory.
        return model.extract(previous_solver, previous_status, stage_results)
    previous_solver, previous_status = solver, status
    second_value = (sum(solver.Value(v) for v in model.dispatch_vehicles.values())
                    if second == "vehicles" else sum(solver.Value(v) for v in model.dispatch_people.values()))
    stage_results.append({"stage": second, "status": solver.StatusName(status),
                          "objective": second_value, "best_bound": solver.BestObjectiveBound()})
    model.add_hints(solver)
    if second == "vehicles":
        model.model.Add(sum(model.dispatch_vehicles.values()) == second_value)
    else:
        model.model.Add(sum(model.dispatch_people.values()) == second_value)
    model.set_objective("fairness")
    solver, status = model.solve(time_limit, workers)
    stage_results.append({"stage": "fairness", "status": solver.StatusName(status),
                          "objective": solver.ObjectiveValue(), "best_bound": solver.BestObjectiveBound()})
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return model.extract(previous_solver, previous_status, stage_results)
    model.add_hints(solver)
    refinement_limit = time_limit if refinement_time_limit is None else refinement_time_limit
    refined_solver, refined_status = model.solve(refinement_limit, workers)
    stage_results.append({"stage": "fairness_refinement", "status": refined_solver.StatusName(refined_status),
                          "objective": refined_solver.ObjectiveValue(), "best_bound": refined_solver.BestObjectiveBound(),
                          "time_limit_s": refinement_limit})
    if refined_status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return model.extract(refined_solver, refined_status, stage_results)
    return model.extract(solver, status, stage_results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=int, default=32)
    ap.add_argument("--b", type=int, required=True)
    ap.add_argument("--time-limit", type=float, default=30.0,
                    help="每个字典序阶段的CP-SAT时限（秒）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--baseline", type=Path, help="受限候选JSON，用于CP-SAT热启动")
    ap.add_argument("--order", choices=("vehicles", "people"), default="vehicles",
                    help="第一阶段先最小化车辆或人员")
    ap.add_argument("--refinement-time-limit", type=float,
                    help="第四阶段负荷极差细化时限；默认等于前三阶段时限")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    raw_path, raw, data = load_inputs()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    result = run_case(args.a, args.b, data, args.time_limit, args.workers,
                      baseline=baseline, order=args.order,
                      refinement_time_limit=args.refinement_time_limit)
    result["source_sha256"] = data["source_sha256"]
    result["normalized_input_sha256"] = hashlib.sha256(raw).hexdigest()
    result["input_path"] = str(raw_path.relative_to(ROOT))
    result["solver_parameters"] = {"time_limit_per_stage_s": args.time_limit,
                                    "refinement_time_limit_s": args.refinement_time_limit or args.time_limit,
                                    "workers": args.workers, "random_seed": 20261121,
                                    "scale": SCALE}
    result["selected_final_stage"] = "fairness_refinement"
    result["stage_note"] = "前两阶段按人数优先，再固定人车数；最终采用内置fairness_refinement返回的排程。"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("operations", "batch_operations", "pairable_overlaps")},
                     ensure_ascii=False, indent=2))
    if result["status"] not in ("FEASIBLE", "OPTIMAL"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
