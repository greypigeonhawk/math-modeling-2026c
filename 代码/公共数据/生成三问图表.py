"""从已验证证书与逐批记录生成三题队内报告图。"""
from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[2]s[2]
OUT=ROOT/'results/三问详细材料/图表'
OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.sans-serif':['Noto Sans CJK SC','DejaVu Sans'], 'axes.unicode_minus':False,'font.size':10})


def q1():
    paths=[ROOT/'results/h810itx_returns/round3/fixed_resources.json',ROOT/'results/q1_reordered156_51vehicle_candidate_resources.json']
    ds=[json.loads(p.read_text()) for p in paths]
    cats=[f'Z{i}' for i in range(1,10)]
    x=np.arange(9); fig,ax=plt.subplots(figsize=(7,3))
    for j,(d,label,color) in enumerate(zip(ds,['固定流程','可调流程'],['#245575','#d09344'])):
        ax.bar(x+(j-.5)*.36,[d['vehicle_additions'][c] for c in cats],width=.36,label=label,color=color)
    ax.set(xticks=x,xticklabels=cats,ylabel='新增车辆（辆）'); ax.legend(frameon=False,ncol=2)
    ax.spines[['top','right']].set_visible(False);fig.tight_layout();fig.savefig(OUT/'q1_vehicles.png',dpi=200);plt.close(fig)


def q2():
    names=['q2_joint_repaired_b16','q2_sync_joint_b24','q2_joint_legacy_b30']
    ds=[json.loads((ROOT/'results'/f'{n}.json').read_text()) for n in names]
    labels=['32A+16B','32A+24B','32A+30B']; x=np.arange(3)
    fig,ax=plt.subplots(figsize=(6.5,3));
    for shift,key,label,color in [(-.18,'dispatch_people','人员（人）','#245575'),(.18,'dispatch_vehicles','车辆（辆）','#d09344')]:
        values=[sum(d[key].values()) for d in ds]; ax.bar(x+shift,values,.36,label=label,color=color)
        for xx,v in zip(x+shift,values):ax.text(xx,v+.4,str(v),ha='center')
    ax.set(xticks=x,xticklabels=labels,ylabel='N方派遣数量');ax.legend(frameon=False,ncol=2);ax.spines[['top','right']].set_visible(False);fig.tight_layout();fig.savefig(OUT/'q2_dispatch.png',dpi=200);plt.close(fig)


def q3():
    p=ROOT/'results/问题3_迭代版/场景1/批次与伞勤点.csv'
    with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))[:54]
    fig,ax=plt.subplots(figsize=(7,2.6));colors={'F2':'#cf8b40','F3':'#245575','F4':'#69a39e'}
    for r in rows:
        lane=r['停留跑道']; start=float(r['首机着陆']); ax.broken_barh([(start,7)],(int(lane[1:])-.33,.62),facecolors=colors[lane])
    ax.set(yticks=[2,3,4],yticklabels=['F2 乙','F3 丙','F4 丁'],xlabel='K后时间（分钟）');ax.spines[['top','right']].set_visible(False);fig.tight_layout();fig.savefig(OUT/'q3_runways.png',dpi=200);plt.close(fig)


if __name__=='__main__':q1();q2();q3()
