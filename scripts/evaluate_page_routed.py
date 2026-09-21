#!/usr/bin/env python3
"""Score saved paired page-routed/full-document outcomes; never calls providers."""
from __future__ import annotations
import argparse, json, pathlib, sys

def load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)
def norm(v, r):
    if isinstance(v,str) and r.get('trim_strings',True): return v.strip()
    return v
def score(job, gold, rubric):
    fields=gold.get('fields',{}); out=job.get('data') or {}; refs=job.get('evidence') or {}
    valid_pages=set(job.get('valid_evidence_pages') or job.get('retrieved_pages') or [])
    expected_pages={p for x in fields.values() for p in x.get('evidence_pages',[])}
    correct=unsupported=filled=absent_correct=0
    for name,spec in fields.items():
        has=name in out and out[name] is not None
        if has: filled+=1
        if has and norm(out[name],rubric['normalization'])==norm(spec.get('value'),rubric['normalization']): correct+=1
    for name in gold.get('absent_fields',[]):
        if name not in out or out[name] is None: absent_correct+=1
        elif name in out: unsupported+=1
    for name in out:
        if name not in fields and name not in gold.get('absent_fields',[]): unsupported+=1
    cited=set()
    if isinstance(refs,dict):
        for v in refs.values(): cited.update(v if isinstance(v,list) else v.get('pages',[]) if isinstance(v,dict) else [])
    elif isinstance(refs,list): cited.update(refs)
    return {'status':job.get('status','unknown'),'failed':job.get('status') not in ('succeeded','success','completed'),'field_correct':correct,'field_total':len(fields),'field_correctness':correct/len(fields) if fields else None,'filled':filled,'unsupported_fills':unsupported,'evidence_recall':len(expected_pages & valid_pages)/len(expected_pages) if expected_pages else None,'reference_validity':len(cited & valid_pages)/len(cited) if cited else None,'retrieved_pages':len(valid_pages),'parse_result_id':job.get('parse_result_id'),'latency_ms':job.get('latency_ms'),'tokens':job.get('tokens'),'retries':job.get('retries'),'cache_hit':job.get('cache_hit')}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--outcomes',required=True,help='JSON array or JSONL; each row has case_id,strategy,scenario and outcome fields'); ap.add_argument('--output'); a=ap.parse_args()
 base=pathlib.Path(a.manifest).parent; m=load(a.manifest); rubric=load(base/'rubric.json'); raw=load(a.outcomes) if a.outcomes.endswith('.json') else [json.loads(x) for x in open(a.outcomes,encoding='utf-8') if x.strip()]
 by={c['case_id']:c for c in m['cases']}; rows=[]
 for j in raw:
  c=by.get(j.get('case_id'))
  if not c: rows.append({'case_id':j.get('case_id'),'error':'not_in_manifest'}); continue
  g=load(base/c['gold']); r=score(j,g,rubric); r.update({k:j.get(k) for k in ('case_id','strategy','scenario')}); rows.append(r)
 report={'manifest_version':m['manifest_version'],'rubric_version':rubric['rubric_version'],'rows':rows,'denominator':len(rows),'rollout_decision':'NO_GO_UNTIL_PROVIDER_AND_AUTHORIZED_THRESHOLDS','gaps':[]}
 if any(c.get('parse_result_id') is None for c in m['cases']): report['gaps'].append('manifest parse_result_id not filled')
 if not raw: report['gaps'].append('no outcomes supplied')
 text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
 if a.output: pathlib.Path(a.output).write_text(text,encoding='utf-8')
 else: print(text,end='')
if __name__=='__main__': main()
