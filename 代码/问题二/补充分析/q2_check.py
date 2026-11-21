# -*- coding: utf-8 -*-
"""第二问 复核：充气按并发编组口径（每侧 ⌈N/10⌉ 辆、每车 1 人）重新判定三档配置"""
from ortools.sat.python import cp_model


def build_planes(nA, nB, n_tr, n_fu, ratio=0.2):
    n = nA + nB
    both = max(0, int(round(ratio * n_tr)))
    out = []
    for i in range(n):
        kind = 'A' if i < nA else 'B'
        tr = i < n_tr
        fu = (i < both) or (n_tr <= i < n_tr + (n_fu - both))
        out.append((kind, tr, fu))
    return out


def solve(nA, nB, cfg, tl=40):
    n_tr = max(1, int(round(0.10 * (nA + nB))))
    n_fu = max(1, int(round(0.10 * (nA + nB))))
    planes = build_planes(nA, nB, n_tr, n_fu)
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

    def cum(pairs, cap):
        ivs = [m.NewFixedSizeIntervalVar(v, d, f'c{i}') for i, (v, d) in enumerate(pairs)]
        m.AddCumulative(ivs, [1] * len(ivs), cap)

    cum(res['Z1'], cfg['k1']); cum(res['Z2'], cfg['k2']); cum(res['Z7'], cfg['k7'])
    cum(res['Z8'], cfg['k8'])
    cum(res['Z3'], 10 * cfg['k3']); cum(res['Z4'], 10 * cfg['k4'])
    A = [m.NewFixedSizeIntervalVar(v, d, f'a{i}') for i, (v, d) in enumerate(res['Z5'])]
    B = [m.NewFixedSizeIntervalVar(v, d, f'b{i}') for i, (v, d) in enumerate(res['Z6'])]
    m.AddCumulative(A, [1] * len(A), 2 * cfg['k5'])
    m.AddCumulative(B, [1] * len(B), 2 * cfg['k6'])
    m.AddCumulative(A + B, [1] * (len(A) + len(B)), 2 * cfg['P56'])
    allc = res['Z3'] + res['Z4']
    m.AddCumulative([m.NewFixedSizeIntervalVar(v, d, f'g{i}') for i, (v, d) in enumerate(allc)],
                    [1] * len(allc), 10 * min(cfg['k3'] + cfg['k4'], cfg['P34']))
    mk = m.NewIntVar(0, H, 'mk')
    for e in E.values():
        m.Add(mk >= e)
    m.Minimize(mk)
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = tl
    s.parameters.num_search_workers = 8
    st = s.Solve(m)
    return s.StatusName(st), (s.Value(mk) if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None)


if __name__ == '__main__':
    base = dict(k1=8, k7=1, H=120)
    cases = [
        ('48 架 M 自有 12/10/30/20人', 32, 16, dict(k2=12, k8=10, k3=4, k4=7, k5=15, k6=15, P56=20, P34=8)),
        ('48 架 最小编组 10/7/5+5/15人', 32, 16, dict(k2=10, k8=7, k3=5, k4=5, k5=10, k6=10, P56=15, P34=10)),
        ('56 架 最小编组 13/9/6+6/18人', 32, 24, dict(k2=13, k8=9, k3=6, k4=6, k5=12, k6=12, P56=18, P34=12)),
        ('62 架 最小编组 15/11/7+7/20人', 32, 30, dict(k2=15, k8=11, k3=7, k4=7, k5=15, k6=15, P56=20, P34=14)),
    ]
    for name, nA, nB, c in cases:
        print(f'{name:34s}', *solve(nA, nB, dict(base, **c)))
