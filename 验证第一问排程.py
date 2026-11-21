"""独立复核问题1导出排程：任务时长/流程/技能/人员车辆容量。"""
from __future__ import annotations
import argparse, csv, json, math
from collections import defaultdict
from pathlib import Path
from 问题1_优化模型 import GAS_BATCH_CAPACITY, PEOPLE, VEHICLES, SKILL_GROUP, ceil_div

ROOT=Path(__file__).resolve().parent
TASK_BASE={'tow':10,'power_a':15,'aircon_a':15,'oil':10,'fuel':15,'oxygen':3,'nitrogen':3,'meal':8,'power_b':15,'aircon_b':15}
VEH_OF={'tow':'Z1','power_a':'Z5','aircon_a':'Z6','oil':'Z7','fuel':'Z2','oxygen':'Z3','nitrogen':'Z4','meal':'Z8','power_b':'Z5','aircon_b':'Z6'}

def check(path: Path, reordered: bool, n: int, horizon: int, resource_path: Path|None, *, b_final: bool = False, parachute_sizes: list[int] | None = None):
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    additions=json.loads(resource_path.read_text(encoding='utf-8')) if resource_path else {}
    vadd=additions.get('vehicle_additions',{}); padd=additions.get('people_additions',{})
    vcap={k:v+int(vadd.get(k,0)) for k,v in VEHICLES.items()}
    pcap={k:v+int(padd.get(k,0)) for k,v in PEOPLE.items()}
    promoted={tuple(x) for x in additions.get('promoted_skills',[])}
    aircraft=defaultdict(dict); other=[]
    for r in rows:
        if r['aircraft'].isdigit():
            aid=int(r['aircraft']); op=r['operation']
            if op in aircraft[aid]: raise ValueError(f'duplicate aircraft operation: {aid}/{op}')
            aircraft[aid][op]=r
        else: other.append(r)
    errors=[]
    if sorted(aircraft)!=list(range(n)): errors.append(f'aircraft ids/count mismatch: {len(aircraft)}')
    source=json.loads((ROOT/'results/q1_source_tables.json').read_text(encoding='utf-8'))
    eligibility={}
    for row in source['multi_skill_table'][1:]:
        primary,second,third=(row[i].strip() for i in (1,2,3)); group=SKILL_GROUP[primary]
        eligibility[(group,primary)]=1
        for skill in filter(None,second.split('、')): eligibility[(group,skill)]=2
        for skill in filter(None,third.split('、')): eligibility[(group,skill)]=2 if (group,skill) in promoted else 3
    for i,ops in aircraft.items():
        for op,base in TASK_BASE.items():
            if op not in ops:
                if op in {'tow','oil'}: continue
                errors.append(f'aircraft {i}: missing {op}'); continue
            r=ops[op]; st,en=float(r['start_min']),float(r['end_min'])
            level=int(r['skill_level']); group=r['operator_group']; skill=r['skill']
            prof=1 if skill=='伞勤' or level==1 else (.8 if level==2 else .4)
            if abs((en-st)-base/prof)>.251: errors.append(f'aircraft {i} {op}: duration mismatch')
            if eligibility.get((group,skill))!=level: errors.append(f'aircraft {i} {op}: ineligible {group}/{skill}/{level}')
        if max(float(r['end_min']) for r in ops.values())>horizon+1e-8: errors.append(f'aircraft {i}: beyond horizon')
        edges=([('tow','power_a'),('tow','aircon_a'),('tow','oil'),('tow','fuel'),
                ('power_a','oxygen'),('aircon_a','oxygen'),('power_a','nitrogen'),('aircon_a','nitrogen'),
                ('fuel','oxygen'),('fuel','nitrogen'),('oil','oxygen'),('oil','nitrogen'),
                ('oxygen','meal'),('nitrogen','meal'),('power_a','meal'),('aircon_a','meal'),('meal','power_b'),('meal','aircon_b')]
               if not reordered else
               [('tow','power_a'),('tow','aircon_a'),('tow','oil'),('tow','fuel'),
                ('tow','oxygen'),('tow','nitrogen'),('fuel','meal'),
                ('oxygen','meal'),('nitrogen','meal'),('meal','power_b'),('meal','aircon_b')])
        if reordered and b_final:
            edges += [(a, b) for a in ("power_a", "aircon_a", "oil")
                      for b in ("power_b", "aircon_b")]
        for pred,succ in edges:
            if pred in ops and succ in ops and float(ops[succ]['start_min'])+1e-8<float(ops[pred]['end_min']): errors.append(f'aircraft {i}: {pred}->{succ}')
        # Explicit source incompatibilities remain in force even when order is adjustable.
        for gas in (('oxygen',) if reordered else ('oxygen','nitrogen')):
            for other_op in ('fuel','power_a','power_b'):
                if gas in ops and other_op in ops:
                    a,b=ops[gas],ops[other_op]
                    if max(float(a['start_min']),float(b['start_min'])) < min(float(a['end_min']),float(b['end_min']))-1e-8:
                        errors.append(f'aircraft {i}: incompatible overlap {gas}/{other_op}')
        for power in ('power_a','power_b'):
            if power in ops and 'meal' in ops:
                a,b=ops[power],ops['meal']
                if max(float(a['start_min']),float(b['start_min'])) < min(float(a['end_min']),float(b['end_min']))-1e-8:
                    errors.append(f'aircraft {i}: incompatible overlap {power}/meal')
    tow_ids={i for i,o in aircraft.items() if 'tow' in o}; oil_ids={i for i,o in aircraft.items() if 'oil' in o}
    both=len(tow_ids & oil_ids)
    if not (10*len(tow_ids)>=n and 10*len(tow_ids)<=n+9): errors.append(f'tow count={len(tow_ids)}, expected ceil rule')
    if not (10*len(oil_ids)>=n and 10*len(oil_ids)<=n+9): errors.append(f'oil count={len(oil_ids)}, expected ceil rule')
    if not (5*both>=len(tow_ids) and 5*both<=len(tow_ids)+4): errors.append(f'tow/oil intersection={both}, tow={len(tow_ids)}')
    z1=ceil_div(len(tow_ids),2) if len(tow_ids)<=4 else (ceil_div(2*len(tow_ids),3) if len(tow_ids)<=8 else ceil_div(5*len(tow_ids),6))
    if vcap['Z1']<z1: errors.append(f'Z1 rule requires {z1}, available {vcap["Z1"]}')
    if sum(r['aircraft']=='material' for r in rows)!=ceil_div(n,20): errors.append('material batch count mismatch')
    sizes = parachute_sizes or [min(40, n-i) for i in range(0, n, 40)]
    if sum(sizes) != n or any(not 1 <= size <= 40 for size in sizes):
        raise ValueError("伞勤分组须覆盖全体飞机，且每组1至40架")
    if sum(r['aircraft']=='parachute' for r in rows) != len(sizes):
        errors.append('parachute batch count mismatch')
    groups = {}
    cursor = 0
    for batch, size in enumerate(sizes):
        groups[batch] = range(cursor, cursor + size)
        cursor += size
    material={int(r['operation']):r for r in rows if r['aircraft']=='material'}
    parachute={int(r['operation']):r for r in rows if r['aircraft']=='parachute'}
    for b,r in material.items():
        if abs((float(r['end_min'])-float(r['start_min']))-10)>1e-8: errors.append(f'material batch {b}: duration')
        for i in range(b*20,min((b+1)*20,n)):
            if i in tow_ids and float(r['start_min'])+1e-8<float(aircraft[i]['tow']['end_min']): errors.append(f'material batch {b}: before tow {i}')
    for b,r in parachute.items():
        group, level = r["operator_group"], r["skill_level"]
        if r["skill"] != "伞勤" or level not in {"1", "2", "3"} or eligibility.get((group, "伞勤")) != int(level):
            errors.append(f"parachute batch {b}: ineligible {group}/{level}")
        members=groups[b]; expected_duration=6+.5*len(members)
        if abs((float(r['end_min'])-float(r['start_min']))-expected_duration)>1e-8: errors.append(f'parachute batch {b}: duration')
        for i in members:
            if float(r['start_min'])+1e-8<float(material[i//20]['end_min']): errors.append(f'parachute batch {b}: before material {i}')
            if not reordered and float(aircraft[i]['meal']['start_min'])+1e-8<float(r['end_min']): errors.append(f'aircraft {i}: meal before parachute')
            if reordered and b_final:
                for op in ("power_b", "aircon_b"):
                    if float(aircraft[i][op]["start_min"]) + 1e-8 < float(r["end_min"]):
                        errors.append(f"aircraft {i}: {op} before parachute")
    # Verify each paired electrical interval is represented by exactly two matching rows.
    paired=defaultdict(list)
    for i,ops in aircraft.items():
        for op in ('power_a','aircon_a','power_b','aircon_b'):
            r=ops[op]
            if r.get('vehicle_mode')=='paired': paired[(op,r.get('vehicle_pair',''))].append((i,r))
            elif r.get('vehicle_mode')!='single': errors.append(f'aircraft {i} {op}: missing vehicle mode')
    for (op,pair),items in paired.items():
        expected_ids=[int(x) for x in pair.split('-') if x]
        if len(items)!=2 or sorted(i for i,_ in items)!=expected_ids: errors.append(f'{op} pair {pair}: member mismatch')
        if len(items)==2:
            a,b=items[0][1],items[1][1]
            for field in ('start_min','end_min','operator_group','skill','skill_level'):
                if a[field]!=b[field]: errors.append(f'{op} pair {pair}: {field} mismatch')
    gas_batches=defaultdict(list)
    for i,ops in aircraft.items():
        for op in ('oxygen','nitrogen'):
            r=ops.get(op,{})
            if r.get('vehicle_mode')!='batch' or not r.get('vehicle_pair'):
                errors.append(f'aircraft {i} {op}: missing integer gas batch assignment')
            else:
                gas_batches[(op,r['vehicle_pair'])].append(r)
    ve=defaultdict(list); pe=defaultdict(list); pair_seen=set()
    for (op,batch_id),members in gas_batches.items():
        if not (1 <= len(members) <= GAS_BATCH_CAPACITY):
            errors.append(f'{op} batch {batch_id}: size {len(members)} outside 1..{GAS_BATCH_CAPACITY}')
        for field in ('start_min','end_min','operator_group','skill','skill_level'):
            if len({r[field] for r in members})!=1: errors.append(f'{op} batch {batch_id}: inconsistent {field}')
        st,en=float(members[0]['start_min']),float(members[0]['end_min'])
        vehicle=VEH_OF[op]; group=members[0]['operator_group']
        ve[vehicle]+=[(st,1),(en,-1)]
        pe[group]+=[(st,2),(en,-2)]
    for r in rows:
        st,en=float(r['start_min']),float(r['end_min']); op=r['operation']; a=r['aircraft']
        if a.isdigit() and op in VEH_OF:
            if op in {'oxygen','nitrogen'}: continue
            v=VEH_OF[op]; paired=r.get('vehicle_mode')=='paired'; key=(op,r.get('vehicle_pair',''),st,en)
            if paired and key in pair_seen: continue
            if paired: pair_seen.add(key)
            ve[v]+=[(st,1),(en,-1)]
            g=r['operator_group']; demand=2*(2 if op=='meal' else 1)
            pe[g]+=[(st,demand),(en,-demand)]
        elif a=='material':
            ve['Z9'] += [(st,1),(en,-1)]; pe['M3'] += [(st,2),(en,-2)]; pe['M4'] += [(st,4),(en,-4)]
        elif a=='parachute':
            ve['Z9'] += [(st,1),(en,-1)]; pe[r['operator_group']] += [(st,4),(en,-4)]
    peaks={}
    for pools,capacity,label in ((ve,vcap,'vehicle'),(pe,{k:v*2 for k,v in pcap.items()},'staff')):
        for name,events in pools.items():
            load=peak=0
            for t,d in sorted(events,key=lambda x:(x[0],x[1])): load+=d; peak=max(peak,load)
            peaks[f'{label}_{name}']=peak
            if peak>capacity[name]: errors.append(f'{label} {name}: peak {peak}>{capacity[name]}')
    return {'file':path.name,'flow':'reordered' if reordered else 'fixed','aircraft':len(aircraft),
            'horizon_minutes':horizon,'status':'PASS' if not errors else 'FAIL','errors':errors,
            'tow_count':len(tow_ids),'oil_count':len(oil_ids),'intersection_count':both,
            'vehicle_additions':vadd,'people_additions':padd,'resource_peaks':peaks}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--aircraft',type=int,default=40); ap.add_argument('--horizon',type=int,default=100)
    ap.add_argument('--flow',choices=('fixed','reordered'),required=True)
    ap.add_argument('--parachute-sizes', type=int, nargs='+')
    ap.add_argument('--b-final', action='store_true')
    ap.add_argument('--resources',type=Path); ap.add_argument('files',nargs='+')
    args=ap.parse_args(); out=[]
    for f in args.files:
        p=Path(f); reord=args.flow=='reordered'
        out.append(check(p,reord,args.aircraft,args.horizon,args.resources,b_final=args.b_final,parachute_sizes=args.parachute_sizes))
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if any(x['status']!='PASS' for x in out): raise SystemExit(1)
