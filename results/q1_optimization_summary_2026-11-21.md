# 第一问优化复核（2026-11-21，更新版）

## 当前最好方案

在同一题面口径、允许调整工序先后、允许重新配对电源/空调作业的条件下，当前最好可复核方案是：

- **156 架 A 型机，120 分钟完成**；
- **新增车辆 51 辆**；
- **新增人员 2 人，均为 M7**；
- 独立验证器 `status=PASS`。

车辆增援向量按 `Z1…Z9` 为：

```text
(6, 16, 0, 0, 10, 9, 1, 7, 2)
```

总数为 51。人员增援为 `M7=2`，其余专业组为 0。技能调整为：`M1→加油`、`M3→电源空调`、`M5→餐食`、`M6→充气`、`M7→餐食`。

## 与队友稿比较

| 目标 | 队友稿/修正后基线 | 当前已复核结果 |
|---|---:|---:|
| 100 分钟可调流程 | 48 架 | **52 架**，99 分钟完成 |
| 156 架固定流程增援 | 52 辆/21 人（漏计 Z1；补齐后为 58/21） | 57 辆/5 人 |
| 156 架可调流程增援 | 无同口径可复核方案 | **51 辆/2 人** |

相对队友方案补齐牵引车后的 58 辆/21 人，当前可调方案少 **7 辆车、19 人**。相对上一版可调 57 辆/9 人，少 **6 辆车、7 人**。

## 独立复核命令

```bash
python '验证第一问排程.py' --flow reordered --b-final \
  --aircraft 156 --horizon 120 \
  results/q1_reordered156_51vehicle_candidate.csv \
  --resources results/q1_reordered156_51vehicle_candidate_resources.json
```

P1 独立质检复核：`PASS`，exit code=0；复核结果：`PASS`；牵引/附油/交集为 `16/16/4`；最大完工时间不超过 120 分钟；工序前置、B 段末端、技能、气体批次、车辆和人员峰值全部通过。

代表性峰值为：车辆 `Z2=28,Z5=25,Z6=24,Z8=17,Z9=3`，人员容量采用验证器的 2 倍单位，`M7=44`、`M1=80`、`M2=26`，均不超过增援后的容量。

## 搜索轨迹与边界

| 车辆上限 | 找到的可行方案 | 人员增援 | 状态 |
|---:|---:|---:|---|
| 57 | 57 | 9 | PASS |
| 56 | 56 | 7 | PASS |
| 55 | 55 | 4 | PASS |
| 54 | 54 | 5 | PASS |
| 53 | 53 | 2 | PASS |
| 52 | **51** | **2** | PASS |
| 50 | 未找到 | — | UNKNOWN |

“50 辆”只是 300 秒局部搜索未找到候选，不能解释为不可行证明。51 辆也是已验证可行上界，不是全局最优证明。

## 文件

- 最佳排程：[q1_reordered156_51vehicle_candidate.csv](q1_reordered156_51vehicle_candidate.csv)
- 最佳资源：[q1_reordered156_51vehicle_candidate_resources.json](q1_reordered156_51vehicle_candidate_resources.json)
- 复现清单：[q1_optimization_manifest.json](q1_optimization_manifest.json)
- 100 分钟 52 架排程：`h810itx_returns/round3/reordered52.csv`
- 固定流程 156 架 57 辆/5 人排程：`h810itx_returns/round3/fixed.csv`

这些仍是建模草稿级材料，提交前需人工核对附录取整和流程口径。
