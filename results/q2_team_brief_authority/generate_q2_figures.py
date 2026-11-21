from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Noto Sans CJK SC', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'figure.dpi': 160,
})

cases = [16,24,30]
js = [json.load(open(ROOT / f'results/q2_fair_b{b}.json')) for b in cases]
# 1) flow diagram
fig, ax = plt.subplots(figsize=(12,3.0))
ax.set_xlim(0,12); ax.set_ylim(0,3); ax.axis('off')
boxes=[(0.2,1.0,1.7,1.0,'N方随队进驻\nM/N资源合并'),(2.2,1.0,1.7,1.0,'牵引 / 附油\n部分飞机'),(4.2,1.0,1.7,1.0,'电源A、空调A\n加油、航材'),(6.2,1.0,1.7,1.0,'充氧 / 充氮\n3 min'),(8.2,1.0,1.7,1.0,'餐食 + 伞勤\nZ8 / Z9'),(10.2,1.0,1.5,1.0,'电源B、空调B\n120 min内')]
colors=['#12324a','#1c5d78','#2c7a7b','#4b9e8e','#d19a39','#b85c38']
for (x,y,w,h,txt),c in zip(boxes,colors):
    patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.04,rounding_size=0.08',fc=c,ec='white',lw=1.5)
    ax.add_patch(patch); ax.text(x+w/2,y+h/2,txt,ha='center',va='center',color='white',fontsize=10,weight='bold')
for a,b in zip(boxes[:-1],boxes[1:]):
    ax.add_patch(FancyArrowPatch((a[0]+a[2]+.06,1.5),(b[0]-.06,1.5),arrowstyle='-|>',mutation_scale=14,lw=1.4,color='#566573'))
ax.text(6,0.35,'模型保留：工序前置、人车容量、A/B跨机型0.9折减；当前候选只启用第一技能',ha='center',fontsize=9,color='#43515c')
fig.tight_layout(); fig.savefig(OUT/'flow.png',bbox_inches='tight'); plt.close(fig)

# 2) dispatched people/vehicles
fig, axes = plt.subplots(1,2,figsize=(11.0,3.8))
people_groups=['M1','M6','M7']; veh_groups=['Z2','Z3','Z5','Z6','Z8','Z9']
for ax,groups,key,title in [(axes[0],people_groups,'dispatch_people','N方派出人员（人）'),(axes[1],veh_groups,'dispatch_vehicles','N方派出车辆（辆）')]:
    x=np.arange(len(cases)); width=.22
    for j,g in enumerate(groups):
        vals=[d[key].get(g,0) for d in js]
        ax.bar(x+(j-(len(groups)-1)/2)*width,vals,width,label=g,color=['#287c8e','#d19a39','#b85c38','#758a9c','#4b9e8e','#8c6bb1'][j])
        for i,v in enumerate(vals):
            if v: ax.text(i+(j-(len(groups)-1)/2)*width,v+max(vals)*.03,str(v),ha='center',va='bottom',fontsize=8)
    ax.set_xticks(x,cases); ax.set_xlabel('B型机数量（架）'); ax.set_title(title,weight='bold'); ax.spines[['top','right']].set_visible(False); ax.grid(axis='y',alpha=.25); ax.legend(frameon=False,ncol=3,fontsize=8)
fig.tight_layout(); fig.savefig(OUT/'dispatch.png',bbox_inches='tight'); plt.close(fig)

# 3) utilization chart
fig, ax = plt.subplots(figsize=(9.5,4.1))
groups=['M1','M6','M7']; x=np.arange(len(cases)); width=.23
for j,g in enumerate(groups):
    vals=[d['group_utilization_thousandths'].get(g,0)/10 for d in js]
    ax.bar(x+(j-1)*width,vals,width,label=g,color=['#287c8e','#d19a39','#b85c38'][j])
    for i,v in enumerate(vals): ax.text(i+(j-1)*width,v+1,f'{v:.1f}%',ha='center',va='bottom',fontsize=8)
ax.set_xticks(x,cases); ax.set_xlabel('B型机数量（架）'); ax.set_ylabel('组平均利用率（%）'); ax.set_ylim(0,100); ax.set_title('均衡候选的组级利用率（FEASIBLE）',weight='bold'); ax.grid(axis='y',alpha=.25); ax.spines[['top','right']].set_visible(False); ax.legend(frameon=False,ncol=3)
fig.tight_layout(); fig.savefig(OUT/'utilization.png',bbox_inches='tight'); plt.close(fig)

# 4) sample gantt: first 4 aircraft b24, operations, origin colors
D=js[1]; ops=[o for o in D['operations'] if o['aircraft']<4]
order=['tow','oil','power_a','aircon_a','fuel','oxygen','nitrogen','meal','parachute','power_b','aircon_b']
labels=[]; rows=[]
for i in range(4):
    for op in order:
        matches=[o for o in ops if o['aircraft']==i and o['operation']==op]
        if matches:
            labels.append(f'A{i+1}·{op}'); rows.append(matches[0])
fig, ax=plt.subplots(figsize=(11,4.8)); y=np.arange(len(rows))
colors={'M':'#287c8e','N':'#d19a39'}
for yi,row in zip(y,rows):
    ax.barh(yi,row['end_min']-row['start_min'],left=row['start_min'],height=.65,color=colors.get(row['origin'],'#758a9c'),edgecolor='white')
ax.set_yticks(y,labels,fontsize=8); ax.invert_yaxis(); ax.set_xlim(0,120); ax.set_xlabel('时间（分钟）'); ax.set_title('B=24 候选排程片段（前4架A机）',weight='bold'); ax.grid(axis='x',alpha=.25); ax.spines[['top','right']].set_visible(False)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color='#287c8e',label='M方承担'),Patch(color='#d19a39',label='N方承担')],frameon=False,loc='lower right')
fig.tight_layout(); fig.savefig(OUT/'gantt_b24.png',bbox_inches='tight'); plt.close(fig)
