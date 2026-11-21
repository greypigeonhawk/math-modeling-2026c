"""用原题数据和第三问核验结果生成三类证据图及模型流程。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import PercentFormatter

from utils.q3_plot_style import apply_publication_style, export_figure
from 问题3_复核 import DEFAULT_OUTPUT, ROOT, read_rows, source_limits, table_rows, Document, SOURCE

DEFAULT_FIGURES = ROOT / "figures/问题3专项"
BLUE, RUST, GRAY = "#254C72", "#B56337", "#6B767F"
STATION = {"F2": "#528378", "F3": BLUE, "F4": RUST}
HATCH = {"0405": "//", "0809": "...."}
OPS = {
    "0102": ("牵引", "#70628A"), "0203": ("逐机发伞", "#56626A"),
    "0204": ("加油", BLUE), "0405": ("充氧/充氮", "#997240"), "0406": ("充氧/充氮", "#997240"),
    "0708": ("餐食", "#528378"), "0809": ("电源/空调", RUST), "0810": ("电源/空调", RUST),
}


def canvas(height=2.5):
    return plt.subplots(figsize=(6.1, height), layout="constrained")


def export(fig, folder, name):
    export_figure(fig, folder / name)
    plt.close(fig)


def heatmap(fig, ax, matrix, xlabels, ylabels, label):
    m = ax.pcolormesh(matrix, cmap="Blues", vmin=0)
    ax.invert_yaxis()
    ax.set_xticks([index + 0.5 for index in range(len(xlabels))], xlabels)
    ax.set_yticks([index + 0.5 for index in range(len(ylabels))], ylabels)
    colorbar = fig.colorbar(m, ax=ax, label=label, pad=0.035, fraction=0.055)
    colorbar.solids.set_rasterized(False)


def raw_data(folder, parking, stock):
    fig, ax = canvas()
    lanes = list(parking)
    for typ, dx, color, hatch in (("A", -0.18, BLUE, None), ("B", 0.18, RUST, "//")):
        ax.bar([j + dx for j in range(len(lanes))], [parking[lane][typ] for lane in lanes],
               width=0.35, label=f"{typ} 型机", color=color,
               edgecolor="white" if hatch else color, linewidth=0.4, hatch=hatch)
    ax.set(xticks=range(len(lanes)), xticklabels=lanes, ylabel="停机容量（架）", ylim=(0, 28))
    ax.legend(frameon=False, ncols=2)
    export(fig, folder, "raw_q3_parking")

    fig, ax = canvas(2.15)
    keys = [f"Z{i}" for i in range(1, 10)]
    lanes = list(stock)
    matrix = [[stock[r][key] for key in keys] for r in lanes]
    heatmap(fig, ax, matrix, keys, lanes, "库存（辆）")
    for j, row in enumerate(matrix):
        for i, value in enumerate(row):
            ax.text(i + 0.5, j + 0.5, str(value), ha="center", va="center", color="white" if value > 10 else BLUE)
    export(fig, folder, "raw_q3_vehicles")

    fig, ax = canvas(2.75)
    raw = list(table_rows(Document(SOURCE).tables[7]))
    distances = [[int(k) for k in row[1:]] for row in raw[1:] if row[0] in "甲乙丙丁戊己庚"]
    short_lanes = [f"F{i}" for i in range(1, 8)]
    heatmap(fig, ax, distances, short_lanes, short_lanes, "公路里程（km）")
    export(fig, folder, "raw_q3_distance")


def processes(folder, schedule):
    rows = read_rows(schedule, "逐机工序")
    ids = (73, 74, 1, 2, 3, 4, 5, 6)
    fig, ax = canvas(3.05)
    for row in rows:
        if (row["波次"], row["批次"]) != ("1", "1"):
            break
        code = row["再次出动保障工序"]
        if code in {"0406", "0810"}:
            continue
        start, end = (float(row[k]) for k in ("工序开始时刻", "工序结束时刻"))
        _, color = OPS[code]
        lane = ids.index(int(row["飞机编号"]))
        is_parachute = code == "0203"
        ax.barh(lane + (0.36 if is_parachute else -0.05), end - start, left=start,
                height=0.19 if is_parachute else 0.57, color=color,
                hatch=HATCH.get(code), edgecolor="white" if code in HATCH else color,
                linewidth=0.35)
        if code == "0102":
            ax.text((start + end) / 2, lane - 0.05, "牵引",
                    fontsize=6.5, color="white", ha="center", va="center")
    ax.set(xlabel="距批次首机着陆（分钟）", yticks=range(8),
           yticklabels=[f"{'B' if i >= 73 else 'A'}-{i:02d}" for i in ids], ylim=(7.55, -0.55))
    handles = [Rectangle((0, 0), 1, 1, fc=color, hatch=HATCH.get(code),
                         ec="white" if code in HATCH else color) for code, (_, color) in OPS.items()
               if code not in {"0102", "0406", "0810"}]
    ax.legend(handles, [name for code, (name, _) in OPS.items() if code not in {"0102", "0406", "0810"}],
              frameon=False, ncols=3, loc="lower left", bbox_to_anchor=(0, 1))
    export(fig, folder, "process_q3_batch")

    batch_rows = read_rows(schedule, "批次与伞勤点")
    lanes = ("F3", "F2", "F4")
    fig, ax = canvas(2.2)
    for j, lane in enumerate(lanes):
        positions = [int(row["全局批次"]) for row in batch_rows[:54] if row["停留跑道"] == lane]
        ax.scatter(positions, [j] * len(positions), color=STATION[lane], s=16, marker=("s", "o", "^")[j])
    ax.axvline(18.5, color=GRAY, ls="--", lw=0.8)
    ax.set(xlim=(0, 55), xlabel="54 批周期内的批次序号", yticks=range(3),
           yticklabels=lanes, ylim=(2.5, -0.5))
    export(fig, folder, "process_q3_cycle")

    fig, ax = canvas(2.45)
    rests = read_rows(schedule, "跑道休息")[:3]
    for j, lane in enumerate(lanes):
        row = next(r for r in rests if r["停留跑道"] == lane)
        close, start, end = (float(row[k]) for k in ("停止接收时刻", "休息开始", "休息结束"))
        ax.barh(j, start - close, left=close, height=0.46, color=STATION[lane])
        ax.barh(j, end - start, left=start, height=0.46, facecolor="white",
                edgecolor=GRAY, hatch="////", lw=0.7)
    ax.set(xlabel="K 后时间（分钟）", xlim=(0, 1200), yticks=range(3), yticklabels=lanes, ylim=(2.55, -0.55))
    ax.legend([Rectangle((0, 0), 1, 1, fc=BLUE),
               Rectangle((0, 0), 1, 1, fc="white", ec=GRAY, hatch="////")],
              ["清空已接收飞机", "驻场车人休息"], loc="lower left",
              bbox_to_anchor=(0, 1), frameon=False, ncols=2)
    export(fig, folder, "process_q3_rest")


def plot_results(folder, source, parking, stock, summary):
    fig, ax = canvas(2.55)
    flights = read_rows(source / "场景1", "着陆与放飞")
    for typ, color, marker in (("A", BLUE, "o"), ("B", RUST, "^")):
        counts = Counter(int(row["保障完工时刻"]) - int(row["着陆时刻"])
                         for row in flights if row["机型"] == typ)
        xs, ys = zip(*sorted(counts.items()))
        ax.vlines(xs, 0, ys, colors=color, linewidth=1.1)
        ax.scatter(xs, ys, color=color, marker=marker, label=f"{typ} 型机")
    ax.axvline(80, color=GRAY, ls="--", lw=1, label="80 分钟时限")
    ax.set(xlim=(35, 83), xlabel="着陆后保障耗时（分钟）", ylabel="架次", ylim=(0, 2400))
    ax.legend(frameon=False, ncols=3, loc="lower left", bbox_to_anchor=(0, 1))
    export(fig, folder, "result_q3_ground")

    fig, ax = canvas(2.5)
    observed = {}
    for info in summary.values():
        for key, value in info["停机峰值"].items():
            if not key.endswith("合计"):
                observed[key] = max(observed.get(key, 0), value)
    keys = list(sorted(observed))
    for j, key in enumerate(keys):
        lane, typ = key.split("/")
        cap = parking[lane][typ]
        ax.plot((observed[key], cap), (j, j), color="#ACB5BC", lw=1.2, zorder=1)
        ax.scatter(observed[key], j, marker="o", color=BLUE, zorder=3, s=18)
        ax.scatter(cap, j, marker="|", color=RUST, zorder=4, s=100)
    ax.set(xlabel="停机量（架）", yticks=range(len(keys)), yticklabels=keys,
           xlim=(0, 27), ylim=(len(keys) - 0.4, -0.6))
    handles = [plt.Line2D([], [], marker=marker, linestyle="", color=color)
               for marker, color in (("o", BLUE), ("|", RUST))]
    ax.legend(handles, ["停机峰值", "题面容量"], frameon=False, loc="lower right",
              bbox_to_anchor=(1, 1), ncols=2)
    export(fig, folder, "result_q3_parking")

    fig, ax = canvas(2.5)
    ratios = {}
    for info in summary.values():
        for key, peak in info["车人峰值"].items():
            lane, resource = key.split("/")
            ratios[resource] = max(ratios.get(resource, 0), peak / stock[lane][resource])
    keys = sorted(ratios, key=lambda item: (item[0] == "M", item))
    ax.bar(keys, [ratios[key] for key in keys],
           color=[BLUE if key.startswith("Z") else GRAY for key in keys])
    ax.axhline(1, color=RUST, lw=0.9, ls="--")
    ax.set(ylabel="并发峰值 / 库存", ylim=(0, 1.1))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    export(fig, folder, "result_q3_load")


def flowchart(folder):
    fig, ax = plt.subplots(figsize=(6.1, 1.9), layout="constrained")
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.set_axis_off()
    nodes = [
        (0.03, 0.38, "题面及\n三种状态", True),
        (0.23, 0.69, "批间距与\nB 机关键路径", False),
        (0.23, 0.10, "逐机模块与\n54 批周期", False),
        (0.44, 0.69, "解析下界", False),
        (0.44, 0.10, "全量事件复核", False),
        (0.65, 0.38, "下界与可行\n完工时刻比对", False),
        (0.84, 0.38, "最优值和\n排程附件", True),
    ]
    width, height = 0.145, 0.21
    for x, y, label, terminal in nodes:
        box = FancyBboxPatch((x, y), width, height,
                             boxstyle="round,pad=0.014" if terminal else "square,pad=0.012",
                             fc="#EAF1F5" if terminal else "white", ec=BLUE, linewidth=0.85)
        ax.add_patch(box)
        ax.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=8.4)
    for start, end in ((0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 5), (5, 6)):
        (a, b, *_), (c, d, *_) = nodes[start], nodes[end]
        ax.annotate("", (c - 0.012, d + height / 2), (a + width + 0.01, b + height / 2),
                    arrowprops={"arrowstyle": "->", "lw": 0.85, "color": GRAY})
    export(fig, folder, "flow_overall_model")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_FIGURES)
    args = parser.parse_args()
    apply_publication_style()
    parking, stock = source_limits()
    result = json.loads((args.source / "复核结果.json").read_text(encoding="utf-8"))
    raw_data(args.output, parking, stock)
    processes(args.output, args.source / "场景1")
    plot_results(args.output, args.source, parking, stock, result["scenarios"])
    flowchart(args.output)


if __name__ == "__main__":
    main()
