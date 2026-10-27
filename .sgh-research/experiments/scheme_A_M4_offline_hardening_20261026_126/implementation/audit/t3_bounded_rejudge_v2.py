"""Read-only historical T3 facts. No signals, new processes, or harness top-pass trust."""
from pathlib import Path
import json

EXP=Path('/home/trevor/USV/.sgh-research/experiments')

def rows(path):
 return [json.loads(line)for line in Path(path).read_text().splitlines()if line.strip()]

def rejudge():
 root=EXP/'scheme_A_M4_t3c_impl_20261025_100'
 result={}
 for tag in ['C12','C3']:
  run=root/'implementation/runs'/('T3C_'+tag)
  events=rows(run/'driver_events.jsonl');d=json.loads((run/'driver_result.json').read_text())
  spawned=[r for r in events if r['type']=='role_spawned'];closed=d['closed_roles'];by={r['role']:r for r in closed}
  facts={'four_unique_driver_spawns':len(spawned)==4 and len({r['role']for r in spawned})==4,
   'four_unique_closed':len(closed)==4 and len(by)==4,
   'no_driver_restart_event':not any(any(word in r['type']for word in ['restart','respawn','retry'])for r in events)}
  cleanup=[r for r in events if r['type']=='cleanup_failed']
  if tag=='C12':
   facts.update({'cleanup_failed_fixture':len(cleanup)==1 and cleanup[0]['role']=='fixture'and cleanup[0]['group_empty']is False,
    'fixture_int_term':[s['signal']for s in by['fixture']['signals']]==['SIGINT','SIGTERM'],
    'fixture_rc0_group_nonempty':by['fixture']['returncode']==0 and by['fixture']['group_empty']is False,
    'other_roles_closed':all(by[r]['returncode']==0 and by[r]['group_empty']is True for r in ['regulator','worker','recorder']),
    'original_run_still_failed':d.get('passed')is False and d.get('cleanup_failed_roles')==['fixture']})
  else:
   facts.update({'no_cleanup_failed':not cleanup and d.get('cleanup_failed_roles')==[],
    'all_groups_empty':all(r['group_empty']is True and r['returncode']==0 for r in closed)})
  result[tag]={'facts':facts,'all_expected_facts':all(facts.values()),'role_stream_scope':'Driver event/close journal only'}
 source=(root/'implementation/t2_author/fixture/synthetic_source_m4_t3_survivor.cpp').read_text()
 handler=source[source.index('static void stop_signal'):source.index('\n',source.index('static void stop_signal'))]
 result['survivor_source']={'signal_handler_only_sets_stop':'fork('not in handler and 'stop_requested=true'in handler,
  'fork_reached_from_main':'node->t3_close_with_survivor()'in source[source.index('int main('):],
  'fd_range_3_to_255':'for(int fd=3;fd<256;++fd)'in source,
  'fork_failure_not_handled':'pid<0'not in source and 'pid < 0'not in source,
  'all_fd_cleanup':'not_covered','kernel_hard_exit':'not_covered','generic_restart_proof':'not_covered'}
 result['audit101_provenance']={
  'independently_recomputed':['Source row counts/generated-emitted-dropped balance','Driver close/signal/group entries','SHA of listed binary/source/manifest files'],
  'referenced_harness_or_runner':['assertion names/count/passed fields','v2 runner verdict population and pass fields'],
  'not_proved':['Q2 accepted identity multiset uniqueness','full source-bundle entry population','generic no-restart outside Driver journal','absolute kernel exit bound'],
  'current_host_pid_probe_used':False}
 return result
