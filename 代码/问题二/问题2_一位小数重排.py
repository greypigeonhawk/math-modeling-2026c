"""固定已证实的车人编组，将作业重排到 0.1 分钟网格。"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import heapq
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from ortools.sat.python import cp_model
from 验证问题2实体证书 import verify

ROOT=Path(__file__).resolve().parents[2]
CASES={16:('q2_corrected_b16','q2_joint_repaired_b16'),24:('q2_sync_b24','q2_sync_joint_b24'),30:('q2_single_skill_b30_seed','q2_joint_legacy_b30')}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case',type=int,choices=CASES)
    ap.add_argument('--seconds',type=int,default=90)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--reassign',action='store_true',help='在原派遣规模内重分配实体编号')
    args=ap.parse_args()
    base,cert=CASES[args.case]
    source=ROOT/'results'/f'{base}.json'
    data=json.loads(source.read_text(encoding='utf-8'))
    certificate=json.loads((ROOT/'results'/f'{cert}.json').read_text(encoding='utf-8'))
    stock=json.loads((ROOT/'results/q23_normalized.json').read_bytes())['airport_resources']
    verify(source.read_bytes(),certificate,stock)
    model=cp_model.CpModel()
    tasks={}
    rows=data['operations']+data['batch_operations']
    for r in rows:
        i=r['aircraft'] if 'aircraft' in r else r['batch']
        key=(i,r['operation'])
        start=model.new_int_var(0,1200,f's_{key}'); end=model.new_int_var(0,1200,f'e_{key}')
        duration=math.ceil((r['end_min']-r['start_min'])*10-1e-7)
        model.add(end==start+duration)
        model.add_hint(start,round(r['start_min']*10)); model.add_hint(end,round(r['end_min']*10))
        tasks[key]=(start,end,r)
    aircraft=range(data['aircraft_a']+data['aircraft_b'])
    def precede(a,b):model.add(tasks[a][1]<=tasks[b][0])
    for i in aircraft:
        for gas in ('oxygen','nitrogen'):
            for pred in ('power_a','aircon_a','fuel','oil'):
                if (i,pred) in tasks: precede((i,pred),(i,gas))
            precede((i,gas),(i,'meal'))
        for final in ('power_b','aircon_b'):precede((i,'meal'),(i,final))
        if (i,'tow') in tasks:
            for pred in ('power_a','aircon_a','fuel','oil'):
                if (i,pred) in tasks:precede((i,'tow'),(i,pred))
            precede((i,'tow'),(20*(i//20),'material'))
        precede((20*(i//20),'material'),(i//40,'parachute'))
        precede((i//40,'parachute'),(i,'meal'))
    pools=defaultdict(list); services=[]
    for idx,service in enumerate(certificate['services']):
        keys=[tuple(item) for item in service['tasks']]
        ss=model.new_int_var(0,1200,f'service_s{idx}'); ee=model.new_int_var(0,1200,f'service_e{idx}')
        model.add_min_equality(ss,[tasks[key][0] for key in keys]);model.add_max_equality(ee,[tasks[key][1] for key in keys])
        size=model.new_int_var(1,1200,f'service_d{idx}');model.add(size==ee-ss)
        interval=model.new_interval_var(ss,size,ee,f'service{idx}')
        model.add_hint(ss,round(service['start_min']*10));model.add_hint(ee,round(service['end_min']*10))
        for name,items in [('vehicle',[service['vehicle']]),('person',service['people'])]:
            for item in items:
                key=(name,*item[:2]) if args.reassign else (name,*item)
                pools[key].append(interval)
        if len(keys)==2:
            model.add(tasks[keys[0]][0]+1<=tasks[keys[1]][1]);model.add(tasks[keys[1]][0]+1<=tasks[keys[0]][1])
            if tasks[keys[0]][2].get('mode')=='synchronous_pair':
                model.add(tasks[keys[0]][0]==tasks[keys[1]][0]);model.add(tasks[keys[0]][1]==tasks[keys[1]][1])
        services.append((ss,ee))
    for key,iv in pools.items():
        if args.reassign:
            kind,side,group=key
            category='vehicles' if kind=='vehicle' else 'people'
            capacity=stock['M'][category][group] if side=='M' else certificate['dispatch_'+category][group]
            model.add_cumulative(iv,[1]*len(iv),capacity)
        else:
            model.add_no_overlap(iv)
    model.add_min_equality(model.new_constant(0),[tasks[key][0] for key in tasks])
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=args.seconds;solver.parameters.num_search_workers=args.workers
    status=solver.solve(model);print('状态',solver.status_name(status),flush=True)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):raise SystemExit(2)
    for key,(start,end,row) in tasks.items():
        row['start_min']=solver.value(start)/10;row['end_min']=solver.value(end)/10
        if 'duration_min' in row:row['duration_min']=(solver.value(end)-solver.value(start))/10
    if args.reassign:
        requests=defaultdict(list)
        for index,(service,(start,end)) in enumerate(zip(certificate['services'],services)):
            for key,items in [('vehicle',[service['vehicle']]),('people',service['people'])]:
                counts=Counter(tuple(item[:2]) for item in items)
                for (side,group),demand in counts.items():
                    requests[(key,side,group)].append((solver.value(start),solver.value(end),index,demand))
        for (kind,side,group),jobs in requests.items():
            category='vehicles' if kind=='vehicle' else 'people'
            capacity=stock['M'][category][group] if side=='M' else certificate['dispatch_'+category][group]
            available=list(range(1,capacity+1));heapq.heapify(available); occupied=[]
            for start,end,index,demand in sorted(jobs):
                while occupied and occupied[0][0]<=start:
                    _,number=heapq.heappop(occupied);heapq.heappush(available,number)
                selected=[heapq.heappop(available) for _ in range(demand)]
                service=certificate['services'][index]
                if kind=='vehicle':service['vehicle']=[side,group,selected[0]]
                else:
                    service['people']=[x for x in service['people'] if tuple(x[:2])!=(side,group)]
                    service['people'].extend([[side,group,number] for number in selected])
                for number in selected:heapq.heappush(occupied,(end,number))
    actual={g:[0.0]*n for g,n in certificate['dispatch_people'].items() if n}
    for service,(start,end) in zip(certificate['services'],services):
        service['start_min']=solver.value(start)/10;service['end_min']=solver.value(end)/10
        for side,group,index in service['people']:
            if side=='N': actual[group][index-1]+=service['end_min']-service['start_min']
    certificate['N_workload_minutes']=actual
    dest=ROOT/'results'/f'q2_tenth_b{args.case}.json'
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raw=dest.read_bytes();certificate['schedule_sha256']=hashlib.sha256(raw).hexdigest()
    outfile=ROOT/'results'/f'q2_tenth_joint_b{args.case}.json'
    outfile.write_text(json.dumps(certificate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(verify(raw,certificate,stock),ensure_ascii=False))

if __name__=='__main__':main()
