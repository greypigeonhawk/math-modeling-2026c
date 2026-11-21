# -*- coding: utf-8 -*-
"""口径敏感性：10% 特殊机位按「全机队总量取整」vs「按机型分别取整」"""
import math
from ortools.sat.python import cp_model


def planes_of(nA, nB, mode):
    if mode == 'total':
        n_tr = max(1, int(round(0.10 * (nA + nB))))
    else:
        n_tr = max(1, math.ceil(0.10 * nA) + math.ceil(0.10 * nB))
    both = min(n_tr, max(1, int(round(0.02 * (nA + nB))))) 
    out = []
    for i in range(nA + nB):
        kind = 'A' if i < nA else 'B'
        tr = i < n_tr
        fu = (i < both) or (n_tr <= i < n_tr + (n_tr - both))
        out.append((kind, tr, fu))
    return out, n_tr, both


def solve(nA, nB, cfg, mode='total', tl=30):
    planes, n_tr, both = planes_of(nA, nB, mode)
    H = cfg.get('H', 130)
    m = cp_model.CpModel()
    S, E = {}, {}
    res = {k: [] for k in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7', 'Z8']}
    for j, (kind, tr, fu) in enumerate(planes):
        rf = 15 if kind == 'A' else 30
        meal = 8 if kind == 'A' else 25
        spec = [('PA', 'Z5', 15), ('AA', 'Z6', 15), ('RF', 'Z2', rf),
                ('OX', 'Z3', 3), ('NX', 'Z4', 3), ('MEAL', 'Z8', meal),
                ('PB', 'Z5', 15), ('AB', 'Z6', 15)]
        if fu:
            spec.insert(3, ('FO', 'Z7', 10))
        p1 = ['PA', 'AA'] + (['FO'] if fu else []) + ['RF']
        if tr:
            spec.insert(0, ('TR', 'Z1', 10))
        for nm, r, d in spec:
            S[j, nm] = m.NewIntVar(0, H, f's{j}_{nm}')
            E[j, nm] = m.NewIntVar(0, H, f'e{j}_{nm}')
            m.Add(E[j, nm] == S[j, nm] + d)
            res[r].append((S[j, nm], d))
        if tr:
            for nm in p1:
                m.Add(S[j, nm] >= E[j, 'TR'])
        for nm in ['OX', 'NX']:
            for p in p1:
                m.Add(S[j, nm] >= E[j, p])
        for nm in ['PB', 'AB']:
            m.Add(S[j, nm] >= E[j, 'MEAL'])

    def cum(pairs, cap, tag):
        ivs = [m.NewFixedSizeIntervalVar(v, d, f'{tag}{i}') for i, (v, d) in enumerate(pairs)]
        m.AddCumulative(ivs, [1] * len(ivs), cap)

    cum(res['Z1'], cfg['k1'], 'z1'); cum(res['Z2'], cfg['k2'], 'z2')
    cum(res['Z7'], cfg['k7'], 'z7'); cum(res['Z8'], cfg['k8'], 'z8')
    cum(res['Z3'], 10 * cfg['k3'], 'z3'); cum(res['Z4'], 10 * cfg['k4'], 'z4')
    A = [m.NewFixedSizeIntervalVar(v, d, f'a{i}') for i, (v, d) in enumerate(res['Z5'])]
    B = [m.NewFixedSizeIntervalVar(v, d, f'b{i}') for i, (v, d) in enumerate(res['Z6'])]
    m.AddCumulative(A, [1] * len(A), 2 * cfg['k5'])
    m.AddCumulative(B, [1] * len(B), 2 * cfg['k6'])
    m.AddCumulative(A + B, [1] * (len(A) + len(B)), 2 * cfg['P56'])
    mk = m.NewIntVar(0, H, 'mk')
    for e in E.values():
        m.Add(mk >= e)
    m.Minimize(mk)
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = tl
    s.parameters.num_search_workers = 8
    st = s.Solve(m)
    val = s.Value(mk) if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return s.StatusName(st), val, n_tr, both


CASES = [
    ('48架 A32+B16  10/7/5+5/15人', 32, 16, dict(k2=10, k8=7, k3=5, k4=5, k5=10, k6=10, P56=15, P34=10)),
    ('56架 A32+B24  13/9/6+6/18人', 32, 24, dict(k2=13, k8=9, k3=6, k4=6, k5=12, k6=12, P56=18, P34=12)),
    ('62架 A32+B30  15/11/7+7/20人', 32, 30, dict(k2=15, k8=11, k3=7, k4=7, k5=15, k6=15, P56=20, P34=14)),
]

for mode in ('total', 'pertype'):
    print('== 10% 取整口径:', mode)
    for name, nA, nB, c in CASES:
        st, val, n_tr, both = solve(nA, nB, dict(k1=8, k7=1, H=120, **c), mode)
        print(f'  {name:30s} 牵引=附油={n_tr} 交集={both}  状态={st} 完工={val}')
