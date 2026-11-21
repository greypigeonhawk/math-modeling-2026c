"""从项目内的原始DOCX提取第一题资源与首次保障任务表。"""
from pathlib import Path
import json
from docx import Document

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "新2026C.docx"
OUT = ROOT / "results" / "q1_source_tables.json"


def cell_text(cell: object) -> str:
    return " ".join(cell.text.split())


def rows(table: object) -> list[list[str]]:
    return [[cell_text(cell) for cell in row.cells] for row in table.rows]


def main() -> None:
    document = Document(SOURCE)
    if len(document.tables) < 4:
        raise ValueError(f"预期至少4张表，实际发现{len(document.tables)}张")
    data = {
        "source": str(SOURCE.relative_to(ROOT)),
        "multi_skill_table": rows(document.tables[0]),
        "m_ground_resources": rows(document.tables[1]),
        "first_service_tasks": rows(document.tables[3]),
    }
    if len(data["multi_skill_table"]) != 9:
        raise ValueError("一专多能表行数与题面不符")
    if len(data["first_service_tasks"]) != 11:
        raise ValueError("首次保障任务表行数与题面不符")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"extracted skill_rows={len(data['multi_skill_table']) - 1}")
    print(f"extracted first_service_rows={len(data['first_service_tasks']) - 1}")
    print(f"output={OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
