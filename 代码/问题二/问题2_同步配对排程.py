"""第二问同步配对。每项电源/空调服务独占一辆车和一人。"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from 问题2_多技能双容量候选 import Q2Model, load_inputs, run_case

PAIRABLE = {"power_a", "aircon_a", "power_b", "aircon_b"}


class SynchronousModel(Q2Model):
    def __init__(self, a, b, data, baseline):
        times = {(r["aircraft"], r["operation"]): r["start_min"]
                 for r in baseline.get("operations", [])}
        self.leaders = {}
        # Prefer pairings whose prior release times were similar. Aircraft in a
        # pair share the type, operation and proficiency, hence the duration.
        for operation in sorted(PAIRABLE):
            for members in (range(a), range(a, a + b)):
                ordered = sorted(members, key=lambda i: (times.get((i, operation), 0), i))
                for left, right in zip(ordered[::2], ordered[1::2]):
                    self.leaders[(max(left, right), operation)] = (min(left, right), operation)
        super().__init__(a, b, data)

    def _add_resource_option(self, key, base, required, vehicle, people, pairable, start, end):
        leader_key = self.leaders.get(key)
        if leader_key is None:
            super()._add_resource_option(key, base, required, vehicle, people, False, start, end)
            return
        leader = self.operations[leader_key]
        self.model.Add(start == leader["start"])
        self.model.Add(end == leader["end"])
        choices = []
        for option in leader["choices"]:
            flag = self.model.NewBoolVar(f"paired_{key[0]}_{key[1]}_{len(choices)}")
            self.model.Add(flag == option["choice"])
            choices.append(dict(option, choice=flag))
        self.operations[key]["choices"] = choices

    def add_json_hints(self, baseline):
        rows = {(r["aircraft"], r["operation"]): r for r in baseline.get("operations", [])}
        for follower, leader in self.leaders.items():
            if follower in rows and leader in rows:
                reference = max((rows[follower], rows[leader]), key=lambda r: r["start_min"])
                for aircraft, operation in (leader, follower):
                    rows[(aircraft, operation)] = dict(reference, aircraft=aircraft)
        super().add_json_hints(dict(baseline, operations=list(rows.values())))
        from 问题2_多技能双容量候选 import SCALE
        batch_rows = {(r["operation"], r["batch"]): r for r in baseline.get("batch_operations", [])}
        for kind, number, start, end, _ in self.batches:
            row = batch_rows.get((kind, number))
            if row is not None:
                self.model.AddHint(start, round(row["start_min"] * SCALE))
                self.model.AddHint(end, round(row["end_min"] * SCALE))

    def extract(self, solver, status, stage_results):
        result = super().extract(solver, status, stage_results)
        result["scope"] = "same-type synchronous power/aircon pairs with one shared vehicle and operator"
        result.pop("aggregation_warning", None)
        result.pop("pairable_overlaps", None)
        partners = {**self.leaders, **{v: k for k, v in self.leaders.items()}}
        for row in result["operations"]:
            partner = partners.get((row["aircraft"], row["operation"]))
            if partner is not None:
                row.update(mode="synchronous_pair", pair_with=partner[0])
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=25)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--order", choices=("people", "vehicles"), default="people")
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    _, raw, data = load_inputs()
    result = run_case(baseline["aircraft_a"], baseline["aircraft_b"], data, args.seconds,
                      args.workers, baseline, args.order, args.seconds,
                      lambda a, b, d: SynchronousModel(a, b, d, baseline))
    result.update(source_sha256=data["source_sha256"],
                  normalized_input_sha256=hashlib.sha256(raw).hexdigest(),
                  baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                  solver_parameters=dict(seconds_per_stage=args.seconds, workers=args.workers,
                                         random_seed=20261121, order=args.order))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(result["status"], result["dispatch_people"], result["dispatch_vehicles"], result["stage_results"])
    if not result["operations"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
