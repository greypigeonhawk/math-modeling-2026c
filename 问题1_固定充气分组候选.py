"""通过预先指定充气分组缩小第一题搜索空间，只用于构造可行解。"""
import os

import 问题1_优化模型 as solver


class GroupedGasModel(solver.FirstServiceModel):
    def __init__(self, *args, **kwargs):
        if os.environ.get("Q1_ORIGINAL_SKILLS") == "1":
            kwargs["optimize_skills"] = False
        super().__init__(*args, **kwargs)

    def solve(self, time_limit=60, workers=8):
        return super().solve(time_limit, workers, use_schedule_hint=False)

    def add_task(self, key, presence, duration_minutes, people, vehicle, vehicle_demand=1, staff_demand=1):
        if (os.environ.get("Q1_PRIMARY_EXCEPT_ELECTRICAL") == "1"
                and isinstance(people, str) and people != "电源空调"):
            options = self.skill_candidates[people]
            self.skill_candidates[people] = [option for option in options if option[1] == 1]
            try:
                return super().add_task(key, presence, duration_minutes, people, vehicle,
                                        vehicle_demand, staff_demand)
            finally:
                self.skill_candidates[people] = options
        return super().add_task(key, presence, duration_minutes, people, vehicle,
                                vehicle_demand, staff_demand)

    def parachute_groups(self, nmax):
        sizes = os.environ.get("Q1_PARACHUTE_GROUPS")
        if not sizes:
            return super().parachute_groups(nmax)
        counts = [int(value) for value in sizes.split(",")]
        if sum(counts) != nmax or any(not 1 <= count <= 40 for count in counts):
            raise ValueError("伞勤分组须覆盖全体飞机，且每组1至40架")
        groups = []
        start = 0
        for count in counts:
            groups.append(range(start, start + count))
            start += count
        return groups

    def build(self):
        model = super().build()
        if self.reorder and os.environ.get("Q1_B_FINAL") == "1":
            parachute_batch = {i: batch for batch, group in
                               enumerate(self.parachute_groups(len(self.completions))) for i in group}
            for i, complete in enumerate(self.completions):
                for last in ("power_b", "aircon_b"):
                    start = self.task_starts[i, last]
                    for earlier in ("power_a", "aircon_a"):
                        model.Add(start >= self.task_ends[i, earlier]).OnlyEnforceIf(complete)
                    model.Add(start >= self.task_ends[i, "oil"]).OnlyEnforceIf(self.oil[i])
                    model.Add(start >= self.task["parachute", parachute_batch[i]][1]).OnlyEnforceIf(complete)
        if os.environ.get("Q1_FORCE_ELECTRICAL_PAIRS") == "1":
            for key, task in self.task.items():
                if key[0] == "pair":
                    model.Add(task[3] == self.completions[key[1] + 1])
        limits = os.environ.get("Q1_VEHICLE_CAPS")
        if limits:
            caps = [int(value) for value in limits.split(",")]
            if len(caps) != len(solver.VEHICLES) or self.fixed_count is None:
                raise ValueError("增援上限需要固定任务规模及Z1至Z9九项")
            for kind, cap in zip(solver.VEHICLES, caps):
                model.Add(self.extra_vehicles[kind] <= cap)
        limit_people = os.environ.get("Q1_M7_CAP_ONLY")
        if limit_people is not None:
            for group, variable in self.extra_people.items():
                model.Add(variable <= (int(limit_people) if group == "M7" else 0))
        if os.environ.get("Q1_PEER_PIPELINE") == "1":
            self.fix_peer_pipeline(model)
        return model

    def fix_peer_pipeline(self, model):
        n = len(self.completions)
        if n == 48 and [len(group) for group in self.parachute_groups(n)] == [20, 20, 8]:
            material_starts = [0, 26, 52]
            parachute_starts = [10, 36, 62]
            for i in range(n):
                model.Add(self.task_starts[i, "fuel"] == 15 * (i // 12) * solver.SCALE)
                model.Add(self.tow[i] == (i in {20,21,22,23,24}))
                model.Add(self.oil[i] == (i in {20, 0, 4, 8, 12}))
        elif n == 156 and [len(group) for group in self.parachute_groups(n)] == [40, 40, 40, 36]:
            material_starts = [0, 10, 0, 10, 46, 56, 46, 56]
            parachute_starts = [20, 20, 66, 66]
        elif n == 156 and [len(group) for group in self.parachute_groups(n)] == [20] * 7 + [16]:
            material_starts = [0, 0, 0, 26, 26, 26, 52, 52]
            parachute_starts = [start + 10 for start in material_starts]
        else:
            raise ValueError("流水线只定义了48架与156架的指定分组")
        for operation, starts in (("material", material_starts), ("parachute", parachute_starts)):
            for batch, start in enumerate(starts):
                model.Add(self.task[operation, batch][0] == start * solver.SCALE)

    def add_gas_batches(self, operation, vehicle, duration_minutes, complete, nmax,
                        task_starts, task_ends):
        width = int(os.environ.get("Q1_GAS_GROUP_SIZE", "2"))
        if not 1 <= width <= solver.GAS_BATCH_CAPACITY:
            raise ValueError("充气分组大小超出车辆容量")
        if self.fixed_count is None and self.test_count is None:
            raise ValueError("预分组模型需要指定飞机架数")
        primary_only = os.environ.get("Q1_GAS_PRIMARY_ONLY") == "1"
        original_skills = self.skill_candidates["充气"]
        if primary_only:
            self.skill_candidates["充气"] = [
                entry for entry in original_skills if entry[1] == 1
            ]
        try:
            for batch, first in enumerate(range(0, nmax, width)):
                batch_key = ("gas_batch", operation, batch)
                self.internal_tasks.add(batch_key)
                start, end, intervals = self.add_task(
                    batch_key, complete[first], duration_minutes, "充气", vehicle)
                for i in range(first, min(first + width, nmax)):
                    key = (i, operation)
                    self.task[key] = (start, end, intervals, complete[i])
                    task_starts[key], task_ends[key] = start, end
                    self._task_skill_links[key] = [batch_key]
                    self.gas_batch_assignments[key] = [
                        self.model.NewConstant(0)
                    ] * batch + [complete[i]]
        finally:
            self.skill_candidates["充气"] = original_skills


if __name__ == "__main__":
    solver.FirstServiceModel = GroupedGasModel
    solver.main()
