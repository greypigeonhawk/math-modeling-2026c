"""根据已核验的第三问结果构建独立 Word 专项报告。"""

import json
import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from docx.shared import Cm, Pt

from 问题3_复核 import DEFAULT_OUTPUT, ROOT, read_rows, source_limits

DEFAULT_FIGURES = ROOT / "figures/问题3专项"
SKILL = Path.home() / ".codex/skills/math-modeling"
sys.path.insert(0, str(SKILL / "tools/docx/scripts"))
import paper_format as pf

TEMPLATE = SKILL / "references/roles/论文手/references/论文模板.docx"
FILENAME = "新2026C 第三问专项报告.docx"


def main():
    summary = json.loads((DEFAULT_OUTPUT / "复核结果.json").read_text(encoding="utf-8"))
    cases = summary["scenarios"]
    standard = cases["场景1"]
    _, stock = source_limits()
    doc = pf.new_document(template_path=TEMPLATE)
    doc.core_properties.title = "新2026C 第三问 多跑道再次飞行保障排程"
    doc.core_properties.subject = "三种机场状态下的45波次排程与最优性证明"
    doc.core_properties.author = ""
    section = doc.sections[0]
    grid = section._sectPr.find(qn("w:docGrid"))
    if grid is not None:
        section._sectPr.remove(grid)
    page_number = section.footer.paragraphs[0]
    page_number.clear()
    page_number.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    page_number._p.append(field)

    def paragraph(text):
        p = pf.body(doc, text)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = Pt(17)
        return p

    def heading(text, new_page=False):
        p = pf.heading3(doc, text)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.page_break_before = new_page
        return p

    def equation(latex):
        pf.equation(doc, latex)

    def figure(number, name, title, width=14.3):
        p = pf.image(doc, DEFAULT_FIGURES / f"{name}.png", width_cm=width)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_with_next = True
        caption = pf.figure_caption(doc, f"图{number}  {title}")
        caption.paragraph_format.space_after = Pt(7)

    def table(number, label, rows, formulas=None):
        caption = pf.figure_caption(doc, f"表{number}  {label}")
        caption.paragraph_format.keep_with_next = True
        if number == 3:
            caption.paragraph_format.page_break_before = True
        t = pf.three_line_table(doc, rows)
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.space_before = Pt(2)
                    p.paragraph_format.line_spacing = Pt(13)
                    for run in p.runs:
                        run.font.size = Pt(10)
        if number == 1:
            t.autofit = False
            for col, width in zip(t.columns, (3.7, 2.6, 2.1, 3.4, 2.75)):
                col.width = Cm(width)
                for cell in col.cells:
                    cell.width = Cm(width)
        if formulas:
            for index, formula in enumerate(formulas, 1):
                p = t.cell(index, 0).paragraphs[0]
                p.clear()
                p._p.append(etree.fromstring(pf._latex2omml(formula)))
        return t

    pf.title(doc, "新2026C 第三问 多跑道再次飞行保障排程")
    pf.abstract_title(doc)
    paragraph("96架飞机分12批循环执行45波次。机场完好、甲跑道停机坪停用、乙跑道及其地勤失能三种情景都需要满足同一批次落地间隔、单机80分钟保障上限、120分钟飞行、分类停机容量和驻场休息要求。")
    paragraph("由批次最小首机间距和B型机关键路径推导完工下界。排程每批先接收两架B型机，随后接收六架A型机。以54批为一个周期分配给三条具有本场地勤的跑道，将各站停收和休息窗嵌入其他跑道仍可接收的时段。")
    paragraph(f"三种情景均在K后{standard['完工分钟']:,.0f}分钟完成第45波次保障，达到解析下界，跨跑道驰援次数和距离均为零。机场完好和甲停机坪停用时使用乙、丙、丁跑道，乙跑道与地勤失能时使用甲、丙、丁跑道。各参与跑道接收180批。")
    paragraph(f"每个情景逐条核验{standard['保障架次']:,}架次、{standard['逐机工序记录']:,}条逐机作业和{standard['休息次数']}个休息窗。单机最长保障{standard['最长保障']:.0f}分钟，返抵上空到下一次落地的等待为{standard['最短上空等待']:.0f}至{standard['最长上空等待']:.0f}分钟。若计入第45次放飞后的最后一段120分钟飞行，末架在K后{standard['末架飞行返回上空分钟']:,.0f}分钟返回机场上空。")
    pf.keywords(doc, "离散事件调度、关键路径、跑道分配、模块化飞行保障")

    heading("一  三种情景的最优方案")
    paragraph("以第45波次全部飞机再次保障完工时刻为首要目标。在相同完工时刻下依次最小化跨跑道驰援次数和总距离。题面的机场状态和停机能力均按附录7处理。场景2将甲停机坪容量置零，保留甲地勤的可用性。场景3同时移除乙跑道和乙地勤。结论见表1，求解与核验过程见图1。")
    result_rows = [["情景", "接收跑道", "每站批数", "K后完工（分钟）", "驰援（次）"]]
    runway_names = {"F1": "甲", "F2": "乙", "F3": "丙", "F4": "丁"}
    for info in cases.values():
        result_rows.append([info["场景"], "、".join(runway_names[r] for r in info["各站批次数"]),
                            str(next(iter(info["各站批次数"].values()))),
                            f"{info['完工分钟']:,.0f}", str(info["跨跑道调动"])])
    table(1, "三种机场状态下的完工时刻与驰援方案", result_rows)
    old_three = json.loads((ROOT / "results/q3_three_45waves.json").read_text(encoding="utf-8"))
    old_time = old_three["makespan_min"]
    paragraph(f"既有丙、丁、己三跑道候选采用单站逐批串行并由甲地勤赴己，记录完工时刻为K后{old_time:,.0f}分钟。本方案允许同跑道不同批次的工序在资源限额内重叠，完工提前{old_time-standard['完工分钟']:,.0f}分钟。")

    heading("二  题面数据与时序口径", new_page=True)
    paragraph("工序、车人资源、跑道容量与填报代码来自《新2026C》第三问及附录[1]。图1给出下界推导与构造验证的关系。图2给出七条跑道的分机型容量，图3给出四支地勤的车型库存。人员按附录7表7的各专业组人数核对。计算符号见表2。")
    figure(1, "flow_overall_model", "第三问的求解与验证流程", width=13.8)
    table(2, "符号与单位", [
        ["符号", "含义", "单位"],
        ["", "第 b 批首机的着陆时刻", "分钟"],
        ["", "第 w 波第 q 批内第 j 架飞机的着陆时刻", "分钟"],
        ["", "飞机 i 在第 w 波次的再次保障完工时刻", "分钟"],
        ["", "飞机 i 在第 w 波次的放飞时刻", "分钟"],
        ["", "第45波次全部飞机再次保障完工时刻", "分钟"],
        ["", "跑道 r 可同时停留的 k 型飞机数", "架"],
    ], [r"T_b", r"t_{w,q,j}", r"c_{i,w}", r"u_{i,w}", r"C_{45}", r"C_{r,k}"])
    figure(2, "raw_q3_parking", "各跑道的A型与B型飞机停机容量", width=13.2)
    figure(3, "raw_q3_vehicles", "各主要跑道地勤的各型车辆库存", width=13.2)

    heading("三  约束与完工下界")
    paragraph("首架飞机落地立即开始加油，着陆和首道工序的开始同为K时刻。每架飞机从落地起占用停机位，末道工序完成即放飞。起飞120分钟后飞机返回上空，可以等待既定批次的落地时刻。单机完工和相邻波次落地满足以下条件，式中的落地时刻按飞机编号在相应波次取值。")
    equation(r"c_{i,w}\leq t_{i,w}^{\mathrm{land}}+80,\qquad u_{i,w}=c_{i,w}")
    equation(r"t_{i,w+1}^{\mathrm{land}}\geq u_{i,w}+120")
    paragraph("同批相邻两架至少相隔1分钟，故同批首末机至少相隔7分钟。依照附录1的定义，后批首机至少晚于前批末机10分钟。由此，540批中第540批首机最早在K后9,163分钟落地。")
    equation(r"T_{b+1}-T_b\geq7+10=17,\qquad T_{540}\geq539\times17=9163")
    paragraph("最后一批两架B型机的着陆时刻至少相差1分钟，较晚的一架至少在K后9,164分钟落地。再保障图的加油、任一充气工序、餐食及任一末端工序形成一条串行路径。采用题面给出的最快技能，B型机这条路径仍至少耗时73分钟。")
    equation(r"p_{\mathrm B}=30+3+25+15=73")
    equation(r"C_{45}\geq T_{540}+1+p_{\mathrm B}\geq9237")
    paragraph("该下界允许跑道、地勤、落地顺序和资源编组任意选择，只使用共同的着陆间隔、K时刻和工序先后约束。只要存在9,237分钟完工的合规方案，完工时间即达到最优。驰援次数及距离的下界均为零。")

    heading("四  批次分配与逐机工序", new_page=True)
    paragraph("前54批的分配见图4。全机场每17分钟接收一个批次，周期开始的18批连续安排在丙跑道。其余36批在另两条跑道交替落地，各18批。场景1与2的这两站为乙和丁，场景3将乙替换为甲。循环执行10次即可覆盖540批。每波同一飞机的批次和批内位置固定，因此相邻波的着陆间距均为204分钟。")
    figure(4, "process_q3_cycle", "场景1与2的54批周期分配")
    paragraph("每批两架B型机在相对时刻0、1落地，六架A型机在相对时刻2至7落地。首架A型机牵引10分钟，其余飞机落地即加油。各机加油后并行充氧与充氮。每批在相对时刻12至18开设保伞点，随后按落地顺序每架用0.5分钟发伞，在相对时刻22完成。车辆和两名送伞员从开点至末机发伞结束连续占用。")
    paragraph("首批的工序关系见图5，表3列出相对于批首机落地的作业区间。题面图2要求伞勤和餐食在电源与空调之前都已完成。本方案让各机在两项充气作业结束且整批发伞完成后开始餐食。每架飞机的电源和空调并行开工，分别占一辆车及一名电源空调专业人员。")
    figure(5, "process_q3_batch", "首批逐机工序甘特图", width=13.3)
    tasks = [row for row in read_rows(DEFAULT_OUTPUT / "场景1", "逐机工序")
             if row["波次"] == row["批次"] == "1"]
    task_index = {(int(row["飞机编号"]), row["再次出动保障工序"]): row for row in tasks}
    fields = ["0102", "0204", "0405", "0203", "0708", "0809"]
    template = [["机型编号", "牵引", "加油", "双充气", "发伞", "餐食", "电源和空调"]]
    for plane in (73, 74, 1, 2, 3, 4, 5, 6):
        cells = [f"{'B' if plane >= 73 else 'A'}-{plane:02d}"]
        for code in fields:
            row = task_index.get((plane, code))
            cells.append("—" if row is None else
                         f"{float(row['工序开始时刻']):g}–{float(row['工序结束时刻']):g}")
        template.append(cells)
    table(3, "首批逐机工序相对时刻（分钟）", template)

    heading("五  休息窗与在途时间")
    paragraph("各跑道接收本轮第18批末架后即停止接收新飞机。已在场飞机保障结束后，当前驻场人员与车辆原地休息180分钟。首个周期的关闭和休息窗口见图6及表4。每条接收跑道完成180批，记录10次休息，其中最后一次之后没有新批次。三种情景每条有后续批次的休息窗均在重新接收之前结束，最小余量为86分钟。")
    figure(6, "process_q3_rest", "场景1与2首轮停止接收和地勤休息窗口", width=12.1)
    rest_data = [["跑道", "停止接收", "开始休息", "结束休息"]]
    for row in read_rows(DEFAULT_OUTPUT / "场景1", "跑道休息")[:3]:
        rest_data.append([row[key] for key in ("停留跑道", "停止接收时刻", "休息开始", "休息结束")])
    table(4, "首个周期休息安排（K后分钟）", rest_data)
    paragraph("同一架飞机再次落地前的可用时间为204分钟。B型机保障73分钟，加上飞行120分钟，最少等待11分钟。A型机的地面保障用时为41至51分钟，相应等待为33至43分钟。图7展示三种情景共同的保障时长分布。全部飞机距80分钟限制至少有7分钟余量。")
    figure(7, "result_q3_ground", "每个情景的逐机地面保障时长分布", width=12.1)

    heading("六  停机容量与车人占用")
    paragraph("事件扫描按每架飞机从着陆到放飞的半开区间累计在场量。图8显示各站停机峰值和题面容量。丙跑道收批最密，A型机和B型机峰值分别为18架和10架，且合计瞬时峰值为26架。乙和丁跑道A型机峰值恰好达到12架的容量。")
    figure(8, "result_q3_parking", "三种情景所用跑道的停机峰值与容量")
    paragraph("车辆按作业区间累计，每项工序使用对应专业组的第一技能人员。充氧和充氮共用充气组的人员额度，电源和空调共用电源空调组人员额度，餐食占一辆车与两名人员。各车型和专业组的最高库存占比见图9，几项并发约束见表5。Z2加油车在丙、丁跑道达到本场库存，参加保障的三个跑道各使用一辆Z9开设保伞点。")
    figure(9, "result_q3_load", "三种情景中各车辆与专业组的最大并发库存占比")
    resource_rows = [["跑道", "停机峰值 A/B", "Z2 峰值/库存", "Z8 峰值/库存", "M7 峰值/库存"]]
    for lane in ("F1", "F2", "F3", "F4"):
        source_case = cases["场景3"] if lane == "F1" else standard
        p = source_case["停机峰值"]
        u = source_case["车人峰值"]
        resource_rows.append([lane, f"{p[lane+'/A']}/{p[lane+'/B']}",
                              *[f"{u[lane+'/'+key]}/{stock[lane][key]}" for key in ("Z2", "Z8", "M7")]])
    table(5, "实际停机量与关键车人并发", resource_rows)

    heading("七  适用条件与结果附件", new_page=True)
    paragraph("上述结论采用逐批向上取整，每批牵引一架A型机。由题面最快工时可知，若牵引B型机，其牵引、加油、充气、餐食和电源关键路径为83分钟，会超过80分钟时限。电源和空调按逐机配车，因而仍满足题面允许每车最多同时保障两架的上限。")
    paragraph("Z3、Z4按跑道在场待保障队列确定配给下限，各自至少达到队列规模除以10向上取整。丙站合计在场峰值26架，要求至少各配3辆，库存各4辆，逐车工序并发峰值各3辆。若采用每批充氧和充氮分别仅能并发使用一辆车的解释，须重新校验该排程。")
    paragraph("题面给出的是返抵机场上空的时间，排程利用了返回上空后等待落地的余量。若要求返抵即落地，需重新求解。休息主口径允许先完成已接收飞机的保障。若要求第18批末机刚落地就由现有地勤全部停工180分钟，在没有接班力量时，末机无法在80分钟内完成保障。若整个任务每条跑道只需触发一次休息，本文排程仍然可行。")
    paragraph("场景2中甲跑道停机坪容量为零，题面未给出落地后转运至其他停机坪的机制。该方案在乙、丙、丁跑道达到下界，甲地勤保有支援能力且无需调动。场景3未使用戊、己、庚跑道，因此也无需触发戊、庚的替代驰援顺序。")
    paragraph("对应 C_Solution2-1 和 C_Solution2-2 的工作簿依据附录9表11与表12重建，分别记录驰援和逐机编组。每份含三个情景工作表。驰援表只有列标题，表示零调动。逐机工序表每景30,780行，时刻以K为0，保留一位小数。随附CSV另列着陆、完工、放飞、返抵上空、跑道休息和保伞点开设，供追溯所有时间与占用。赛方原始工作簿未随题目文件取得。")
    heading("参考文献")
    paragraph("[1] 《新2026C》题目文件。第三问，附录1第6条，附录2图2，附录3至9。")

    out = pf.save_document(doc, ROOT, filename=FILENAME, overwrite=True)
    print(out)


if __name__ == "__main__":
    main()
