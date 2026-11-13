"""Compare measured records to independently authored source expectations."""
import hashlib
import json
from pathlib import Path

SCALARS=('request_id','request_date','kind','requester','team','system','environment','permission','business_purpose','start_date','end_date','manager')
def compare_records(records,expected):
    actual={row['document_id']:row for row in records}
    if len(actual)!=len(records):raise ValueError('duplicate measured documents')
    report=dict(matches=0,denominator=12*len(expected),whole_record_matches=0,route_matches=0,documents=len(expected),factual_errors=[],manual_review=[],route_errors=[],integrity_errors=[],missing_documents=[],extraction_errors=[],field_matches={key:0 for key in SCALARS},origins=sorted({row.get('response_source','unknown') for row in records}))
    for name,case in expected.items():
        document_id=Path(case['input']).name;row=actual.get(document_id)
        if row is None:report['missing_documents'].append(document_id)
        extraction=row.get('extraction') if row and not row.get('error') else None
        if extraction is None:report['extraction_errors'].append(document_id)
        count=0
        for field in SCALARS:
            wanted=case['extraction'][field]
            if extraction is not None and field in extraction and extraction[field]==wanted:
                report['matches']+=1;report['field_matches'][field]+=1;count+=1
            else:
                discrepancy={'document_id':document_id,'field':field,'expected':wanted,'actual':extraction.get(field) if extraction else None}
                if extraction is not None:
                    if field=='business_purpose':report['manual_review'].append(discrepancy)
                    else:report['factual_errors'].append(discrepancy)
        if count==12:report['whole_record_matches']+=1
        route=case['expected_route_for_later_steps']
        if row and all(row.get(k)==v for k,v in route.items()):report['route_matches']+=1
        else:report['route_errors'].append(document_id)
        if row:
            path=Path(case['input'])
            if path.exists():
                raw=path.read_bytes();message=json.loads(raw.decode('utf-8'))['message']
                if row.get('source_sha256')!=hashlib.sha256(raw).hexdigest():report['integrity_errors'].append(document_id+': source hash mismatch')
                if extraction and any(not isinstance(quote,str) or quote not in message for quote in extraction.get('supporting_quotes',[])):report['integrity_errors'].append(document_id+': unsupported quote')
            if extraction:
                for field in SCALARS:
                    if case['extraction'][field] is None and not any(field.replace('_',' ') in issue.lower().replace('_',' ') for issue in extraction.get('issues',[])):
                        report['integrity_errors'].append(document_id+': missing issue for '+field)
    return report

def write_accuracy(records,expected_path,out):
    expected=json.loads(Path(expected_path).read_text())['cases'];report=compare_records(records,expected)
    lines=['# Accuracy evidence','', '**Observation: mock records verify pipeline/fixture agreement; this is not live-model factual accuracy.**' if report['origins']==['mock'] else '**Observation: see each record response_source and configuration; source expectations remain independent.**','',f"Scalar exact matches: {report['matches']}/{report['denominator']}; whole scalar records: {report['whole_record_matches']}/{report['documents']}; routes: {report['route_matches']}/{report['documents']}.",'', 'Twelve scalar fields are scored once per source. Strings compare exactly, without normalization; JSON null matches only JSON null on a successful extraction. Missing/failed extractions score zero across all twelve slots, even where the expected value is null. Arrays are excluded from this denominator; quote provenance and missing-fact issues are checked separately. There is no minimum accuracy threshold.','', 'Business-purpose wording disagreements count as exact-match misses and require human factual review. The evaluator does not claim to determine paraphrase equivalence automatically. Other scalar disagreements, missing/failed records, routing errors and provenance issues are reported explicitly.','', 'Reproduce: `python3 -m access_intake accuracy --actual deliverables/extractions.jsonl --expected tests/expected/source-facts.json --out deliverables/accuracy.md`','', '## Observed configurations','', '```json',json.dumps([{'document_id':r['document_id'],'response_source':r.get('response_source'),'configuration':r.get('configuration',{})} for r in records],indent=2),'```','', '## Source-derived expected facts','', '| Case | Input | Expected scalar facts | Expected route | Source evidence |','|---|---|---|---|---|']
    for name,case in expected.items():
        facts={key:case['extraction'][key] for key in SCALARS}
        evidence=' '.join(item['quote'] for item in case['source_evidence'])
        cells=[name,case['input'],json.dumps(facts,ensure_ascii=False),json.dumps(case['expected_route_for_later_steps']),evidence]
        lines.append('| '+' | '.join(cell.replace('|','&#124;').replace('\n','<br>') for cell in cells)+' |')
    lines+=['','## Comparison details','','```json',json.dumps(report,indent=2,ensure_ascii=False),'```','', ('No live observations were collected. Request-construction evidence uses a separately labeled capture-only provider configuration and did not produce these mock records.' if report['origins']==['mock'] else 'This evaluator makes no model calls. Provider observations are identified per record; request evidence is separately labeled capture-only.')]
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text('\n'.join(lines)+'\n')
    return report
