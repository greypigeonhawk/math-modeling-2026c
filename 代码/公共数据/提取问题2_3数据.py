"""从题目 DOCX 提取问题2、问题3使用的权威表格与表格字段。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "新2026C.docx"
OUTPUT = ROOT / "results" / "q23_source_tables.json"


def table_rows(table):
    return [[cell.text.strip() for cell in row.cells] for row in table.rows]


def main():
    doc = Document(SOURCE)
    if len(doc.tables) != 12:
        raise ValueError(f"预期12张表，实际为{len(doc.tables)}张；需复核题面版本")
    payload = {
        "source": {
            "path": "data/新2026C.docx",
            "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        },
        "skills": table_rows(doc.tables[0]),
        "M_resources": table_rows(doc.tables[1]),
        "N_resources": table_rows(doc.tables[2]),
        "first_service_tasks": table_rows(doc.tables[3]),
        "second_service_tasks": table_rows(doc.tables[4]),
        "parking_capacity": table_rows(doc.tables[5]),
        "runway_resources": table_rows(doc.tables[6]),
        "road_distances": table_rows(doc.tables[7]),
        "vehicle_priority": table_rows(doc.tables[8]),
        "C_Solution1_schema": table_rows(doc.tables[9]),
        "C_Solution2_1_schema": table_rows(doc.tables[10]),
        "C_Solution2_2_schema": table_rows(doc.tables[11]),
    }
    # Guard the row sets and key fields used by both optimization models.
    expected = {
        "skills": 9,
        "M_resources": 11,
        "N_resources": 11,
        "first_service_tasks": 11,
        "second_service_tasks": 9,
        "parking_capacity": 15,
        "runway_resources": 18,
        "road_distances": 9,
        "vehicle_priority": 8,
    }
    for name, nrows in expected.items():
        if len(payload[name]) != nrows:
            raise ValueError(f"{name} 行数异常：{len(payload[name])} != {nrows}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "sha256": payload["source"]["sha256"],
                      "tables": {k: len(payload[k]) for k in expected}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
