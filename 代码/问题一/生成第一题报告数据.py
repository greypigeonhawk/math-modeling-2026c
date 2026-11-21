"""从第一题排程和复核器生成报告中的数值和表格。"""
import csv
import json
from pathlib import Path

from 验证第一问排程 import check
from 问题1_优化模型 import PEOPLE, VEHICLES, SKILL_GROUP

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
RETURNS = RESULTS / "h810itx_returns"
output = RESULTS / "q1_full_report_latex" / "evidence.tex"
lines = []


def macro(name, value):
    lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")


def table_row(values):
    return " & ".join(map(str, values)) + r" \\"


def audited(stem, n, limit, reordered=False, sizes=None, with_resources=False):
    path = RETURNS / (stem + ".csv")
    resources = path.with_name(path.stem + "_resources.json") if with_resources else None
    audit = check(path, reordered, n, limit, resources, b_final=reordered, parachute_sizes=sizes)
    if audit["status"] != "PASS":
        raise ValueError(audit)
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    tally = (sum(audit["vehicle_additions"].values()), sum(audit["people_additions"].values()))
    last = max(float(row["end_min"]) for row in rows)
    return audit, tally, last


def main():
    cases = {
        "FixedShort": ("peer_flow/fixed48_preset", 48, 100, False, [20,20,8], False),
        "FlexShort": ("round3/reordered52", 52, 100, True, [20,20,12], False),
        "FixedLong": ("round3/fixed", 156, 120, False, None, True),
        "FlexLong": ("round3/reordered", 156, 120, True, None, True),
        "Original": ("batch_v3/fixed156_original_skills", 156, 120, False, None, True),
    }
    logs = {}
    for name, case in cases.items():
        audit, (cars, people), last = audited(*case)
        logs[name] = audit
        for label, val in (("Aircraft",audit["aircraft"]),("Cars",cars),("People",people),("Last",f"{last:g}")):
            macro(name+label,val)
    original_flex, _, _ = audited("batch_v3/fixed156_original_skills", 156, 120, True, with_resources=True)
    for key, name in (("vehicle", "VehicleRows"),("staff","StaffRows")):
        rows = []
        pools = VEHICLES if key == "vehicle" else PEOPLE
        field = "vehicle_additions" if key == "vehicle" else "people_additions"
        for item, available in pools.items():
            values = [item, available]
            for mode in ("FixedLong","FlexLong"):
                stamp = logs[mode]
                peak = stamp["resource_peaks"].get(f"{key}_{item}",0)
                values.extend([stamp[field].get(item,0),peak if key == "vehicle" else peak//2])
            rows.append(table_row(values))
        macro(name,"\n".join(rows))

    table = json.loads((RESULTS/"q1_source_tables.json").read_text())["multi_skill_table"][1:]
    promoted = dict(json.loads((RETURNS/"round3/fixed_resources.json").read_text())["promoted_skills"])
    flex = dict(json.loads((RETURNS/"round3/reordered_resources.json").read_text())["promoted_skills"])
    if promoted != flex:
        raise ValueError("两种流程的技能调整不一致")
    rows = {}
    for _, primary, second, third in table:
        group = SKILL_GROUP[primary.strip()]
        level2 = second.strip().split("、")
        level3 = third.strip().split("、")
        changed = promoted.get(group)
        if changed:
            level3.remove(changed)
            level2.append(changed)
        rows[group] = table_row([group, primary.strip(), "、".join(level2), "、".join(level3), changed or "—"])
    macro("SkillRows","\n".join(rows[group] for group in PEOPLE))
    output.write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()
