# 2026 C 题：飞机保障调度

本仓库汇集三道题的建模代码、原题数据、排程结果、报告和附件模板。第一题与第二题的增援结果包含限时求解得到的可行方案，使用前请核对报告中的求解状态和假设。

## 目录

| 路径 | 内容 |
|---|---|
| `代码/问题一/` | 第一题求解、局部改进、报告数据和排程验证 |
| `代码/问题二/` | 第二题多技能调度、结果汇总、验证和配对证书 |
| `代码/问题三/` | 第三题三情景排程、复核、绘图和报告 |
| `代码/公共数据/` | 第二、三题输入提取与规范化 |
| `文档/` | 题目分析、术语表、队友参考稿和第三题报告 |
| `data/` | 原题文件 |
| `附件模版/` | 题目提供的三份 XLSX 原模板 |
| `results/` | 各题报告、排程、验证记录和历史计算结果 |
| `figures/`、`utils/` | 图表及绘图辅助代码 |

## 最新三问详细材料（2026-11-21）

- [第一问完整详细材料](results/三问详细材料/第一问_完整详细材料.docx)：固定流程 48 架达到上界；可调流程 52 架；156 架可调方案新增 51 辆、2 人，保留最优性边界。
- [第二问完整详细材料](results/三问详细材料/第二问_完整详细材料.docx)：三种机队的实体排班分别为 8 人7车、8人20车、26人26车。注意不同阶段共享假设及第三种情景负荷不均。
- [第三问完整详细材料](results/三问详细材料/第三问_完整详细材料.docx)：三情景 9237 分钟及各站资源配置，详见报告中的假设和限定范围。
- [第二题原模板填报草案](results/附件1_C_Solution1_实体证书草案.xlsx)：16、24架情景已完成0.1分钟网格重排与实体验证；30架情景存储原始精度、显示一位小数，显示值尚未完成重新排程与复验。
- 第三题原模板填报文件：[驰援表](results/问题3_迭代版/C_Solution2-1.xlsx)、[逐机保障表](results/问题3_迭代版/C_Solution2-2.xlsx)。

## 先看结果

- 第一题：[完整报告](results/q1_full_report.pdf)、[方案比较](results/第一题两份方案对比.md)。逐机排程与验证在 `results/h810itx_returns/round3/`。完整报告说明了伞勤、餐食的原题流程与保守排程之间的区别。
- 第二题：[阶段结果及改进候选](results/问题2阶段性结果.md)、[结果汇总](results/q2_improved_summary.json)。逐机候选及配对证书以 `results/q2_improved_` 开头。阶段报告保留了历史状态，填写最终附件请以最新结果和模板为准。
- 第三题：[专项报告](文档/新2026C%20第三问专项报告.docx)、[三情景结果](results/问题3专项/)、[低峰值补充方案](results/问题3_低峰值版/)。`按附录9重建` 的工作簿属于先前生成的结果，正式填报时应以 `附件模版/` 对应原模板为底稿。

`results/` 中也保留了服务器计算包、历史候选和日志。使用结果前请对照文件对应的假设、求解状态和验证记录。

## 运行环境

代码使用 Python 3。当前开发环境中的主要版本记录在 `requirements.txt`。安装示例：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\\Scripts\\activate
python -m pip install -r requirements.txt
```

部分绘图和 Word 报告生成脚本还调用本机安装的数学建模技能模板或字体；在其他机器运行时需要提供对应依赖。求解大规模实例需要较多内存和计算时间。

## 快速核对已有结果

在仓库根目录执行：

```bash
python 代码/问题一/验证第一问排程.py --flow fixed --aircraft 156 --horizon 120 --resources results/h810itx_returns/round3/fixed_resources.json results/h810itx_returns/round3/fixed.csv
python 代码/问题一/验证第一问排程.py --flow reordered --b-final --aircraft 156 --horizon 120 --resources results/h810itx_returns/round3/reordered_resources.json results/h810itx_returns/round3/reordered.csv
python 代码/问题二/验证问题2多技能候选.py results/q2_improved_b16_peoplefirst.json
```

第三题的 `代码/问题三/问题3_复核.py --output 结果目录 --excel` 会更新该目录里的 `复核结果.json`；复现入口为 `sh 代码/问题三/问题3_复现.sh`，默认会生成或覆盖相应结果，使用前请检查脚本参数。已有复现清单保留生成时的机器路径和哈希，目录整理后的脚本哈希可能变化。

## 团队协作

克隆仓库后，建议每人建立自己的分支，提交前先拉取最新变更，通过 Pull Request 合并。报告中的计算结论应保留来源排程与验证记录，修改模型或结果后同步更新报告。仓库整理前的原始版本可通过 Git 提交历史恢复。
