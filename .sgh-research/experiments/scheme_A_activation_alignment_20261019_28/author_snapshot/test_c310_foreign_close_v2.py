#!/usr/bin/env python3
"""Finite checker mutations; no actual DDS qualification is inferred."""
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import check_c310_foreign_close_v2 as q
OG=[1]*16
FG=[2]*16

def endpoint(gid):return {'kind':'publisher','topic':q.c36.APPLIED,'type':q.c36.APPLIED_TYPE,'gid':deepcopy(gid)}
def state(n,seq):return {'command_n':deepcopy(n),'command_known':[True,True],'command_sequence':[seq,seq],'command_publish_ns':[seq*2,seq*2+1]}
def fixture():
    first=dict(sequence=1,final_n=[3.,4.],control_source='normal',plant_acceptance_observed=False,force_measured=False,execution_atomicity_proven=False)
    zero=deepcopy(first);zero.update(sequence=2,final_n=[0.,0.],control_source='shutdown_zero')
    nonzero=deepcopy(zero);nonzero['final_n']=[1.,-1.]
    messages=[first,zero,zero,nonzero,zero];rows=[]
    for i,(message,gid,ns) in enumerate(zip(messages,[OG,OG,FG,FG,FG],[10,20,40,50,60]),1):
        raw={k:0 for k in q.p.RAW_FIELDS};raw.update(schema='p1-input-callback-full-cdr-v1',topic=q.c36.APPLIED,message_type=q.c36.APPLIED_TYPE,callback_sequence=i,entry_steady_ns=ns,publisher_gid=deepcopy(gid),rmw_implementation='rmw_fastrtps_cpp',from_intra_process=False)
        rows.append(dict(type='adapter_applied_callback',raw_input=raw,sequence=message['sequence'],processed_ns=ns+1,expected_gid=deepcopy(OG),authentication_reason='' if i<=2 else 'callback_foreign_gid',queued_terminal_tail=False,owner_process_alive=i<=2))
        if i<=2:
            rows.extend([dict(type='adapter_applied_observed',sequence=message['sequence'],processed_ns=ns+1,reason='',evidence=state(message['final_n'],message['sequence'])),dict(type='legacy_anchor',sequence=message['sequence'],processed_ns=ns+1,applied=deepcopy(message),applied_text_truncated=False,final_n=deepcopy(message['final_n']),received_count=i)])
            if i==1:rows.append(dict(type='adapter_driver_close_observed',evidence=state(first['final_n'],1)))
        else:rows.append(dict(type='adapter_applied_auth_rejected',sequence=message['sequence'],processed_ns=ns+1,reason='callback_foreign_gid',anchor_after=[0.,0.],component=state([0.,0.],2)))
    rows.append(dict(type='adapter_applied_reception_closed',closed_ns=100,executor_detached=True,legacy_received=5,raw_callback_sequence=5,legacy_admitted=2))
    return rows,{q.c36.APPLIED:[{'message':deepcopy(m)} for m in messages]},{'endpoints':[endpoint(OG)]},{'endpoints':[endpoint(FG)]},messages

class AppliedPopulation(unittest.TestCase):
    def check(self,mutation=None):
        rows,decoded,pub,foreign,messages=fixture()
        if mutation:mutation(rows,decoded,pub,foreign)
        c=q.c36.Checks();out,*other=q.applied_population(rows,decoded,pub,foreign,{'requested_ns':14,'observed_ns':15},30,c,decode=lambda raw,label:deepcopy(messages[raw['callback_sequence']-1]));return c,out,other
    def test_four_colliding_sequences_retain_three_distinct_foreign_denials(self):
        c,out,other=self.check();self.assertEqual(c.issues,[]);self.assertEqual(out['foreign_received'],3);self.assertFalse(out['unique_bag_row_writer_identity_proven']);self.assertEqual([m['sequence'] for m in other[1]],[2,2,2])
    def test_missing_or_extra_identical_Storage_occurrence_rejected(self):
        for op in ('remove','add'):
            def edit(rows,d,*_):d[q.c36.APPLIED].pop() if op=='remove' else d[q.c36.APPLIED].append(deepcopy(d[q.c36.APPLIED][-1]))
            c,*_=self.check(edit);self.assertIn('entire_Storage_Applied_full_typed_occurrence_population_received',{r['code'] for r in c.issues})
    def test_native_counter_omission_rejected(self):
        c,*_=self.check(lambda rows,*_:rows[-1].update(legacy_received=4));self.assertIn('entire_Applied_callback_counter_conservation',{r['code'] for r in c.issues})
    def test_payload_sequence_cannot_replace_callback_sequence(self):
        def edit(rows,*_):
            for row in rows:
                if row['type']=='adapter_applied_callback':row['raw_input']['callback_sequence']=row['sequence']
        c,*_=self.check(edit);self.assertIn('entire_Applied_callback_sequence_not_payload_sequence',{r['code'] for r in c.issues})
    def test_manifest_owner_GID_rebinding_rejected(self):
        c,*_=self.check(lambda rows,d,p,f:f['endpoints'][0].update(gid=deepcopy(OG)));self.assertIn('independent_foreign_GID_not_original_owner',{r['code'] for r in c.issues})
    def test_unknown_actual_writer_and_boolean_gid_alias_rejected(self):
        for gid in ([3]*16,[True]*16):
            def edit(rows,*_):next(r for r in rows if r['type']=='adapter_applied_callback' and r['raw_input']['callback_sequence']==3)['raw_input']['publisher_gid']=gid
            c,*_=self.check(edit);self.assertTrue(c.issues)
    def test_foreign_zero_cannot_borrow_queued_tail_exception(self):
        def edit(rows,*_):next(r for r in rows if r['type']=='adapter_applied_callback' and r['raw_input']['callback_sequence']==3)['queued_terminal_tail']=True
        c,*_=self.check(edit);self.assertIn('actual_post_close_foreign_DataWriter_denied_at_auth_guard',{r['code'] for r in c.issues})
    def test_collision_cannot_reuse_another_rejection(self):
        def edit(rows,*_):next(r for r in rows if r['type']=='adapter_applied_auth_rejected')['processed_ns']=51
        c,*_=self.check(edit);self.assertIn('actual_post_close_foreign_DataWriter_denied_at_auth_guard',{r['code'] for r in c.issues})
    def test_denied_callback_cannot_mutate_anchor(self):
        def edit(rows,*_):next(r for r in rows if r['type']=='adapter_applied_auth_rejected')['anchor_after']=[1.,-1.]
        c,*_=self.check(edit);self.assertIn('foreign_denial_anchor_before_after_exactly_unchanged',{r['code'] for r in c.issues})
    def test_denied_callback_cannot_mutate_component_command(self):
        def edit(rows,*_):next(r for r in rows if r['type']=='adapter_applied_auth_rejected')['component']['command_sequence']=[3,3]
        c,*_=self.check(edit);self.assertIn('foreign_denial_component_command_anchor_unchanged',{r['code'] for r in c.issues})
    def test_missing_close_or_sham_exit_time_rejected(self):
        row=next(r for r in fixture()[0] if r['type']=='adapter_applied_callback' and r['raw_input']['callback_sequence']==3);rejection=dict(reason='callback_foreign_gid',sequence=2,processed_ns=41)
        for proof,close in ((True,15),(40,15),(30,False),(30,45)):self.assertFalse(q.foreign_rejection(row,rejection,OG,FG,proof,close))
    def test_illicit_anchor_with_colliding_sequence_detected(self):
        def edit(rows,*_):
            a=deepcopy(next(r for r in rows if r['type']=='legacy_anchor' and r['sequence']==2));a['processed_ns']=41;rows.insert(-1,a)
        c,*_=self.check(edit);self.assertIn('foreign_sequence_collision_never_creates_semantic_anchor_or_component_observation',{r['code'] for r in c.issues})

class TransportPopulation(unittest.TestCase):
    def check(self,mutation=None):
        topics={q.c36.APPLIED:q.c36.APPLIED_TYPE};manifests={'publisher':{'endpoints':[endpoint(OG)]},'foreign':{'endpoints':[endpoint(FG)]}};transport=[]
        for i,(gid,sha) in enumerate(zip([OG,OG,FG,FG,FG],['a'*64,'b'*64,'b'*64,'c'*64,'b'*64]),1):transport.append(dict(type='transport_message',ordinal=i,topic=q.c36.APPLIED,ros_type=q.c36.APPLIED_TYPE,publisher_gid=deepcopy(gid),payload_sha256=sha,serialization='cdr',serialized_bytes=32,receive_ns=i*10))
        raw={q.c36.APPLIED:[r['payload_sha256'] for r in transport]}
        if mutation:mutation(raw,transport,manifests,topics)
        c=q.c36.Checks();report,roles=q.multiwriter_transport(raw,transport,manifests,topics,c);return c,report,roles
    def test_identical_wire_copies_conserved_without_unique_bagrow_writer_claim(self):
        c,r,roles=self.check();self.assertEqual(c.issues,[]);self.assertEqual(len(roles['foreign']),3);self.assertFalse(r['unique_bag_row_writer_identity_proven'])
    def test_wire_order_not_only_counts(self):
        def edit(raw,*_):raw[q.c36.APPLIED][2:4]=reversed(raw[q.c36.APPLIED][2:4])
        c,*_=self.check(edit);self.assertIn('entire_multiwriter_transport_Storage_CDR_SHA_sequence',{r['code'] for r in c.issues})
    def test_third_unregistered_actual_writer_rejected(self):
        c,*_=self.check(lambda raw,tr,*_:tr[-1].update(publisher_gid=[3]*16));self.assertIn('actual_transport_type_GID_CDR_and_monotonic_observation',{r['code'] for r in c.issues})
    def test_foreign_manifest_cannot_merge_original_gid(self):
        c,*_=self.check(lambda raw,tr,m,*_:m['foreign']['endpoints'][0].update(gid=deepcopy(OG)));self.assertIn('exact_two_independent_Applied_DataWriters',{r['code'] for r in c.issues})
    def test_transport_Source_ordinal_gap_rejected(self):
        c,*_=self.check(lambda raw,tr,*_:tr[-1].update(ordinal=6));self.assertIn('entire_transport_Source_ordinal_population',{r['code'] for r in c.issues})
    def test_actual_interface_type_gid_shape_time_alias_rejected(self):
        for changes in ({'ros_type':'std_msgs/msg/String'},{'publisher_gid':[True]*16},{'receive_ns':True}):
            c,*_=self.check(lambda raw,tr,*_:tr[-1].update(changes));self.assertIn('actual_transport_type_GID_CDR_and_monotonic_observation',{r['code'] for r in c.issues})


def source_fixture():
    messages=[dict(sequence=23,control_source='shutdown_zero',final_n=[0.,0.],copied_field='original'),dict(sequence=23,control_source='shutdown_zero',final_n=[1.,-1.],copied_field='original'),dict(sequence=23,control_source='shutdown_zero',final_n=[0.,0.],copied_field='original')]
    source=[dict(type='foreign_ready',prepared_ns=45,manifest_sha256='a'*64,command_sha256='a'*64,publisher_gid=FG,execute_qualified=False,stage_qualified=False),dict(type='foreign_emit_observed',observed_ns=60,issued_ns=50,emit_sha256='a'*64,matched_subscriptions=3,command_sha256='a'*64,manifest_sha256='a'*64)]
    transport=[];callbacks=[]
    for i,(application,ns) in enumerate(zip([b'zero!',b'nonzero',b'zero!'],[70,80,90]),1):
        padding=(-len(application))%4;blob=application+b'\0'*padding
        start=dict(type='foreign_publish_start',packet_index=i,label=q.LABELS[i-1],topic=q.c36.APPLIED,ros_type=q.c36.APPLIED_TYPE,sequence=23,publisher_gid=FG,serialization='cdr',cdr_hex=blob.hex(),cdr_bytes=len(blob),payload_sha256=hashlib.sha256(blob).hexdigest(),application_cdr_hex=application.hex(),application_cdr_bytes=len(application),application_cdr_sha256=hashlib.sha256(application).hexdigest(),padding_bytes=padding,publish_start_ns=ns,final_n=messages[i-1]['final_n'],physical_publish_attempted=False,stage_qualified=False,execute_qualified=False)
        result=deepcopy(start);result.update(type='foreign_publish_result',publish_end_ns=ns+1,returned=True,error='');source.extend([start,result])
        transport.append(dict(topic=q.c36.APPLIED,publisher_gid=FG,payload_sha256=start['payload_sha256'],receive_ns=ns+3));callbacks.append({'raw_input':{'entry_steady_ns':ns+4}})
    source.append(dict(type='foreign_summary',finished_ns=100,generated=3,returned=3,expected_packets=3,normal_source_complete=True,physical_publish_attempted=False,execute_qualified=False,stage_qualified=False))
    for i,row in enumerate(source,1):row['source_ordinal']=i
    command={'original_applied_cdr_hex':b'zero!'.hex(),'original_applied_cdr_sha256':hashlib.sha256(b'zero!').hexdigest()};manifest={'endpoints':[endpoint(FG)],'created_steady_ns':40,'boot_id':'boot'}
    terminal=dict(schema='p1-C3.10-foreign-Applied-terminal-v1',run_id='run',boot_id='boot',closed_ns=101,manifest_sha256='a'*64,command_sha256='a'*64,source_sha256='a'*64,generated=3,returned=3,normal_end=True,physical_publisher_endpoints=0,execute_qualified=False,stage_qualified=False)
    return source,terminal,messages,transport,callbacks,command,manifest

class ForeignSource(unittest.TestCase):
    def check(self,mutation=None,decoder=None):
        rows,terminal,messages,transport,callbacks,command,manifest=source_fixture()
        if mutation:mutation(rows,terminal,messages,transport,callbacks,command,manifest)
        c=q.c36.Checks()
        if decoder is None:decoder=lambda row,label:deepcopy(messages[label['packet_index']-1])
        with patch.object(q.c36,'sha',return_value='a'*64):r=q.foreign_source_population(Path('/run'),{'run_id':'run'},manifest,command,{'issued_ns':50},rows,terminal,messages,callbacks,transport,30,{'observed_ns':20},c,decode=decoder)
        return c,r
    def test_whole_native_calls_wire_and_typed_closed(self):
        c,r=self.check();self.assertEqual(c.issues,[]);self.assertEqual(r['published'],3)
    def test_source_summary_cannot_claim_unpublished_repeat(self):
        c,*_=self.check(lambda rows,terminal,*_:rows[-1].update(returned=2));self.assertIn('foreign_Source_terminal_complete_call_count_conservation',{r['code'] for r in c.issues})
    def test_source_wire_digest_tamper_rejected(self):
        c,*_=self.check(lambda rows,*_:rows[2].update(payload_sha256='b'*64));self.assertIn('foreign_Source_wire_CDR_SHA_binding',{r['code'] for r in c.issues})
    def test_nonzero_clone_cannot_change_other_copied_field(self):
        c,*_=self.check(lambda rows,terminal,messages,*_:messages[1].update(copied_field='changed'));self.assertIn('exact_copied_terminal_zero_nonzero_only_final_n_and_repeat',{r['code'] for r in c.issues})
    def test_repeated_zero_transport_omission_rejected(self):
        c,*_=self.check(lambda rows,terminal,messages,tr,*_:tr.pop());self.assertIn('entire_foreign_Source_actual_GID_transport_wire_CDR_occurrence_population',{r['code'] for r in c.issues})
    def test_pre_exit_emit_or_incomplete_actual_discovery_rejected(self):
        for change in ({'observed_ns':25},{'matched_subscriptions':2},{'matched_subscriptions':True}):
            c,*_=self.check(lambda rows,*_:rows[1].update(change));self.assertIn('actual_foreign_emit_after_owner_reap_and_finite_native_discovery',{r['code'] for r in c.issues})
    def test_native_terminal_manifest_rebinding_rejected(self):
        c,*_=self.check(lambda rows,terminal,*_:terminal.update(manifest_sha256='b'*64));self.assertIn('foreign_native_terminal_complete_Source_manifest_command_binding',{r['code'] for r in c.issues})
    def test_native_failed_publish_or_physical_attempt_rejected(self):
        for change in ({'returned':False},{'physical_publish_attempted':True}):
            c,*_=self.check(lambda rows,*_:rows[3].update(change));self.assertIn('actual_foreign_full_Source_start_result_packet_binding',{r['code'] for r in c.issues})
    def test_native_packet_index_cannot_use_colliding_payload_sequence(self):
        c,*_=self.check(lambda rows,*_:rows[4].update(packet_index=23));self.assertIn('actual_foreign_full_Source_start_result_packet_binding',{r['code'] for r in c.issues})
    def test_native_CDR_size_boolean_alias_rejected(self):
        c,*_=self.check(lambda rows,*_:rows[2].update(cdr_bytes=True));self.assertIn('foreign_Source_wire_CDR_SHA_binding',{r['code'] for r in c.issues})
    def test_application_and_submission_are_separately_recorded(self):
        c,r=self.check();self.assertEqual(c.issues,[]);self.assertEqual(r['explicit_padding_bytes'],[3,1,3]);self.assertNotEqual(r['cloned_zero_application_SHA'],r['cloned_zero_submitted_SHA'])
    def test_missing_application_or_padding_fields_rejected(self):
        for field in ('application_cdr_hex','application_cdr_bytes','application_cdr_sha256','padding_bytes'):
            c,*_=self.check(lambda rows,*_:rows[2].pop(field));self.assertIn('foreign_Source_explicit_zero_padding_before_submission_exact_bytes',{r['code'] for r in c.issues})
    def test_application_CDR_digest_and_exact_integer_size_rejected(self):
        for change in ({'application_cdr_sha256':'b'*64},{'application_cdr_bytes':True},{'application_cdr_bytes':5.}):
            c,*_=self.check(lambda rows,*_:rows[2].update(change));self.assertIn('foreign_Source_application_CDR_SHA_binding',{r['code'] for r in c.issues})
    def test_Source_padding_boolean_float_and_incorrect_length_rejected(self):
        for pad in (True,3.,2,4):
            c,*_=self.check(lambda rows,*_:rows[2].update(padding_bytes=pad));self.assertIn('foreign_Source_explicit_zero_padding_before_submission_exact_bytes',{r['code'] for r in c.issues})
    def test_zero_append_rule_still_rejects_wire_tamper_with_valid_digest(self):
        def edit(rows,terminal,messages,transport,*_):
            for row in rows[2:4]:
                blob=bytes.fromhex(row['cdr_hex'])[:-1]+b'x';row.update(cdr_hex=blob.hex(),payload_sha256=hashlib.sha256(blob).hexdigest())
            transport[0]['payload_sha256']=rows[2]['payload_sha256']
        c,*_=self.check(edit);self.assertIn('foreign_Source_explicit_zero_padding_before_submission_exact_bytes',{r['code'] for r in c.issues})
    def test_both_application_and_submitted_full_typed_decode_must_agree(self):
        messages=source_fixture()[2]
        def decode(row,label):
            message=deepcopy(messages[label['packet_index']-1])
            if 'packet_index' not in row:message['copied_field']='changed'
            return message
        c,*_=self.check(decoder=decode);self.assertIn('foreign_Source_application_and_submission_full_typed_equal',{r['code'] for r in c.issues})
    def test_command_template_binds_application_before_explicit_padding(self):
        def edit(rows,terminal,messages,transport,callbacks,command,*_):
            command.update(original_applied_cdr_hex=rows[2]['cdr_hex'],original_applied_cdr_sha256=rows[2]['payload_sha256'])
        c,*_=self.check(edit);self.assertIn('exact_copied_terminal_zero_nonzero_only_final_n_and_repeat',{r['code'] for r in c.issues})
    def test_transport_SHA_remains_exact_submitted_bytes_not_application(self):
        def edit(rows,terminal,messages,transport,*_):transport[0]['payload_sha256']=rows[2]['application_cdr_sha256']
        c,*_=self.check(edit);self.assertIn('entire_foreign_Source_actual_GID_transport_wire_CDR_occurrence_population',{r['code'] for r in c.issues})
    def test_start_result_application_metadata_divergence_rejected(self):
        c,*_=self.check(lambda rows,*_:rows[3].update(application_cdr_sha256='b'*64));self.assertIn('actual_foreign_full_Source_start_result_packet_binding',{r['code'] for r in c.issues})

class CommandBindings(unittest.TestCase):
    def check(self,mutation=None):
        run=Path('/run');peer={'driver':{'pid':12,'start_ticks':123},'driver_tool_sha256':'driver'};pub={'boot_id':'boot','contract_sha256':'original-contract'}
        command=dict(schema='p1-C3.10-foreign-Applied-command-v1',run_id='run',boot_id='boot',original_owner_manifest_sha256='a'*64,driver_pid=12,driver_start_ticks=123,driver_tool_sha256='driver',close_request_sha256='a'*64,close_observed_ns=20,owner_exit_proof_sha256='a'*64,original_applied_cdr_hex='abcd',original_applied_cdr_sha256='a'*64)
        emit=dict(schema='p1-C3.10-foreign-Applied-emit-v1',run_id='run',boot_id='boot',driver_pid=12,driver_start_ticks=123,driver_tool_sha256='driver',command_sha256='a'*64,foreign_manifest_sha256='a'*64,issued_ns=50)
        values=dict(run_id='run',contract_file=str(q.HERE/'foreign/foreign_contract_v2.json'),contract_sha256='a'*64,output_dir='/run/foreign',command_file='/run/foreign/command.json',command_sha256='a'*64,emit_file='/run/foreign/emit.json')
        foreign=dict(effective_parameters={k:{'value':v} for k,v in values.items()},contract_sha256='a'*64,command_file='/run/foreign/command.json',command_sha256='a'*64,independent_contract_file=values['contract_file'],diagnostic_only=True,physical_publisher_endpoints=0)
        if mutation:mutation(command,emit,foreign)
        c=q.c36.Checks()
        with patch.object(q.c36,'sha',return_value='a'*64):q.command_binding(run,{'run_id':'run'},peer,pub,foreign,command,emit,{'proof_ns':30},{'observed_ns':20},c)
        return c
    def test_current_owner_close_exit_driver_and_separate_contract_bound(self):self.assertEqual(self.check().issues,[])
    def test_sham_close_or_proof_reference_rejected(self):
        for change in ({'close_request_sha256':'b'*64},{'owner_exit_proof_sha256':'b'*64},{'close_observed_ns':21}):
            c=self.check(lambda command,*_:command.update(change));self.assertIn('foreign_command_exact_original_owner_actual_close_exit_driver_binding',{r['code'] for r in c.issues})
    def test_rebound_driver_or_boolean_process_fields_rejected(self):
        for change in ({'driver_pid':True},{'driver_pid':12.0},{'driver_start_ticks':123.0},{'driver_start_ticks':124},{'driver_tool_sha256':'other'}):
            c=self.check(lambda command,*_:command.update(change));self.assertIn('foreign_command_exact_original_owner_actual_close_exit_driver_binding',{r['code'] for r in c.issues})
    def test_emit_cannot_rebind_foreign_manifest_or_issued_before_owner_reap(self):
        for change in ({'foreign_manifest_sha256':'b'*64},{'issued_ns':25},{'issued_ns':True}):
            c=self.check(lambda command,emit,*_:emit.update(change));self.assertIn('foreign_emit_exact_independent_manifest_current_driver_command_binding',{r['code'] for r in c.issues})
    def test_native_config_cannot_rebind_command_path(self):
        def edit(command,emit,foreign):foreign['effective_parameters']['command_file']['value']='/some/other/command.json'
        c=self.check(edit);self.assertIn('foreign_separate_diagnostic_contract_concrete_effective_input_sources',{r['code'] for r in c.issues})
    def test_diagnostic_cannot_claim_physical_authority(self):
        c=self.check(lambda command,emit,foreign:foreign.update(physical_publisher_endpoints=1));self.assertIn('foreign_separate_diagnostic_contract_concrete_effective_input_sources',{r['code'] for r in c.issues})


class LateActualGraph(unittest.TestCase):
    def check(self,mutation=None):
        topics={q.c36.APPLIED:q.c36.APPLIED_TYPE};manifests={'publisher':{'node':'/original','endpoints':[endpoint(OG)]},'foreign':{'node':'/foreign','endpoints':[endpoint(FG)]}}
        graph={'observed_ns':45,'topics':{q.c36.APPLIED:{'publishers':[dict(node='/foreign',type=q.c36.APPLIED_TYPE,gid=deepcopy(FG)),dict(node='/original',type=q.c36.APPLIED_TYPE,gid=deepcopy(OG))],'subscriptions':[]}}}
        if mutation:mutation(graph,manifests)
        c=q.c36.Checks();report=q.late_graph_population(graph,manifests,topics,{'checked_ns':40},{'issued_ns':50},30,c);return c,report
    def test_one_actual_snapshot_preserves_old_endpoint_exit_unknown(self):
        c,r=self.check();self.assertEqual(c.issues,[]);self.assertEqual(r['original_owner_endpoint_exit'],'unknown')
    def test_stale_original_endpoint_presence_or_absence_does_not_prove_exit(self):
        c,*_=self.check(lambda g,*_:g['topics'][q.c36.APPLIED]['publishers'].pop());self.assertEqual(c.issues,[])
    def test_unknown_third_writer_rejected(self):
        def edit(g,*_):g['topics'][q.c36.APPLIED]['publishers'].append(dict(node='/stranger',type=q.c36.APPLIED_TYPE,gid=[3]*16))
        c,*_=self.check(edit);self.assertIn('late_graph_entire_actual_endpoint_population_registered_and_typed',{r['code'] for r in c.issues})
    def test_foreign_node_name_cannot_replace_actual_gid(self):
        def edit(g,*_):g['topics'][q.c36.APPLIED]['publishers'][0]['gid']=deepcopy(OG)
        c,*_=self.check(edit);self.assertTrue(c.issues)
    def test_foreign_endpoint_missing_or_duplicate_rejected(self):
        for duplicate in (False,True):
            def edit(g,*_):
                rows=g['topics'][q.c36.APPLIED]['publishers'];rows.append(deepcopy(rows[0])) if duplicate else rows.pop(0)
            c,*_=self.check(edit);self.assertIn('late_graph_actual_live_native_endpoint_present_once',{r['code'] for r in c.issues})
    def test_sham_pre_authentication_graph_or_boolean_timestamp_rejected(self):
        for ns in (35,True,51):
            c,*_=self.check(lambda g,*_:g.update(observed_ns=ns));self.assertIn('late_graph_actual_post_reap_authenticated_pre_emit_finite_observation',{r['code'] for r in c.issues})


class ExplicitSubmittedBytes(unittest.TestCase):
    def record(self,blob):return {'hex':blob.hex(),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}
    def test_each_application_alignment_residue_has_exact_explicit_zero_append(self):
        for size in range(4,8):
            app=b'a'*size;pad=(-size)%4;self.assertTrue(q.explicit_submission_relation(self.record(app),self.record(app+b'\0'*pad),pad))
    def test_internal_byte_mutation_never_authorized_as_padding(self):
        self.assertFalse(q.explicit_submission_relation(self.record(b'abcde'),self.record(b'abXde\0\0\0'),3))
    def test_nonzero_suffix_never_authorized(self):
        self.assertFalse(q.explicit_submission_relation(self.record(b'abcde'),self.record(b'abcde\0\0x'),3))
    def test_missing_or_excess_zero_suffix_not_silently_stripped(self):
        for submitted in (b'abcde\0\0',b'abcde\0\0\0\0',b'abcd'):
            self.assertFalse(q.explicit_submission_relation(self.record(b'abcde'),self.record(submitted),3))
    def test_boolean_float_and_out_of_range_padding_fields_rejected(self):
        for pad in (True,3.,-1,4,0):self.assertFalse(q.explicit_submission_relation(self.record(b'abcde'),self.record(b'abcde\0\0\0'),pad))
    def test_declared_application_or_submission_sha_mismatch_rejected(self):
        for which in (0,1):
            values=[self.record(b'abcde'),self.record(b'abcde\0\0\0')];values[which]['sha256']='a'*64
            self.assertFalse(q.explicit_submission_relation(*values,3))
    def test_declared_byte_lengths_are_exact_integer_and_complete(self):
        for which in (0,1):
            for size in (True,5.,4,9):
                values=[self.record(b'abcde'),self.record(b'abcde\0\0\0')];values[which]['bytes']=size
                self.assertFalse(q.explicit_submission_relation(*values,3))
    def test_application_or_submission_field_population_exact(self):
        for which in (0,1):
            values=[self.record(b'abcde'),self.record(b'abcde\0\0\0')];values[which]['extra']='ignored'
            self.assertFalse(q.explicit_submission_relation(*values,3))
    def test_empty_or_oversized_application_and_submission_fail_closed(self):
        for app in (b'',b'a'*8193):
            pad=(-len(app))%4;self.assertFalse(q.explicit_submission_relation(self.record(app),self.record(app+b'\0'*pad),pad))
    def test_uppercase_odd_or_invalid_hex_never_normalized(self):
        for text in ('ABCD','abc','invalid'):
            app=self.record(b'abcde');app['hex']=text
            self.assertFalse(q.explicit_submission_relation(app,self.record(b'abcde\0\0\0'),3))


class ExplicitSubmissionContract(unittest.TestCase):
    def fixture(self):return {'schema':'p1-C3.10-foreign-Applied-contract-v2','topic':q.c36.APPLIED,'ros_type':q.c36.APPLIED_TYPE,'packet_labels':deepcopy(q.LABELS),'max_packets':3,'max_cdr_bytes':8192,'nonzero_final_n':[1.,-1.],'physical_publisher_endpoints':0,'stage_qualified':False,'execute_qualified':False,'submission_alignment_bytes':4,'submission_padding_policy':'explicit-zero-fill-before-native-publish'}
    def check(self,mutation=None):
        value=self.fixture()
        if mutation:mutation(value)
        c=q.c36.Checks();q.foreign_contract_configuration(value,c);return c
    def test_exact_v2_contract_policy_bound(self):self.assertEqual(self.check().issues,[])
    def test_old_contract_or_wrong_padding_policy_rejected(self):
        for value in ({'schema':'p1-C3.10-foreign-Applied-contract-v1'},{'submission_padding_policy':'strip-padding-after-receive'},{'submission_alignment_bytes':8}):self.assertTrue(self.check(lambda d:d.update(value)).issues)
    def test_boolean_float_integer_aliases_rejected(self):
        for value in ({'submission_alignment_bytes':True},{'submission_alignment_bytes':4.},{'physical_publisher_endpoints':False},{'nonzero_final_n':[1,-1]}):self.assertTrue(self.check(lambda d:d.update(value)).issues)
    def test_missing_extra_fields_and_execution_authority_rejected(self):
        for mutation in (lambda d:d.pop('submission_padding_policy'),lambda d:d.update(extra='ignored'),lambda d:d.update(stage_qualified=True),lambda d:d.update(execute_qualified=True)):self.assertTrue(self.check(mutation).issues)


class CheckerDependencyPins(unittest.TestCase):
    def check(self,mutation=None):
        with TemporaryDirectory(prefix='c310-v2-dependencies-') as tmp:
            here=Path(tmp)/'author';run=Path(tmp)/'run';run.mkdir();inputs={'tool_sha256':{}}
            for index,rel in enumerate(q.DEPENDENCIES):
                dep=here/rel;dep.parent.mkdir(parents=True,exist_ok=True);dep.write_bytes(('dependency '+str(index)).encode())
                inputs['tool_sha256'][rel]=hashlib.sha256(dep.read_bytes()).hexdigest();(run/(rel.replace('/','__')+'.snapshot')).write_bytes(dep.read_bytes())
            if mutation:mutation(here,run,inputs)
            c=q.c36.Checks();deps=q.checker_dependency_population(run,inputs,c,here=here);return c,[p.name for p in deps]
    def test_v2_checker_test_driver_and_all_read_dependencies_required(self):
        c,names=self.check();self.assertEqual(c.issues,[])
        for name in ('check_c310_foreign_close_v2.py','test_c310_foreign_close_v2.py','prepare_fixture_v2.py'):self.assertIn(name,names)
    def test_current_checker_modified_after_prerun_snapshot_rejected(self):
        c,*_=self.check(lambda here,*_:(here/'check_c310_foreign_close_v2.py').write_bytes(b'changed'));self.assertTrue(c.issues)
    def test_v2_test_snapshot_must_exist_before_check(self):
        c,*_=self.check(lambda here,run,*_:(run/'test_c310_foreign_close_v2.py.snapshot').unlink());self.assertTrue(c.issues)
    def test_v1_driver_pin_cannot_replace_v2_executed_driver(self):
        def edit(here,run,inputs):inputs['tool_sha256']['prepare_fixture.py']=inputs['tool_sha256'].pop('prepare_fixture_v2.py')
        c,*_=self.check(edit);self.assertTrue(c.issues)
    def test_v2_driver_snapshot_bytes_must_match_current_and_input_SHA(self):
        c,*_=self.check(lambda here,run,*_:(run/'prepare_fixture_v2.py.snapshot').write_bytes(b'changed'));self.assertTrue(c.issues)
    def test_dependency_input_SHA_omission_or_tamper_rejected(self):
        for mutation in (lambda here,run,inputs:inputs['tool_sha256'].pop('check_c39_worker_close.py'),lambda here,run,inputs:inputs['tool_sha256'].update({'check_c39_worker_close.py':'b'*64})):
            c,*_=self.check(mutation);self.assertTrue(c.issues)

if __name__=='__main__':unittest.main()
