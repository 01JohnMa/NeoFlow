#!/usr/bin/env python3
"""Deterministic scorer for saved outcomes. Never calls a provider."""
import argparse,hashlib,json,pathlib
SUCCESS={'succeeded','success','completed'}
def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def norm(v,r): return v.strip() if isinstance(v,str) and r.get('trim_strings',True) else v
def pages_from_refs(refs):
 out=[]
 vals=refs.values() if isinstance(refs,dict) else refs if isinstance(refs,list) else []
 for v in vals:
  if isinstance(v,dict): v=v.get('pages',[])
  if isinstance(v,list):
   for x in v:
    if isinstance(x,int): out.append(x)
    elif isinstance(x,dict) and isinstance(x.get('page'),int): out.append(x['page'])
 return set(out)
def score(j,g,rub):
 fields=g.get('fields',{}); absent=set(g.get('absent_fields',[])); out=j.get('data') or {}; alln=set(fields)|absent
 correct=wrong=unsupported=filled=absc=0
 for n in alln:
  has=n in out and out[n] is not None
  if n in fields:
   if has: filled+=1; correct += norm(out[n],rub['normalization'])==norm(fields[n].get('value'),rub['normalization']); wrong += norm(out[n],rub['normalization'])!=norm(fields[n].get('value'),rub['normalization'])
   elif fields[n].get('required'): wrong+=1
  elif has: unsupported+=1
 for n in out:
  if n not in alln and out[n] is not None: unsupported+=1
 for n in absent:
  if n not in out or out[n] is None: absc+=1
 valid=set(j.get('valid_evidence_pages') or [])
 retrieved=set(j.get('retrieved_pages') or [])
 expected=set(p for x in fields.values() for p in x.get('evidence_pages',[]))
 cited=pages_from_refs(j.get('evidence'))
 supportsets=[set(x) for x in j.get('evidence_support_sets',[]) if isinstance(x,list)]
 support=sum(bool(s & retrieved) for s in supportsets)/len(supportsets) if supportsets else (len(expected&retrieved)/len(expected) if expected else None)
 return {'status':j.get('status','unknown'),'failed':j.get('status') not in SUCCESS,'field_correct':correct,'field_total':len(alln),'field_correctness':correct/len(alln) if alln else None,'wrong_values':wrong,'filled':filled,'unsupported_fills':unsupported,'unsupported_rate':unsupported/filled if filled else 0.0,'abstention_correct':absc,'abstention_total':len(absent),'evidence_page_support':support,'evidence_reference_validity':len(cited&valid)/len(cited) if cited else None,'parse_result_id':j.get('parse_result_id'),'retrieved_pages':len(retrieved),'latency_ms':j.get('latency_ms'),'tokens':j.get('tokens'),'retries':j.get('retries'),'cache_hit':j.get('cache_hit')}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--outcomes',required=True); p.add_argument('--output'); p.add_argument('--freeze',action='store_true'); a=p.parse_args(); mp=pathlib.Path(a.manifest); m=load(mp); base=mp.parent
 if a.freeze:
  missing=[k for k in ('implementation_commit','configuration_revision_id','parse_profile','provider','model') if not m.get(k)]
  if missing: raise SystemExit('cannot freeze: fill '+','.join(missing))
  m['status']='frozen'; m['source_hashes']={c['case_id']:hashlib.sha256((base/c['source']).read_bytes()).hexdigest() for c in m['cases']}; m['gold_hashes']={c['case_id']:hashlib.sha256((base/c['gold']).read_bytes()).hexdigest() for c in m['cases']}; mp.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'status':'frozen','source_hashes':m['source_hashes'],'gold_hashes':m['gold_hashes']},indent=2)); return
 rub=load(base/'rubric.json'); raw=load(a.outcomes) if a.outcomes.endswith('.json') else [json.loads(x) for x in pathlib.Path(a.outcomes).read_text().splitlines() if x.strip()]; by={c['case_id']:c for c in m['cases']}; rows=[]; seen={}
 for j in raw:
  c=by.get(j.get('case_id')); key=tuple(j.get(x) for x in ('case_id','strategy','scenario','repetition')); seen[key]=j; rows.append(dict(score(j,load(base/c['gold']),rub),**{x:j.get(x) for x in ('case_id','strategy','scenario','repetition','stratum')})) if c else rows.append({'case_id':j.get('case_id'),'failed':True,'error':'not_in_manifest'})
 required=[(c['case_id'],s,sc,rep) for c in m['cases'] for s in ('full_document','page_routed') for sc in m['scenarios'] for rep in [0]]
 for k in required:
  if k not in seen: rows.append({'case_id':k[0],'strategy':k[1],'scenario':k[2],'repetition':k[3],'failed':True,'error':'missing_outcome','field_correctness':0.0,'unsupported_rate':0.0})
 strata={}
 for x in rows: strata.setdefault(x.get('stratum') or by.get(x.get('case_id'),{}).get('stratum','unknown'),[]).append(x)
 gates={}
 for st,xs in strata.items():
  def avg(strategy,field):
   z=[x.get(field) for x in xs if x.get('strategy')==strategy and x.get(field) is not None]; return sum(z)/len(z) if z else None
  fc,fp=avg('full_document','field_correctness'),avg('page_routed','field_correctness'); ur,up=avg('full_document','unsupported_rate'),avg('page_routed','unsupported_rate'); gates[st]={'full_correctness':fc,'page_routed_correctness':fp,'full_unsupported_rate':ur,'page_routed_unsupported_rate':up,'pass':fc is not None and fp is not None and fp>=fc and up<=ur}
 report={'manifest_version':m['manifest_version'],'rubric_version':rub['rubric_version'],'rows':rows,'denominator':len(rows),'strata':gates,'rollout_decision':'NO_GO','evaluation_complete':bool(raw) and not any(x.get('error')=='missing_outcome' for x in rows),'gaps':['manifest not frozen'] if m.get('status')!='frozen' else []}
 text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'; pathlib.Path(a.output).write_text(text) if a.output else print(text,end='')
if __name__=='__main__': main()
