"""Normalize source tables for the mixed-fleet and runway models."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/新2026C.docx'
TABLES = ROOT / 'results/q23_source_tables.json'
OUTPUT = ROOT / 'results/q23_normalized.json'
RUNWAYS = '甲乙丙丁戊己庚'


def normalize():
    data = json.loads(TABLES.read_text(encoding='utf-8'))
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != data['source']['sha256']:
        raise ValueError('原题文件哈希与提取表不一致，请重新提取')
    resources = {}
    for side in ('M', 'N'):
        rows = data[f'{side}_resources'][2:]
        resources[side] = {
            'vehicles': {r[0]: int(r[1]) for r in rows if r[0].startswith('Z')},
            'people': {r[3]: int(r[4]) for r in rows if r[3].startswith('M')},
        }
    teams = {name: {'vehicles': {}, 'people': {}} for name in '甲乙丙丁'}
    for row in data['runway_resources'][1:]:
        kind = 'vehicles' if row[1].startswith('Z') else 'people'
        for i, team in enumerate(teams):
            teams[team][kind][row[1]] = int(row[i + 2])
    capacities = {r: {} for r in RUNWAYS}
    for row in data['parking_capacity'][1:]:
        found = re.search(r'([AB])\s*种飞机\s*(\d+)\s*架', row[2])
        if not found:
            raise ValueError(f'无法读取停机能力: {row}')
        capacities[row[1][0]][found.group(1)] = int(found.group(2))
    distances = {}
    for row in data['road_distances'][1:8]:
        distances[row[0]] = {r: int(v) for r, v in zip(RUNWAYS, row[1:])}
    assert all(distances[a][b] == distances[b][a] for a in RUNWAYS for b in RUNWAYS)
    assert all(set(x) == {'A', 'B'} for x in capacities.values())
    assert all(len(r['vehicles']) == 9 and len(r['people']) == 8 for r in resources.values())
    assert all(len(r['vehicles']) == 9 and len(r['people']) == 8 for r in teams.values())
    return {'source_sha256': digest, 'airport_resources': resources,
            'runway_team_resources': teams, 'parking_capacity': capacities,
            'road_distance_km': distances,
            'skills': data['skills'][1:]}


if __name__ == '__main__':
    normalized = normalize()
    OUTPUT.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'已生成 {OUTPUT}; 题面 SHA256={normalized["source_sha256"]}')
