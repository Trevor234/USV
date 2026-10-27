#!/usr/bin/env python3
"""Read-only observation audit. No replacement for the failed prerun checker."""
import hashlib,json,sqlite3
from collections import Counter
from pathlib import Path
D=Path(__file__).resolve().parent.parent
N=D.parent/'p1_execution_architecture_20261005_01'/'authored_D1_C3_10_20261015_v17'
R=N/'runs/owned_C310_foreign_after_close_01'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=R/'foreign/source.jsonl';transport=R/'synthetic_source/transport_source.jsonl';manifest=R/'foreign/owned_manifest.json';db=next((R/'recorder/bag').glob('*.db3'))
paths=[source,transport,manifest,db,D/'runs/foreign_after_close/check_result.json',R/'check_c310_foreign_close.py.snapshot']
before={str(p):sha(p) for p in paths}
loadlines=lambda p:[json.loads(l) for l in p.read_text().splitlines()]
pubs=[r for r in loadlines(source) if r['type']=='foreign_publish_result']
m=json.loads(manifest.read_text());gid=next(e['gid'] for e in m['endpoints'] if e['kind']=='publisher')
tr=[r for r in loadlines(transport) if r['publisher_gid']==gid]
connection=sqlite3.connect(f'file:{db}?mode=ro',uri=True)
tid=connection.execute('SELECT id FROM topics WHERE name=?',('/research/control/applied',)).fetchone()[0]
raw=connection.execute('SELECT id,data FROM messages WHERE topic_id=? ORDER BY timestamp,id',(tid,)).fetchall();connection.close()
rows=[]
for s,t in zip(pubs,tr):
 app=bytes.fromhex(s['cdr_hex']);pad=(-len(app))%4;candidate=app+b'\0'*pad;wire_sha=hashlib.sha256(candidate).hexdigest()
 matching=[(rid,blob) for rid,blob in raw if hashlib.sha256(blob).hexdigest()==t['payload_sha256']]
 rows.append(dict(packet_index=s['packet_index'],Source_CDR_bytes=len(app),Source_CDR_SHA256=hashlib.sha256(app).hexdigest(),
  transport_CDR_bytes=t['serialized_bytes'],transport_CDR_SHA256=t['payload_sha256'],append_zero_bytes=pad,
  expected_padded_CDR_SHA256=wire_sha,actual_SQLite_matching_occurrence_count=len(matching),
  Source_prefix_byte_exact=bool(matching) and all(blob[:len(app)]==app for _,blob in matching),
  actual_appended_hex=sorted(set(blob[len(app):].hex() for _,blob in matching)),
  actual_encapsulation4_unchanged=bool(matching) and all(blob[:4]==app[:4] for _,blob in matching),
  padded_bytes_exact_actual_SQLite=bool(matching) and all(blob==candidate for _,blob in matching),
  transport_GID_exact_foreign=t['publisher_gid']==gid,Source_publish_before_transport_receive=s['publish_start_ns']<=t['receive_ns']))
after={str(p):sha(p) for p in paths}
report=dict(schema='p1-C3.10-readonly-Source-wire-padding-observation-v1',passed=before==after and len(rows)==3 and all(r['Source_prefix_byte_exact'] and r['actual_encapsulation4_unchanged'] and r['padded_bytes_exact_actual_SQLite'] and r['expected_padded_CDR_SHA256']==r['transport_CDR_SHA256'] for r in rows),
 original_prerun_checker_passed=False,original_failure_preserved=True,posthoc_observation_only=True,
 unique_bag_row_writer_identity_proven=False,original_SQLite_row_writer_assignment_performed=False,
 interpretation='Observed three Source buffers match received buffers only after exact zero append to next multiple of four. This is an observed byte relation; this audit alone does not establish which middleware operation caused it or a general CDR normalization rule.',
 population=rows,input_SHA256_before=before,input_SHA256_after=after,qualifications={k:False for k in ('stage','execute','P1','M4','F6','research_conclusion')})
out=Path(__file__).with_suffix('.json')
with out.open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'passed':report['passed'],'output':str(out),'sha256':sha(out),'original_prerun_checker_passed':False}))
