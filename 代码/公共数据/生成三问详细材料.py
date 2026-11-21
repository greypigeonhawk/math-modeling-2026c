"""从排程、复核证书与题面生成三份 Word 队内材料。"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[2]s[2]
SKILL = Path('/home/pigeon/.codex/skills/math-modeling')
sys.path.insert(0, str(SKILL/'tools/docx/scripts'))
import paper_format as pf

OUT = ROOT/'results/三问详细材料'
TEMPLATE = SKILL/'references/roles/论文手/references/论文模板.docx'
OUT.mkdir(parents=True,exist_ok=True)


def document(title, intro):
    doc=pf.new_document(template_path=TEMPLATE)
    pf.title(doc,title)
    pf.abstract_title(doc)
    pf.body(doc,intro)
    return doc


def heading(doc, text):
    p=pf.heading2(doc,text)
    p.paragraph_format.space_before=Pt(10)
    p.paragraph_format.space_after=Pt(4)
    p.paragraph_format.keep_with_next=True
    for run in p.runs: run.bold=True
    return p


def body(doc, paragraphs):
    for text in paragraphs:
        paragraph=pf.body(doc,text)
        paragraph.paragraph_format.keep_together=True


def eq(doc, expression):
    pf.equation(doc,expression)


def table(doc, title, rows):
    caption=pf.figure_caption(doc,title)
    caption.paragraph_format.keep_with_next=True
    tbl=pf.three_line_table(doc,[[str(value) for value in row] for row in rows])
    for row in tbl.rows[:-1]:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next=True


def fig(doc, file, caption):
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(OUT/'图表'/file),width=Cm(13.8))
    pf.figure_caption(doc,caption)


def save(doc,filename):
    doc.core_properties.author=''
    doc.save(OUT/filename)
    print(OUT/filename)


def q1():
    source=json.loads((ROOT/'results/q1_reordered156_51vehicle_candidate_resources.json').read_text())
    fixed=json.loads((ROOT/'results/h810itx_returns/round3/fixed_resources.json').read_text())
    vals=lambda d:[d['vehicle_additions'][f'Z{i}'] for i in range(1,10)]
    assert sum(vals(source))==51 and sum(source['people_additions'].values())==2
    doc=document('第一问  A型飞机首次飞行保障调度',
       '以M地勤原有资源为基础，分别分析100分钟保障量与120分钟保障156架所需增援。固定流程的48架排程达到加油车上界；可调流程已有52架可行排程。调整技能表后，固定流程已验证新增57辆车、5人，可调流程已验证新增51辆车、2人，增援最优性仍待证明。')
    pf.keywords(doc,'工序网络；批次调度；技能补位；资源增援')
    heading(doc,'一  问题分解与原始数据')
    body(doc,[
      '首次保障包含按需牵引、按需附油、电源A、空调A、加油、航材、伞勤、充氧、充氮、餐食、电源B和空调B。固定流程依题面图1的前置关系，可调流程按题面允许的工序调整规则处理，并保留B段在末端。',
      '按本报告主口径，牵引和附油数量各为任务总量的10%向上取整，交集为牵引数的20%向上取整。156架时分别为16架、16架及4架。航材按全机需求处理，每批最多20架，伞勤每点最多40架。',
      '原图将餐食和伞勤两条分支汇合于B段开始前。已有固定流程可行排程额外采用整批伞勤先于餐食的保守约束。以下推导会说明哪些下界使用了该附加约束。'])
    table(doc,'表1  M地勤原有车辆和人员库存',[
      ['资源','1','2','3','4','5','6','7','8','9'],
      ['Z类车辆','8','12','4','7','15','15','1','10','1'],
      ['M组人员','45','20','4','8','15','30','20','8','—']])
    table(doc,'表2  A型机主要作业时长及配置',[
      ['工序','车辆','人员','时长'],['牵引','Z1','M5 1人','10分钟'],['加油','Z2','M6 1人','15分钟'],
      ['充氧、充氮','Z3、Z4','每车M8 1人','各3分钟'],['电源、空调','Z5、Z6','每车M7 1人','各阶段15分钟'],
      ['附油','Z7','M2 1人','10分钟'],['餐食','Z8','M1 2人','8分钟'],['航材','Z9','M3 1人及M4 2人','10分钟/批'],['伞勤','Z9','M4 2人','6+0.5n分钟']])
    heading(doc,'二  工序与资源约束')
    body(doc,[
      '设每项任务的开始与结束时刻为s和c，车辆与人员占用覆盖整个服务区间。不同任务若使用同一实体资源，则占用区间不得重叠。配对作业中，Z5或Z6及一名操作员可在同步区间内服务两架。',
      '按用户明确口径，Z3和Z4每车每批最多同时服务10架，批内共享开始与结束时刻和一名合格操作员，作业结束后可周转。充氧与充氮各占相应车辆并共同占用充气人员。'])
    eq(doc,r'c_j=s_j+p_j')
    eq(doc,r'p_j=p_j^0/\eta_l,\quad \eta_l\in\{1,0.8,0.4\}')
    body(doc,['伞勤按题面固定熟练度1计算，n架的一批占用6+0.5n分钟；航材每批10分钟。第二技能、第三技能按0.8和0.4折算，实际个体不可同时承担冲突作业。'])
    heading(doc,'三  100分钟保障量')
    body(doc,[
      '固定流程的加油之后至少需要3分钟充气、8分钟餐食和15分钟B段，加油最迟于第74分钟结束。12辆Z2各最多完成四个15分钟任务，因此总量最多48架。',
      '将航材伞勤按20、20、8架分组，加油启动时刻安排在0、15、30、45分钟，保存的48架排程末架于99.25分钟完工。上界与可行解相等，48架为该口径下的最优值。',
      '可调流程保留B段末端约束。加油后至少留23分钟餐食和B段，每辆Z2至多做五次，得到60架上界。按20、20、12架分组的可行排程在第99分钟完成52架。52为已验证下界，不能写成已证明的最大值。'])
    eq(doc,r'N_{fixed}\le 12\times4=48')
    eq(doc,r'52\le N_{flex}\le 60')
    heading(doc,'四  156架任务的增援方案')
    body(doc,['原技能表下保留一份新增72辆、43人的可行基线。对已有可行排程进行双机配对和人员错峰调整，再把五项第三技能升为第二技能。表3列出对应流程的最新已验证增配，图1展示逐车型配置。'])
    table(doc,'表3  120分钟保障156架的方案',[
       ['方案','新增车辆','新增人员','求解状态'],['原技能表基线','72','43','可行'],
       ['调整技能  固定流程',sum(vals(fixed)),sum(fixed['people_additions'].values()),'可行'],
       ['调整技能  可调流程',sum(vals(source)),sum(source['people_additions'].values()),'可行']])
    fig(doc,'q1_vehicles.png','图1  两份156架可行排程的逐车型增援')
    rows=[['车型','固定流程（辆）','可调流程（辆）']]
    rows.extend([[f'Z{i}', fixed['vehicle_additions'][f'Z{i}'], source['vehicle_additions'][f'Z{i}']] for i in range(1,10)])
    rows.append(['M7新增人员',fixed['people_additions']['M7'],source['people_additions']['M7']])
    table(doc,'表4  增援数量与题面车型',rows)
    body(doc,['可调方案相对固定方案少增6辆车、少增3名M7人员。两份方案都依赖同一技能调整表，使用的初始分组及搜索范围存在限制。人车数量是独立验证的可行上界。'])
    heading(doc,'五  必要下界与技能调整')
    body(doc,[
      '156架时，按牵引配比至少需14辆Z1，较现有库存新增6辆。每辆Z2最多完成六项加油，至少需26辆，新增14辆。两阶段电源及空调按满载双机工时分别至少需20辆Z5和Z6，各新增5辆。固定流程再计附油、餐食与Z9的必要数量，得到总新增车辆至少38辆。可调流程对应下界为37辆。',
      '若进一步要求整批伞勤完成后才允许餐食，则Z8与Z9的联合工作窗还可把固定流程下界提高至39辆。该强化界不直接适用于题面原图的两条并行分支。',
      '建议将M1的加油、M3的电源空调、M5的餐食、M6的充气、M7的餐食由第三技能升为第二技能。每组第一技能保持不变，第二技能最多三项，总技能最多五项。'])
    source_table=json.loads((ROOT/'results/q1_source_tables.json').read_text())['multi_skill_table'][1:]
    labels={'M1':'餐食','M2':'附油','M3':'航材','M4':'伞勤','M5':'牵引','M6':'加油','M7':'电源空调','M8':'充气'}
    changes=dict(source['promoted_skills'])
    skills=[['组','第一技能','第二技能','第三技能']]
    for group,primary in labels.items():
        row=next(r for r in source_table if r[1].strip()==primary)
        second=row[2].strip().split('、');third=row[3].strip().split('、')
        if group in changes:
            third.remove(changes[group]);second.append(changes[group])
        skills.append([group,primary,'、'.join(second),'、'.join(third)])
    table(doc,'表5  调整后的完整技能表',skills)
    heading(doc,'六  验证与尚待研究的问题')
    body(doc,['保存排程逐机核对任务、起止时间、配对批次、技能资格、库存及牵引规则；51辆方案通过可调流程与B段末端双重检查。其Z1至Z9新增量依次为6、16、0、0、10、9、1、7、2，新增M7两人。需要继续收紧51辆可行上界与37辆必要下界之间的差距。',
      '核心材料：results/q1_reordered156_51vehicle_candidate.csv及同名资源JSON；固定基线位于results/h810itx_returns/round3/fixed.csv；100分钟排程位于peer_flow/fixed48_preset.csv和round3/reordered52.csv。'])
    save(doc,'第一问_完整详细材料.docx')


def q2():
    cases=[(16,'q2_joint_repaired_b16'),(24,'q2_sync_joint_b24'),(30,'q2_joint_legacy_b30')]
    ds=[json.loads((ROOT/'results'/f'{name}.json').read_text()) for _,name in cases]
    rates=[32.7777777778,0.2314814815,68.3396464646]
    doc=document('第二问  混合机队伴随保障与实体编组',
      '对32架A型机与三种B型机规模分别建立120分钟联合排程。以核验过的车人联合指派为依据，16、24、30架B型机情景分别派出8人7车、8人20车、26人26车。三组方案均为给定搜索范围内的可行候选，30架情景的负荷差异仍然较大。')
    pf.keywords(doc,'伴随保障；混合机队；双机共享；工作强度')
    heading(doc,'一  问题与作业口径')
    body(doc,['N地勤随B型机转场，进驻后纳入M地勤统一保障。三种机队分别包含32架A型机和16、24、30架B型机。各工序必须在120分钟内完成。题面未给地面转场耗时，按0时刻伴随力量可用计算。',
      '固定图1的主工序按前置关系组织。牵引与附油按总架数的10%向上取整，二者交集按牵引数量的20%向上取整。航材按全机需求，20架为一组；伞勤每批最多40架，批次结束后释放餐食。该伞勤先于餐食的关系是本模型采用的保守约束。'])
    heading(doc,'二  跨机型和跨技能效率')
    body(doc,['M地勤以A型机、N地勤以B型机为本场机型。另一来源人员服务异机型时系数为0.9。第一、第二、第三技能系数依次为1、0.8、0.4；两类折减按乘积应用，作业时间由基准工时除以相应系数得到。'])
    eq(doc,r'p_{i,o,g}=p_{i,o}^{0}/(\eta_{g,o}\rho_{i})')
    body(doc,['技能表按照第一技能名称匹配人员所属专业组，而非按题面表行号机械映射。曾使用旧映射得到的7人7车、8人16车和17人26车结果不作为本报告的实体编组结论。'])
    table(doc,'表1  工序对应车辆、第一技能及基准工时',[
      ['工序','车辆','第一技能组','A/B工时（分）'],['牵引','Z1','M5','10/10'],['加油','Z2','M6','15/30'],
      ['充氧、充氮','Z3、Z4','M8','3/3'],['电源、空调各阶段','Z5、Z6','M7','15/15'],
      ['附油','Z7','M2','10/10'],['餐食','Z8','M1 两人','8/25'],['航材','Z9','M3一人、M4两人','10/批'],['伞勤','Z9','M4两人','6+0.5n/批']])
    heading(doc,'三  车辆、人员与负荷建模')
    body(doc,['每项单车作业占完整车辆和操作员；电源、空调一车最多同时服务两架。聚合槽位模型用于寻找候选，随后以服务区间同时绑定车辆编号和人员编号。两架共享时，车辆和人员占用覆盖两项作业的并集，不能将两个来自不同车辆或人员组的空槽合并。',
      'N地勤派出人数与车辆数按小组和车型限制在库存内。约束同时检查技能资格、车辆容量、批次时序和120分钟期限。限时求解后固定任务时刻与人员组生成实体证书，证书中的车辆与人员编号支持重叠区间复算。'])
    eq(doc,r'r_g=L_g/(120y_g)')
    body(doc,['其中y为N方某组派出人数，L为该组人员实际忙碌人分钟。双机服务的同一操作员同时服务两架时，重叠部分只计一次。各派遣组平均利用率的最大值减最小值作为组间极差。'])
    heading(doc,'四  三种机队的可行实体方案')
    rows=[['B机数','人员','车辆','双机服务','极差（百分点）']]
    for (count,_),d,r in zip(cases,ds,rates):rows.append([count,sum(d['dispatch_people'].values()),sum(d['dispatch_vehicles'].values()),d['paired_services'],f'{r:.2f}'])
    table(doc,'表2  N方派遣与实体证书结果',rows)
    fig(doc,'q2_dispatch.png','图1  三种机队的N方人员与车辆派遣')
    for (n,_),d in zip(cases,ds):
      pp='、'.join(f'{k} {v}人' for k,v in d['dispatch_people'].items() if v)
      vv='、'.join(f'{k} {v}辆' for k,v in d['dispatch_vehicles'].items() if v)
      body(doc,[f'{n}架B型机：N方派出{pp}；车辆为{vv}。'])
    body(doc,['16架与30架情景分别有2次和4次不同阶段的电源或空调任务共用车人与同一服务区间；24架情景配对均为同阶段。若将不同阶段共享解释为不允许，16架和30架方案需要重新约束并求解。',
       '30架情景的组均极差约68.34个百分点，不应描述为人员负荷已经均衡。16、24、30架三组结果均是可行候选，各自的人车数量与负荷指标尚无全局最优证明。'])
    utilization=[['N方组','16架B','24架B','30架B']]
    for group in [f'M{i}' for i in range(1,9)]:
        row=[group]
        for d in ds:
            work=d['N_workload_minutes'].get(group,[])
            row.append(f'{100*sum(work)/(120*len(work)):.2f}%' if work else '—')
        utilization.append(row)
    table(doc,'表3  N方专业组平均实际利用率',utilization)
    body(doc,['表3中的分母为该组派遣人数乘以120分钟。零负荷人员仍计入对应组人数。该表展示组均值，个人之间的差别应继续参见实体证书。'])
    heading(doc,'五  附件填报与验证')
    body(doc,['三份底层排程和对应联合证书均通过独立实体验证，覆盖工序、人员车辆编号、库存及工作量。保留完整精度时刻的模板草案已生成，Excel按一位小数显示。由于显示四舍五入会缩短部分工序的表观时长，按题目一位小数精确落地的时刻表还需重新优化和逐项验证。',
      '附件草案中每架飞机的共享作业逐机列示，同一个实体服务可能显示在多行。车辆和人员不应按表格行数求和，应结合服务证书中的编号统计。三组证书分别为q2_joint_repaired_b16、q2_sync_joint_b24和q2_joint_legacy_b30。'])
    save(doc,'第二问_完整详细材料.docx')


def q3():
    data=json.loads((ROOT/'results/问题3_迭代版/复核结果.json').read_text())['scenarios']
    assert all(s['完工分钟']==9237 and s['完工差距分钟']==0 for s in data.values())
    doc=document('第三问  三种情景下的多跑道再次保障',
      '针对96架飞机连续45波次的再次保障，构造三种机场情景下的落地、跑道轮换、保障和休息安排。三情景均在K后9237分钟完成第45波次保障，与解析下界相等，且无需跨跑道驰援。')
    pf.keywords(doc,'多跑道调度；再次保障；休息窗口；解析下界')
    heading(doc,'一  场景和任务定义')
    body(doc,['每波96架，包括72架A型机与24架B型机，共12批，每批6架A和2架B。批内相邻落地至少1分钟，后批首机须晚于前批末机至少10分钟。每架飞机着陆后80分钟内完成保障，放飞后120分钟返抵机场上空，可等待下一次落地。',
      '三种场景依次为机场完好、甲跑道停机坪失去停留能力、乙跑道及乙地勤失能。每条跑道累计接收18批后停止接收，已接收飞机完成保障后驻场人员与车辆休息180分钟。K取首架飞机首次保障的第一道工序开始时刻。排程取首架飞机在K时刻落地并立即开工。'])
    heading(doc,'二  工序与资源模型')
    body(doc,['再次保障的牵引、加油、充氧、充氮、伞勤、餐食、电源和空调分别按题面工时与车人配置处理。伞勤和餐食在末端电源及空调开始之前完成；充氧和充氮在加油后执行。每批按10%向上取整牵引一架A型机。',
      '车辆与人员按半开区间计算并发峰值。停机位从飞机落地占用到保障完成并放飞。方案使用本场地勤，不进行跨跑道调动。'])
    eq(doc,r'c_{i,w}\le a_{i,w}+80')
    eq(doc,r'a_{i,w+1}\ge u_{i,w}+120')
    heading(doc,'三  完工时间下界')
    body(doc,['每批首末机至少相隔7分钟，后批首机距前批末机至少10分钟，因此相邻批次的首机至少相隔17分钟。共540批，若首批首机在K时落地，最后一批首机不早于K+539×17=K+9163分钟。',
      '最后一批两架B型机至少相隔1分钟，较晚者不早于K+9164分钟落地。B机加油30分钟、充气3分钟、餐食25分钟、末端电源或空调15分钟形成至少73分钟的串行关键路径。因此第45波保障完工不早于K+9237分钟。'])
    eq(doc,r'C_{45}\ge 539\times17+1+73=9237')
    heading(doc,'四  跑道轮转和排程结果')
    body(doc,['每54批构成一个周期。先将18批连续分配丙跑道，其余36批由另外两条跑道交替接收，每站各18批。周期循环10次，每个参与站接收180批。场景1、2使用乙、丙、丁；场景3使用甲、丙、丁。图1给出场景1首周期的批次起止。',
      '每批两架B型机先落地、六架A型机后落地。三场景的第45波最终保障均在K+9237分钟完成，等于上述共同下界。驰援次数与距离均为0，亦达到各自的非负下界。'])
    fig(doc,'q3_runways.png','图1  场景1首个54批周期的跑道分配')
    table(doc,'表1  三种机场情景的结果', [['情景','保障跑道','批次/站','完工分钟','驰援次数'],
      ['机场完好','乙、丙、丁','180','9237','0'],['甲停机坪失能','乙、丙、丁','180','9237','0'],['乙跑道及地勤失能','甲、丙、丁','180','9237','0']])
    heading(doc,'五  排程性能和配车下界')
    body(doc,['三种情景各复核540批、4320架次、30780条逐机工序及30个休息窗口。A机最长保障57分钟，B机最长保障73分钟。最短返回上空等待11分钟，休息后再次接收的最小余量86分钟。末架最后一次放飞后按120分钟飞行，于K+9357分钟返回上空。',
      '固定当前落地顺序和跑道轮转，丙站一个连续18批区段存在288分钟窗口，必要加油作业至少占2318车分钟，8辆车在窗口内最多提供2304车分钟，因此丙站至少9辆Z2。两条交替站分别至少5辆，现有排程对应9、5、5辆。该车辆最优性限定于既定轮转和批内顺序。',
      'A机最长57分钟在固定34分钟重复模板及所述资源限制下由CP-SAT证明最优；不能把这一结论扩展为全部跑道调度的全局最短保障时长。'])
    peaks=[['情景','跑道','批次数','Z2峰值','Z8峰值','M7峰值','Z9峰值']]
    for name,record in data.items():
        for runway,count in sorted(record['各站批次数'].items()):
            peak=record['车人峰值']
            peaks.append([name,runway,count,peak[f'{runway}/Z2'],peak[f'{runway}/Z8'],peak[f'{runway}/M7'],peak[f'{runway}/Z9']])
    table(doc,'表2  三种情景的逐站任务与资源峰值',peaks)
    body(doc,['表2中的Z2、Z8、Z9为车辆并发峰值，M7为人员并发峰值。资源峰值是实际排程的上界检查量，与队伍编配库存逐站对照。'])
    heading(doc,'六  敏感性与附件')
    body(doc,['场景2将甲停机坪容量置零，题面未给落地后转移至其他停机坪的机制。当前方案使用其他三站且达到时间下界。场景3不使用戊、己、庚跑道，因此无相关驰援调度。休息从第18批现有保障任务完成后开始，若要求落地后立即全员停工，需要重新建模。',
      '两份第三题工作簿由用户提供的原始模板回填。逐机表每个情景30780条，驰援表无数据行代表零调动。CSV另含落地、放飞、返航、休息及保伞点时间。'])
    save(doc,'第三问_完整详细材料.docx')


if __name__=='__main__': q1();q2();q3()
