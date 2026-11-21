"""首次保障资源受限调度模型。时间单位为0.5分钟。"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
RESOURCE_FILE = ROOT / "results" / "q1_source_tables.json"
SCALE = 4  # 0.25 min; exactly represents 0.8/0.4 proficiency-adjusted durations.
CANDIDATE_AIRCRAFT = 160

# 题目附录5的M地勤人力与车辆库存。
PEOPLE = {"M1": 45, "M2": 20, "M3": 4, "M4": 8, "M5": 15, "M6": 30, "M7": 20, "M8": 8}
VEHICLES = {"Z1": 8, "Z2": 12, "Z3": 4, "Z4": 7, "Z5": 15, "Z6": 15, "Z7": 1, "Z8": 10, "Z9": 1}
VEHICLE_UNITS = {"Z1": 1, "Z2": 1, "Z3": 1, "Z4": 1, "Z5": 1, "Z6": 1, "Z7": 1, "Z8": 1, "Z9": 1}
SKILL_GROUP = {"牵引": "M5", "加油": "M6", "附油": "M2", "电源空调": "M7",
               "充气": "M8", "航材": "M3", "伞勤": "M4", "餐食": "M1"}


def ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


class FirstServiceModel:
    def __init__(self, limit_minutes: int, reorder: bool = False, added_people: dict[str, int] | None = None,
                 added_vehicles: dict[str, int] | None = None, fixed_count: int | None = None,
                 test_count: int | None = None, max_added_vehicles: int | None = None,
                 optimize_skills: bool | None = None, validate_warm_start: bool = False):
        self.model = cp_model.CpModel()
        self.limit = limit_minutes * SCALE
        self.reorder = reorder
        self.added_people = added_people or {}
        self.added_vehicles = added_vehicles or {}
        self.fixed_count = fixed_count
        self.test_count = test_count
        self.max_added_vehicles = max_added_vehicles
        self.optimize_skills = fixed_count is not None if optimize_skills is None else optimize_skills
        self.validate_warm_start = validate_warm_start
        self.completions = []
        self.task = {}
        self.people_intervals = {group: [] for group in PEOPLE}
        self.people_demands = {group: [] for group in PEOPLE}
        self.vehicle_intervals = {kind: [] for kind in VEHICLES}
        self.vehicle_demands = {kind: [] for kind in VEHICLES}
        self.extra_people = {}
        self.extra_vehicles = {}
        self.skill_candidates = {}
        self.skill_choice_vars = {}
        self._task_skill = {}
        self._task_skill_links = {}
        self._task_skill_links = {}
        self.skill_upgrades = {}

    def add_task(self, key: tuple, presence, duration_minutes: float, people: dict[str, int] | str, vehicle: str,
                 vehicle_demand: int = 1, staff_demand: int = 1):
        start = self.model.NewIntVar(0, self.limit, f"s_{key}")
        end = self.model.NewIntVar(0, self.limit, f"e_{key}")
        intervals = []
        if isinstance(people, str):
            self._task_skill[key] = people
            candidates = self.skill_candidates[people]
            choices = []
            for group, level, condition, condition_value in candidates:
                choose = self.model.NewBoolVar(f"skill_{key}_{group}_{level}")
                choices.append(choose)
                if condition is not None:
                    if condition_value:
                        self.model.Add(choose <= condition)
                    else:
                        self.model.Add(choose + condition <= 1)
                self.skill_choice_vars.setdefault(key, {})[(group, level)] = choose
                proficiency = 1.0 if people == "伞勤" else (1.0 if level == 1 else (0.8 if level == 2 else 0.4))
                size = int(round(duration_minutes / proficiency * SCALE))
                option_end = self.model.NewIntVar(0, self.limit, f"end_{key}_{group}_{level}")
                interval = self.model.NewOptionalIntervalVar(start, size, option_end, choose,
                                                              f"i_{key}_{group}_{level}")
                self.model.Add(end == option_end).OnlyEnforceIf(choose)
                intervals.append(interval)
                demand = 2 * staff_demand
                self.people_intervals[group].append(interval)
                self.people_demands[group].append(demand)
                self.vehicle_intervals[vehicle].append(interval)
                self.vehicle_demands[vehicle].append(vehicle_demand)
            self.model.Add(sum(choices) == presence)
        else:
            size = int(round(duration_minutes * SCALE))
            interval = self.model.NewOptionalIntervalVar(start, size, end, presence, f"i_{key}")
            intervals.append(interval)
            for group, demand in people.items():
                self.people_intervals[group].append(interval)
                self.people_demands[group].append(2 * demand)
            self.vehicle_intervals[vehicle].append(interval)
            self.vehicle_demands[vehicle].append(vehicle_demand)
        self.task[key] = (start, end, intervals, presence)
        return start, end, intervals

    def add_variable_skill_task(self, key, presence, start, end, duration, skill, vehicle,
                                vehicle_demand=1, staff_demand=1):
        """Attach a variable-duration operation to one qualified staff group."""
        choices = []
        intervals = []
        self._task_skill[key] = skill
        for group, level, condition, condition_value in self.skill_candidates[skill]:
            choose = self.model.NewBoolVar(f"skill_{key}_{group}_{level}")
            choices.append(choose)
            if condition is not None:
                if condition_value:
                    self.model.Add(choose <= condition)
                else:
                    self.model.Add(choose + condition <= 1)
            self.skill_choice_vars.setdefault(key, {})[(group, level)] = choose
            # Parachute proficiency is fixed at 1.0 by Appendix 4.
            interval_end = self.model.NewIntVar(0, self.limit, f"end_{key}_{group}_{level}")
            interval = self.model.NewOptionalIntervalVar(start, duration, interval_end, choose,
                                                          f"i_{key}_{group}_{level}")
            self.model.Add(end == interval_end).OnlyEnforceIf(choose)
            intervals.append(interval)
            self.people_intervals[group].append(interval)
            self.people_demands[group].append(2 * staff_demand)
            self.vehicle_intervals[vehicle].append(interval)
            self.vehicle_demands[vehicle].append(vehicle_demand)
        self.model.Add(sum(choices) == presence)
        self.task[key] = (start, end, intervals, presence)
        return intervals

    def add_electrical_option(self, key, presence, duration_minutes, vehicle):
        """One interval represents either one aircraft alone or a two-aircraft vehicle pair."""
        start, end, intervals = self.add_task(key, presence, duration_minutes, "电源空调", vehicle,
                                               vehicle_demand=1, staff_demand=1)
        return start, end, intervals

    @staticmethod
    def seed_resources_from_schedule(rows, fixed_count):
        """Construct a safe singleton-vehicle warm start from a prior task schedule."""
        vehicle_of = {"tow": "Z1", "power_a": "Z5", "aircon_a": "Z6", "oil": "Z7",
                      "fuel": "Z2", "oxygen": "Z3", "nitrogen": "Z4", "meal": "Z8",
                      "power_b": "Z5", "aircon_b": "Z6"}
        vehicle_events = {kind: [] for kind in VEHICLES}
        people_events = {group: [] for group in PEOPLE}
        tow_count = 0
        for row in rows:
            key, op = row["aircraft"], row["operation"]
            start, end = float(row["start_min"]), float(row["end_min"])
            if key.isdigit():
                vehicle = vehicle_of[op]
                if op == "tow":
                    tow_count += 1
                group = row.get("operator_group", "")
                demand = 2 if op == "meal" else 1
                if group in people_events:
                    people_events[group].extend(((start, demand), (end, -demand)))
            else:
                vehicle = "Z9"
                if key == "material":
                    people_events["M3"].extend(((start, 1), (end, -1)))
                    people_events["M4"].extend(((start, 2), (end, -2)))
                else:
                    group = row.get("operator_group") or "M4"
                    people_events[group].extend(((start, 2), (end, -2)))
            vehicle_events[vehicle].extend(((start, 1), (end, -1)))

        def peak(events):
            load = high = 0
            for _, delta in sorted(events, key=lambda event: (event[0], event[1])):
                load += delta
                high = max(high, load)
            return high

        required_vehicles = {kind: peak(events) for kind, events in vehicle_events.items()}
        required_vehicles["Z3"] = max(required_vehicles["Z3"], ceil_div(fixed_count, 10))
        required_vehicles["Z4"] = max(required_vehicles["Z4"], ceil_div(fixed_count, 10))
        if tow_count <= 4:
            z1_required = ceil_div(tow_count, 2)
        elif tow_count <= 8:
            z1_required = ceil_div(tow_count * 2, 3)
        else:
            z1_required = ceil_div(tow_count * 5, 6)
        required_vehicles["Z1"] = max(required_vehicles["Z1"], z1_required)
        vehicle_additions = {kind: max(0, required_vehicles[kind] - VEHICLES[kind]) for kind in VEHICLES}
        people_additions = {group: max(0, peak(events) - PEOPLE[group]) for group, events in people_events.items()}
        return people_additions, vehicle_additions

    def build(self):
        source = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
        resource_rows = source["m_ground_resources"][2:]
        source_people = {row[3]: int(row[4]) for row in resource_rows if row[3]}
        source_vehicles = {row[0]: int(row[1]) for row in resource_rows if row[0].startswith("Z")}
        if source_people != PEOPLE or source_vehicles != VEHICLES:
            raise ValueError("硬编码资源参数与DOCX提取表不一致")
        skill_rows = source["multi_skill_table"][1:]
        task_rows = source["first_service_tasks"][1:]
        if len(skill_rows) != 8 or len(task_rows) != 10:
            raise ValueError("技能或首次保障工序数据行数异常")
        source_times = [tuple(float(v) for v in re.findall(r"(\d+(?:\.\d+)?)分钟", " ".join(row)))
                        for row in task_rows]
        expected_times = [(10.0,), (15.0, 30.0), (3.0,), (3.0,), (15.0,), (15.0,),
                          (10.0,), (8.0, 25.0), (10.0,), (6.0, 0.5)]
        if source_times != expected_times:
            raise ValueError(f"首次保障工时与附件表4逐行不一致: {source_times}")
        # Build the actual task-skill eligibility map from Appendix 4.
        self.skill_candidates = {skill: [] for skill in SKILL_GROUP}
        for row in skill_rows:
            primary, second, third = row[1].strip(), row[2].strip(), row[3].strip()
            group = SKILL_GROUP[primary]
            self.skill_candidates[primary].append((group, 1, None, None))
            for skill in filter(None, second.split("、")):
                self.skill_candidates[skill].append((group, 2, None, None))
            third_skills = list(filter(None, third.split("、")))
            promotion_vars = []
            for skill in third_skills:
                if self.optimize_skills:
                    promote = self.model.NewBoolVar(f"promote_{group}_{skill}")
                    self.skill_upgrades[(group, skill)] = promote
                    promotion_vars.append(promote)
                    self.skill_candidates[skill].append((group, 2, promote, 1))
                    self.skill_candidates[skill].append((group, 3, promote, 0))
                else:
                    self.skill_candidates[skill].append((group, 3, None, None))
            if self.optimize_skills:
                # Promote one existing third skill to a second skill per row:
                # 1 fixed first + 3 second + 1 third = 5 total skills.
                self.model.Add(sum(promotion_vars) == 1)
        if self.test_count is not None:
            nmax = self.test_count
        elif self.fixed_count is not None:
            nmax = self.fixed_count
        else:
            nmax = min(CANDIDATE_AIRCRAFT, 100)
        complete = [self.model.NewBoolVar(f"complete_{i}") for i in range(nmax)]
        tow = [self.model.NewBoolVar(f"tow_{i}") for i in range(nmax)]
        oil = [self.model.NewBoolVar(f"oil_{i}") for i in range(nmax)]
        # Symmetry breaking: a completed set is always a prefix, without changing attainable counts.
        for i in range(nmax - 1):
            self.model.Add(complete[i] >= complete[i + 1])
        total = self.model.NewIntVar(0, nmax, "completed_aircraft")
        self.model.Add(total == sum(complete))
        tow_total = sum(tow)
        oil_total = sum(oil)
        # Explicit intersection variables keep the 20% nested oil/tow rule auditable.
        both = []
        for i in range(nmax):
            x = self.model.NewBoolVar(f"both_{i}")
            self.model.Add(x <= tow[i])
            self.model.Add(x <= oil[i])
            self.model.Add(x >= tow[i] + oil[i] - 1)
            both.append(x)
            self.model.Add(tow[i] <= complete[i])
            self.model.Add(oil[i] <= complete[i])
        # Counts use cumulative ceiling at the task level.
        self.model.Add(10 * tow_total >= total)
        self.model.Add(10 * tow_total <= total + 9)
        self.model.Add(10 * oil_total >= total)
        self.model.Add(10 * oil_total <= total + 9)
        self.model.Add(5 * sum(both) >= tow_total)
        self.model.Add(5 * sum(both) <= tow_total + 4)

        d = {"tow": source_times[0][0], "power_a": source_times[4][0],
             "aircon_a": source_times[5][0], "oil": source_times[6][0],
             "fuel": source_times[1][0], "oxygen": source_times[2][0],
             "nitrogen": source_times[3][0], "meal": source_times[7][0],
             "power_b": source_times[4][0], "aircon_b": source_times[5][0]}
        task_starts = {}
        task_ends = {}
        electrical_names = {"power_a": (d["power_a"], "Z5"), "aircon_a": (d["aircon_a"], "Z6"),
                            "power_b": (d["power_b"], "Z5"), "aircon_b": (d["aircon_b"], "Z6")}
        for i in range(nmax):
            p = complete[i]
            specs = [
                ("tow", tow[i], d["tow"], "牵引", "Z1", 1, 1),
                ("oil", oil[i], d["oil"], "附油", "Z7", 1, 1),
                ("fuel", p, d["fuel"], "加油", "Z2", 1, 1),
                ("oxygen", p, d["oxygen"], "充气", "Z3", 1, 1),
                ("nitrogen", p, d["nitrogen"], "充气", "Z4", 1, 1),
                ("meal", p, d["meal"], "餐食", "Z8", 1, 2),
            ]
            for name, active, dur, people, vehicle, dem, staff_dem in specs:
                st, en, _ = self.add_task((i, name), active, dur, people, vehicle, dem, staff_dem)
                task_starts[(i, name)] = st
                task_ends[(i, name)] = en

        # For each electrical/air-conditioning stage, choose between one vehicle
        # serving two aircraft together (one driver) and two singleton jobs.
        for i in range(0, nmax, 2):
            j = i + 1
            has_pair = j < nmax
            for name, (duration, vehicle) in electrical_names.items():
                # Pairing is a per-operation decision: Appendix 6 limits each
                # vehicle to at most two aircraft, but does not require the same
                # aircraft pair to remain together across the four stages.
                if has_pair:
                    paired = self.model.NewBoolVar(f"electric_paired_{i}_{name}")
                    self.model.Add(paired <= complete[i])
                    self.model.Add(paired <= complete[j])
                    singles = [self.model.NewBoolVar(f"electric_single_{k}_{name}")
                               for k in (i, j)]
                    self.model.Add(singles[0] + paired == complete[i])
                    self.model.Add(singles[1] + paired == complete[j])
                else:
                    paired = None
                    singles = [complete[i]]
                pair_key = ("pair", i, name)
                pair_result = (self.add_electrical_option(pair_key, paired, duration, vehicle)
                               if has_pair else None)
                single_keys = [("single", i, name)]
                single_results = [self.add_electrical_option(single_keys[0], singles[0], duration, vehicle)]
                if has_pair:
                    single_keys.append(("single", j, name))
                    single_results.append(self.add_electrical_option(single_keys[1], singles[1], duration, vehicle))
                for k, aircraft in enumerate((i, j) if has_pair else (i,)):
                    st = self.model.NewIntVar(0, self.limit, f"s_{aircraft}_{name}")
                    en = self.model.NewIntVar(0, self.limit, f"e_{aircraft}_{name}")
                    if has_pair:
                        pair_st, pair_en, pair_intervals = pair_result
                        self.model.Add(st == pair_st).OnlyEnforceIf(paired)
                        self.model.Add(en == pair_en).OnlyEnforceIf(paired)
                        all_intervals = pair_intervals + single_results[k][2]
                        links = [pair_key, single_keys[k]]
                    else:
                        all_intervals = single_results[k][2]
                        links = [single_keys[k]]
                    self.model.Add(st == single_results[k][0]).OnlyEnforceIf(singles[k])
                    self.model.Add(en == single_results[k][1]).OnlyEnforceIf(singles[k])
                    task_key = (aircraft, name)
                    task_starts[task_key] = st
                    task_ends[task_key] = en
                    self.task[task_key] = (st, en, all_intervals, complete[aircraft])
                    self._task_skill_links[task_key] = links

        # Add process and incompatibility constraints once every operation exists.
        for i in range(nmax):
            if not self.reorder:
                for op in ("power_a", "aircon_a", "oil", "fuel"):
                    self.model.Add(task_starts[(i, op)] >= task_ends[(i, "tow")]).OnlyEnforceIf(tow[i])
                self.model.Add(task_starts[(i, "oxygen")] >= task_ends[(i, "power_a")])
                self.model.Add(task_starts[(i, "oxygen")] >= task_ends[(i, "aircon_a")])
                self.model.Add(task_starts[(i, "nitrogen")] >= task_ends[(i, "power_a")])
                self.model.Add(task_starts[(i, "nitrogen")] >= task_ends[(i, "aircon_a")])
            else:
                # Reordered-flow case retains tow-before-work, meal-after-fuel/gases,
                # and fixed B-stage order from the source diagram.
                for op in ("power_a", "aircon_a", "oil", "fuel"):
                    self.model.Add(task_starts[(i, op)] >= task_ends[(i, "tow")]).OnlyEnforceIf(tow[i])
            # Oil/fuel/gas and pre-B jobs precede meal. In both cases meal follows gas and fuel.
            self.model.Add(task_starts[(i, "oxygen")] >= task_ends[(i, "fuel")])
            self.model.Add(task_starts[(i, "nitrogen")] >= task_ends[(i, "fuel")])
            if not self.reorder:
                self.model.Add(task_starts[(i, "oxygen")] >= task_ends[(i, "oil")]).OnlyEnforceIf(oil[i])
                self.model.Add(task_starts[(i, "nitrogen")] >= task_ends[(i, "oil")]).OnlyEnforceIf(oil[i])
            self.model.Add(task_starts[(i, "meal")] >= task_ends[(i, "oxygen")])
            self.model.Add(task_starts[(i, "meal")] >= task_ends[(i, "nitrogen")])
            if not self.reorder:
                self.model.Add(task_starts[(i, "meal")] >= task_ends[(i, "power_a")])
                self.model.Add(task_starts[(i, "meal")] >= task_ends[(i, "aircon_a")])
            self.model.Add(task_starts[(i, "power_b")] >= task_ends[(i, "meal")])
            self.model.Add(task_starts[(i, "aircon_b")] >= task_ends[(i, "meal")])

            # Oxygen cannot overlap fuel or any electrical-power stage. Power cannot overlap oxygen or meal.
            incompatible = [("oxygen", "fuel"), ("nitrogen", "fuel"), ("oxygen", "power_a"),
                            ("nitrogen", "power_a"), ("oxygen", "power_b"), ("nitrogen", "power_b"),
                            ("power_a", "meal"), ("power_b", "meal")]
            for left, right in incompatible:
                self.model.AddNoOverlap(self.task[(i, left)][2] + self.task[(i, right)][2])

        # One Z9 supports material packages of up to 20 aircraft, each package takes 10 minutes.
        material_ends = {}
        for batch in range(ceil_div(nmax, 20)):
            members = range(batch * 20, min((batch + 1) * 20, nmax))
            active = self.model.NewBoolVar(f"material_batch_{batch}")
            self.model.AddMaxEquality(active, [complete[i] for i in members])
            st, en, interval = self.add_task(("material", batch), active, source_times[8][0],
                                             {"M3": 1, "M4": 2}, "Z9", 1)
            for i in members:
                material_ends[i] = en
                self.model.Add(st >= task_ends[(i, "tow")]).OnlyEnforceIf(tow[i])

        # One Z9 opens sequential parachute points, each serves up to 40 aircraft.
        parachute_ends = {}
        for batch in range(ceil_div(nmax, 40)):
            members = list(range(batch * 40, min((batch + 1) * 40, nmax)))
            active = self.model.NewBoolVar(f"parachute_batch_{batch}")
            self.model.AddMaxEquality(active, [complete[i] for i in members])
            count = sum(complete[i] for i in members)
            parachute_base = int(round(source_times[9][0] * SCALE))
            parachute_per_aircraft = SCALE // 2
            duration = self.model.NewIntVar(0, parachute_base + parachute_per_aircraft * 40,
                                            f"parachute_duration_{batch}")
            self.model.Add(duration == parachute_base * active + parachute_per_aircraft * count)
            start = self.model.NewIntVar(0, self.limit, f"parachute_start_{batch}")
            end = self.model.NewIntVar(0, self.limit, f"parachute_end_{batch}")
            self.add_variable_skill_task(("parachute", batch), active, start, end, duration,
                                         "伞勤", "Z9", vehicle_demand=1, staff_demand=2)
            if batch > 0:
                self.model.Add(start >= parachute_ends[batch - 1]).OnlyEnforceIf(active)
            for i in members:
                self.model.Add(start >= material_ends[i]).OnlyEnforceIf(complete[i])
                if not self.reorder:
                    self.model.Add(task_starts[(i, "meal")] >= end).OnlyEnforceIf(complete[i])
                parachute_ends[i] = end

        for group, intervals in self.people_intervals.items():
            if self.fixed_count is not None:
                self.extra_people[group] = self.model.NewIntVar(0, 200, f"extra_{group}")
                cap = 2 * (PEOPLE[group] + self.extra_people[group])
            else:
                cap = 2 * PEOPLE[group]
            if intervals:
                self.model.AddCumulative(intervals, self.people_demands[group], cap)
        for vehicle, intervals in self.vehicle_intervals.items():
            if self.fixed_count is not None:
                self.extra_vehicles[vehicle] = self.model.NewIntVar(0, 100, f"extra_{vehicle}")
                count = VEHICLES[vehicle] + self.extra_vehicles[vehicle]
            else:
                count = VEHICLES[vehicle]
            if intervals:
                self.model.AddCumulative(intervals, self.vehicle_demands[vehicle], count * VEHICLE_UNITS[vehicle])

        # Task-table total-count requirements for the fleet sizes tied directly to demand.
        # These rules are kept separate from interval concurrency capacities above.
        if self.test_count is not None:
            self.model.Add(total == self.test_count)
            self.model.Add(total <= 10 * VEHICLES["Z3"])
            self.model.Add(total <= 10 * VEHICLES["Z4"])
            self.model.Minimize(0)
        elif self.fixed_count is not None:
            self.model.Add(total == self.fixed_count)
            # Appendix rule: for N aircraft, each of Z3 and Z4 is exactly ceil(N/10).
            z34_required = ceil_div(self.fixed_count, 10)
            self.model.Add(VEHICLES["Z3"] + self.extra_vehicles["Z3"] >= z34_required)
            self.model.Add(VEHICLES["Z4"] + self.extra_vehicles["Z4"] >= z34_required)
            z1_required = self.model.NewIntVar(0, 200, "z1_required_by_tow_count")
            allowed = []
            for tow_count in range(nmax + 1):
                if tow_count <= 4:
                    required = ceil_div(tow_count, 2)
                elif tow_count <= 8:
                    required = ceil_div(tow_count * 2, 3)
                else:
                    required = ceil_div(tow_count * 5, 6)
                allowed.append((tow_count, required))
            self.model.AddAllowedAssignments([tow_total, z1_required], allowed)
            self.model.Add(VEHICLES["Z1"] + self.extra_vehicles["Z1"] >= z1_required)
            vehicle_priority = {"Z6": 1, "Z5": 1, "Z2": 2, "Z8": 2,
                                "Z1": 3, "Z3": 4, "Z4": 4, "Z9": 5, "Z7": 6}
            vehicle_count = sum(self.extra_vehicles.values())
            vehicle_priority_score = sum(vehicle_priority[k] * v for k, v in self.extra_vehicles.items())
            people_score = sum(self.extra_people.values())
            if self.max_added_vehicles is not None:
                self.model.Add(vehicle_count <= self.max_added_vehicles)
            # Lexicographic objective encoded with proven bounds:
            # people_score <= 8*200 = 1,600; priority_score <= 100*sum(priorities)=2,800.
            # Thus 2,000 dominates all people additions, and 6,000,000 dominates
            # every possible priority/personnel tie-break contribution.
            self.model.Minimize(6_000_000 * vehicle_count + 2_000 * vehicle_priority_score + people_score)
        else:
            # Existing fleets must cover the task-table requirement ceil(N/10).
            self.model.Add(total <= 10 * VEHICLES["Z3"])
            self.model.Add(total <= 10 * VEHICLES["Z4"])
            self.model.Maximize(total)
        self.completions = complete
        self.tow = tow
        self.oil = oil
        self.total = total
        self.task_starts = task_starts
        self.task_ends = task_ends
        return self.model

    def solve(self, time_limit: float = 60):
        self.build()
        hints = {}

        def add_hint(variable, value):
            index = variable.Index()
            value = int(value)
            if index in hints and hints[index][1] != value:
                raise ValueError(f"冲突热启动变量: {variable.Name()}")
            hints[index] = (variable, value)
        # Warm-start the multiskill model from a previously feasible single-skill
        # schedule. First-skill assignments reproduce the same durations/capacities.
        warm_start_count = (self.test_count == 40 or self.fixed_count == 156
                            or (self.test_count is None and self.fixed_count is None))
        if warm_start_count:
            if self.fixed_count == 156:
                hint_path = ROOT / "results" / ("q1_skilloptimized_reordered156_candidate.csv" if self.reorder
                                                  else "q1_skilloptimized_fixed156_candidate.csv")
                if not hint_path.exists():
                    hint_path = ROOT / "results" / "q1_fixed156_schedule.csv"
            else:
                hint_path = ROOT / "results" / ("q1_reordered_max_schedule.csv" if self.reorder
                                                  else "q1_fixed_flow_max_schedule.csv")
            if hint_path.exists():
                rows = list(csv.DictReader(hint_path.open(encoding="utf-8-sig")))
                by_key = {}
                rows_by_key = {}
                for row in rows:
                    raw_aircraft = row["aircraft"]
                    key = (int(raw_aircraft) if raw_aircraft.isdigit() else raw_aircraft,
                           int(row["operation"]) if row["operation"].isdigit() else row["operation"])
                    by_key[key] = (float(row["start_min"]), float(row["end_min"]))
                    rows_by_key[key] = row
                tow_ids = {key[0] for key in by_key if isinstance(key[0], int) and key[1] == "tow"}
                oil_ids = {key[0] for key in by_key if isinstance(key[0], int) and key[1] == "oil"}
                hinted_total = self.fixed_count or self.test_count or 40
                for i in range(len(self.completions)):
                    add_hint(self.completions[i], int(i < hinted_total))
                    add_hint(self.tow[i], int(i in tow_ids))
                    add_hint(self.oil[i], int(i in oil_ids))
                for key, (st, en, intervals, presence) in self.task.items():
                    if key in by_key:
                        start, end = by_key[key]
                        assignment = rows_by_key[key]
                        hinted_group = assignment.get("operator_group", "")
                        hinted_level = int(assignment.get("skill_level") or 0)
                        links = self._task_skill_links.get(key)
                        if links:
                            for link in links:
                                link_presence = self.task[link][3]
                                is_pair = link[0] == "pair"
                                # The prior aircraft-level schedule is encoded as
                                # singleton electrical jobs: disable pairs and
                                # activate the matching aircraft's singleton.
                                add_hint(link_presence, int(not is_pair))
                                if not is_pair:
                                    link_st, link_en = self.task[link][0], self.task[link][1]
                                    add_hint(link_st, round(start * SCALE))
                                    add_hint(link_en, round(end * SCALE))
                                for (group, level), var in self.skill_choice_vars.get(link, {}).items():
                                    if hinted_group:
                                        hint_value = int(not is_pair and group == hinted_group and level == hinted_level)
                                    else:
                                        hint_value = int(not is_pair and level == 1 and group == SKILL_GROUP[self._task_skill[link]])
                                    add_hint(var, hint_value)
                        elif key not in self._task_skill_links:
                            add_hint(st, round(start * SCALE))
                            add_hint(en, round(end * SCALE))
                            for (group, level), var in self.skill_choice_vars.get(key, {}).items():
                                if hinted_group:
                                    hint_value = int(group == hinted_group and level == hinted_level)
                                elif key in self._task_skill:
                                    hint_value = int(level == 1 and group == SKILL_GROUP[self._task_skill[key]])
                                else:
                                    hint_value = 0
                                add_hint(var, hint_value)
                if self.fixed_count == 156:
                    candidate_path = ROOT / "results" / ("q1_reordered156_resource_additions.json" if self.reorder
                                                            else "q1_fixed156_resource_additions.json")
                    if not candidate_path.exists():
                        candidate_path = ROOT / "results" / "q1_resource_additions.json"
                    saved = json.loads(candidate_path.read_text(encoding="utf-8"))
                    seed_people, seed_vehicles = self.seed_resources_from_schedule(rows, self.fixed_count)
                    seed_is_allowed = (self.max_added_vehicles is None
                                       or sum(seed_vehicles.values()) <= self.max_added_vehicles)
                    promoted = {tuple(item) for item in saved.get("promoted_skills", [])}
                    for (group, skill), variable in self.skill_upgrades.items():
                        add_hint(variable, int((group, skill) in promoted))
                    for group, var in self.extra_people.items():
                        hint_value = seed_people[group] if seed_is_allowed else saved["people_additions"][group]
                        add_hint(var, int(hint_value))
                    for vehicle, var in self.extra_vehicles.items():
                        hint_value = seed_vehicles[vehicle] if seed_is_allowed else saved["vehicle_additions"][vehicle]
                        add_hint(var, int(hint_value))
        for variable, value in hints.values():
            self.model.AddHint(variable, value)
        solver = cp_model.CpSolver()
        validation_error = self.model.Validate()
        if validation_error:
            raise ValueError(f"CP-SAT模型/热启动校验失败: {validation_error}")
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        if self.validate_warm_start:
            solver.parameters.fix_variables_to_their_hinted_value = True
            solver.parameters.cp_model_presolve = False
        status = solver.Solve(self.model)
        return solver, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--reorder", action="store_true")
    parser.add_argument("--fixed-count", type=int)
    parser.add_argument("--test-count", type=int)
    parser.add_argument("--max-added-vehicles", type=int)
    parser.add_argument("--optimize-skills", action="store_true")
    parser.add_argument("--validate-warm-start", action="store_true")
    parser.add_argument("--time-limit", type=float, default=60)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "q1_schedule.csv")
    args = parser.parse_args()
    if not RESOURCE_FILE.exists():
        raise FileNotFoundError("先运行 提取第一题数据.py")
    model = FirstServiceModel(args.limit, args.reorder, fixed_count=args.fixed_count,
                              test_count=args.test_count, max_added_vehicles=args.max_added_vehicles,
                              optimize_skills=(True if args.optimize_skills else None),
                              validate_warm_start=args.validate_warm_start)
    solver, status = model.solve(args.time_limit)
    result = {
        "status": solver.StatusName(status),
        "objective": solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        "bound": solver.BestObjectiveBound(),
        "limit_minutes": args.limit,
        "reordered": args.reorder,
        "fixed_aircraft_count": args.fixed_count,
        "tested_aircraft_count": args.test_count,
    }
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result["promoted_skills"] = sorted(
            [[group, skill] for (group, skill), variable in model.skill_upgrades.items()
             if solver.Value(variable)], key=lambda row: (row[0], row[1])
        )
        if args.fixed_count is not None:
            result["people_additions"] = {k: solver.Value(v) for k, v in model.extra_people.items()}
            result["vehicle_additions"] = {k: solver.Value(v) for k, v in model.extra_vehicles.items()}
            resource_path = ROOT / "results" / ("q1_reordered156_resource_additions.json"
                                                 if args.reorder else "q1_fixed156_resource_additions.json")
            resource_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["aircraft", "operation", "start_min", "end_min", "skill", "operator_group", "skill_level"])
            for key, (start, end, interval, presence) in model.task.items():
                if isinstance(key[0], str) and key[0] in {"pair", "single"}:
                    continue
                if solver.Value(presence):
                    skill_links = model._task_skill_links.get(key, [key])
                    selected_skill = next((model._task_skill[link] for link in skill_links
                                           if link in model._task_skill), "")
                    selected_group, selected_level = "", ""
                    for link in skill_links:
                        for (group, level), variable in model.skill_choice_vars.get(link, {}).items():
                            if solver.Value(variable):
                                selected_group, selected_level = group, level
                                break
                        if selected_group:
                            break
                    writer.writerow([*key, solver.Value(start) / SCALE, solver.Value(end) / SCALE,
                                     selected_skill, selected_group, selected_level])
        try:
            result["schedule_csv"] = str(args.output.relative_to(ROOT))
        except ValueError:
            result["schedule_csv"] = str(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
