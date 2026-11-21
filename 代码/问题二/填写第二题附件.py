"""从已验证的人车联合服务证书生成第二题原模板填报草案。"""
from collections import Counter
from copy import copy
import argparse
import json
from pathlib import Path
from openpyxl import load_workbook
from 验证问题2实体证书 import verify

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    16: ('q2_tenth_b16', 'q2_tenth_joint_b16'),
    24: ('q2_tenth_b24', 'q2_tenth_joint_b24'),
    30: ('q2_tenth_b30', 'q2_tenth_joint_b30'),
}
CODE = {'tow':'0102','power_a':'0203','aircon_a':'0204','oil':'0205',
        'fuel':'0206','material':'0207','parachute':'0708','oxygen':'0910',
        'nitrogen':'0911','meal':'1213','power_b':'1314','aircon_b':'1315'}
SKILL = {'M1':'08','M2':'03','M3':'06','M4':'07','M5':'01','M6':'02','M7':'04','M8':'05'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT/'results/附件1_C_Solution1_填报.xlsx')
    args=ap.parse_args()
    template=ROOT/'附件模版/附件1  C_Solution1.xlsx'
    book=load_workbook(template)
    evidence={}
    for count,(schedule_name,certificate_name) in CASES.items():
        schedule_path=ROOT/'results'/f'{schedule_name}.json'
        certificate_path=ROOT/'results'/f'{certificate_name}.json'
        # Fail closed if a source file or certificate cannot be verified.
        stock=json.loads((ROOT/"results/q23_normalized.json").read_bytes())["airport_resources"]
        result=verify(schedule_path.read_bytes(),json.loads(certificate_path.read_bytes()),stock)
        schedule=json.loads(schedule_path.read_text(encoding='utf-8'))
        certificate=json.loads(certificate_path.read_text(encoding='utf-8'))
        operations={(r['aircraft'],r['operation']):r for r in schedule['operations']}
        rows=[]
        for service in certificate['services']:
            groups=Counter((side,group) for side,group,_ in service['people'])
            vehicle=service['vehicle'][1]
            for aircraft,operation in service['tasks']:
                if operation=='material':
                    ids=range(aircraft,min(aircraft+20,32+count))
                elif operation=='parachute':
                    ids=range(aircraft*40,min((aircraft+1)*40,32+count))
                else:
                    ids=(aircraft,)
                for i in ids:
                    op=operations.get((i,operation))
                    start=op['start_min'] if op else service['start_min']
                    end=op['end_min'] if op else service['end_min']
                    for (side,group),number in groups.items():
                        rows.append(('A' if i<32 else 'B',i+1,vehicle,1,side,group,number,
                                     SKILL[group],CODE[operation],start,end))
        rows.sort(key=lambda x:(x[1],x[9],x[10],x[8],x[5]))
        sheet=book[f'B种飞机{count}架']
        body_styles = [copy(sheet.cell(2, col)._style) for col in range(1, 12)]
        # Template body contains examples; replace only body rows, leaving the header intact.
        if sheet.max_row>1:
            sheet.delete_rows(2,sheet.max_row-1)
        for row in rows:
            sheet.append(row)
        for row in sheet.iter_rows(min_row=2):
            for cell, style in zip(row, body_styles):
                cell._style = copy(style)
            row[7].number_format='@'; row[8].number_format='@'
            row[9].number_format='0.0'; row[10].number_format='0.0'
        evidence[str(count)]={'rows':len(rows),'services':len(certificate['services']),'paired':certificate['paired_services'],
                              'source':schedule_name,'certificate':certificate_name,'verification':result}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    book.save(args.output)
    print(json.dumps({'output':str(args.output),'cases':evidence},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
