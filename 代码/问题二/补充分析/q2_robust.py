# -*- coding: utf-8 -*-
"""问题二 鲁棒性补算：工序抖动 + 牵引全覆盖（与第三问口径做交叉校核）"""
import math
from ortools.sat.python import cp_model


def planes_of(nA, nB, tow_mode='ratio10'):
    if tow_mode == 'allB':
        tr_idx = set(range(0, max(1, int(round(0.10 * nA))))) | set(range(nA, nA + nB))
        n_tr = len(tr_idx)
    else:
        n_tr = max(1, int(round(0.10 * (nA + nB))))
        tr_idx = set(range(n_tr))
    both = min(max(1, int(round(0.02 * (nA + nB)))), n_tr)
    out = []
    for i in range(nA + nB):
        kind = 'A' if i < nA else 'B'
        tr = i in tr_idx
        fu = (i < both) or (n_tr <= i < n_tr + (n_tr - both))
        out.append((kind, tr, fu))
    return out, n_tr


def solve(nA, nB, cfg, delta=0, tow_mode='ratio10', tl=30):
    planes, n_tr = planes_of(nA, nB, tow_mode)
    H = cfg.get('H', 140)
    m = cp_model.CpModel()
    S, E = {}, {}
    res = {k: [] for k in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7', 'Z8']}
    for j, (kind, tr, fu) in enumerate(planes):
        rf = (15 if kind == 'A' else 30) + delta
        meal = (8 if kind == 'A' else 25) + delta
        spec = [('PA', 'Z5', 15 + delta), ('AA', 'Z6', 15 + delta), ('RF', 'Z2', rf),
                ('OX', 'Z3', 3 + delta), ('NX', 'Z4', 3 + delta), ('MEAL', 'Z8', meal),
                ('PB', 'Z5', 15 + delta), ('AB', 'Z6', 15 + delta)]
        if fu:
            spec.insert(3, ('FO', 'Z7', 10 + delta))
        p1 = ['PA', 'AA'] + (['FO'] if fu else []) + ['RF']
        if tr:
            spec.insert(0, ('TR', 'Z1', 10 + delta))
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
    return s.StatusName(st), val, n_tr


CI = [
    ('48架', 32, 16, dict(k2=10, k8=7, k3=5, k4=5, k5=10, k6=10, P56=15, P34=10)),
    ('56架', 32, 24, dict(k2=13, k8=9, k3=6, k4=6, k5=12, k6=12, P56=18, P34=12)),
    ('62架', 32, 30, dict(k2=15, k8=11, k3=7, k4=7, k5=15, k6=15, P56=20, P34=14)),
]

print('== A. 工序时长整体抖动 delta')
for d in (0, 1, 2, 3):
    row = []
    for nm, nA, nB, c in CI:
        st, val, n_tr = solve(nA, nB, dict(k1=8, k7=1, H=140, **c), delta=d)
        row.append(f'{nm}={val}')
    print(f'  delta={d}min  ' + '  '.join(row))

print('== B. B 机全部需要牵引（10% 口径被读成全覆盖）')
for nm, nA, nB, c in CI:
    st, val, n_tr = solve(nA, nB, dict(k1=8, k7=1, H=140, **c), delta=0, tow_mode='allB')
    print(f'  {nm}  牵引机位={n_tr}  状态={st} 完工={val}')
