#!/usr/bin/env python3
"""Independently join declared preparation create-call IO exception and actual closed evidence."""
import argparse,json,sys
from pathlib import Path
AUTHOR=Path(__file__).resolve().parent;N=AUTHOR.parent/'authored_D1_C3_4_20261013_v10'
R=AUTHOR.parent.parent/'scheme_A_C3_5_20261013_10'
sys.path.insert(0,str(N))
import check_release_observation_v1 as C
from build_c34_v10 import dump
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 run=args.run;assert run==N/'runs/owned_C3_4_ambiguous_preparation_01';reader=C.Inputs();inputs=reader.json(run/'inputs.json');result=reader.json(run/'result.json')
 C.domains.inputs(inputs);C.domains.result(result)
 assert result['passed'] is False and result['evidence_qualification_clean'] is False and result['held_negative_passed'] is True
 assert result['cleanup_complete'] is True and result['cleanup_within_budget'] is True and result['close_elapsed_ns']<=15_000_000_000
 assert result['owned_role_returncodes']=={r:0 for r in C.ROLES}
 ambiguous=result['publication_ambiguous'];evidence=reader.raw(ambiguous['path']);assert ambiguous['target_visible'] is True and C.digest(evidence)==ambiguous['content_sha256']
 assert not (run/'release.json').exists() and not (run/'publisher/release_receipt.json').exists() and not (run/'synthetic_start.json').exists()
 report=reader.json(run/'publisher/release_observation.json');C.domains.report(report);gate=report['gate'];C.domains.gate(gate)
 assert gate['gate_state']=='Held' and gate['failure_phase']=='none' and gate['original_freshness_read_count']==0 and gate['receipt_io_completed'] is False
 assert all(gate[k] is None for k in ('validate_now_ns','attempt_now_ns','final_freshness_now_ns','commit_steady_ns','accepted_release_sha256','arm_start_steady_ns','arm_end_steady_ns'))
 startup=reader.json(run/'publisher/startup_manifest.json');session=reader.json(run/'publisher/session_summary.json')
 C.check_source_session(session,startup,report['snapshot_steady_ns'],'unarmed')
 assert set(session['streams'])=={'state','applied','cycle','reference_prediction'} and all(type(v) is int and v==0 for row in session['streams'].values() for v in row.values())
 publication=reader.json(run/'release_publication_observation.json');assert publication['events']==[]
 topics=reader.json(run/'topics.json')['topics'];storage_rows,storage,inventory=C.sqlite_storage(reader,run/'recorder/bag',topics)
 owned={r:reader.json(run/r/'owned_manifest.json') for r in C.ROLES};gids={}
 for manifest in owned.values():
  for endpoint in manifest['endpoints']:
   if endpoint['kind']=='publisher' and endpoint['topic'] in topics:
    assert endpoint['topic'] not in gids;gids[endpoint['topic']]=endpoint['gid']
 observed={t:[] for t in topics}
 for ordinal,row in enumerate(reader.jsonl(run/'synthetic_source/transport_source.jsonl'),1):
  C.domains.transport(row);assert row['ordinal']==ordinal and row['publisher_gid']==gids[row['topic']] and row['ros_type']==topics[row['topic']]
  observed[row['topic']].append((row['payload_sha256'],row['serialized_bytes']))
 assert observed==storage_rows
 command_topics=['/research/state_snapshot','/research/control/applied','/research/cycle_timing','/research/reference_prediction']+[owned['publisher']['effective_parameters'][k]['value'] for k in ('vrx_left_thrust_topic','vrx_right_thrust_topic')]
 assert all(not observed[t] for t in command_topics)
 terminal=reader.json(run/'recorder/terminal.json');assert terminal['clean'] is True and terminal['Recorder_stop_completed'] is True and terminal['error']==''
 ledger=reader.jsonl(run/'owned_process_ledger.jsonl');assert len([x for x in ledger if x.get('type')=='spawn'])==5
 for row in ledger:C.domains.ledger(row)
 assert reader.unchanged()==reader.before
 output={'schema':'p1-C3.5-ambiguous-preparation-actual-join/v2','passed':True,'run':str(run),'publication_ambiguous':ambiguous,
  'fault_origin':'declared Python driver directory-fsync exception at real preparation evidence create-call; not spontaneous storage failure',
  'publisher_gate':gate,'publisher_session_streams':session['streams'],'whole_transport_SQLite_join':True,'storage':storage,'command_topics_zero':command_topics,
  'cleanup_complete':True,'source_input_sha256':reader.before,'input_bytes_unchanged':True,'normal_qualified':False,'evidence_qualification_clean':False,
  'limits':['preparation evidence failure occurred before release authorization create-call','zero is proven by actual terminal/transport/storage; never inferred from exception alone','visible release with failed driver return is covered separately by A native probe only','old timeout causes remain unknown'],
  'stage_qualified':False,'execute':False,'research_conclusion':False}
 dump(args.output,output);print(json.dumps({'passed':True,'storage_messages':storage['total_messages'],'gate':'Held','command_streams_zero':True}));return 0
if __name__=='__main__':raise SystemExit(main())
