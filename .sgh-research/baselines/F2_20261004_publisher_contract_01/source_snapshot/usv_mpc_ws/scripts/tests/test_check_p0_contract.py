"""Behavioral publisher-contract fixtures; no ROS or external package required."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import check_p0_contract as checker

NS = 1_000_000_000
TYPES = {checker.DEFAULT_TOPICS[k]:v for k,v in checker.TOPIC_TYPES.items()}

def stamp(value):
    return {"sec":value//NS,"nanosec":value%NS}

def record(role,time,payload):
    return checker.Record(checker.DEFAULT_TOPICS[role],time,payload)

def fixture(count=3):
    context={"run_id":"run-1","producer_instance_id":"producer-1","baseline_id":"F2-1","config_hash":"a"*64,
             "steady_clock_domain":"boot-id:steady_clock","frame_contract_verified":True,
             "expected_pose_frame":"world","expected_child_frame":"base_link","twist_frame":"body",
             "physical_publisher_counts":{"left":1,"right":1},"physical_match_window_ns":20_000_000,
             "frozen_baseline_verified":True,"max_source_clock_lag_ns":500_000_000,"max_source_clock_future_ns":500_000_000}
    summary={key:context[key] for key in ("run_id","producer_instance_id","baseline_id","config_hash","steady_clock_domain")}
    summary.update(schema_version="p0-contract-v1",start_steady_ns=99*NS,end_steady_ns=102*NS,normal_end=True,flushed=True,queue_dropped_total=0,
                   cycle_invocations_started=count,interrupted_cycle_sequence=0,
                   streams={role:{"generated":count,"emitted":count,"dropped":0,"first_sequence":1,"last_sequence":count}
                            for role in ("state","applied","cycle")})
    records=[]
    for index in range(count):
        seq=index+1
        sim=10*NS+index*200_000_000
        steady=100*NS+index*200_000_000
        bag=500*NS+index*200_000_000
        common={key:context[key] for key in ("run_id","producer_instance_id","baseline_id","config_hash","steady_clock_domain")}
        common.update(schema_version="p0-contract-v1",sequence=seq,clock_epoch=0,sim_time_ns=sim,
                      clock_receive_steady_ns=steady-1_000_000,clock_age_ns=1_000_000,clock_status="observed")
        state=[1.+index,2.,math.pi/2,3.,4.,.1]
        odom={"header":{"stamp":stamp(sim),"frame_id":"world"},"child_frame_id":"base_link",
              "pose":{"pose":{"position":{"x":state[0],"y":state[1],"z":0.},
                                "orientation":{"x":0.,"y":0.,"z":math.sin(math.pi/4),"w":math.cos(math.pi/4)}}},
              "twist":{"twist":{"linear":{"x":3.,"y":4.,"z":0.},"angular":{"x":0.,"y":0.,"z":.1}}}}
        imu={"header":{"stamp":stamp(sim),"frame_id":"imu_link"},"angular_velocity":{"x":0.,"y":0.,"z":.2}}
        snapshot=dict(common,received_odom_sequence=41+seq,odom_stamp_ns=sim,receive_steady_ns=steady-500_000,
                      freeze_steady_ns=steady,frame_id="world",child_frame_id="base_link",state_6=state,
                      valid=True,quality_reason="valid_numeric",source_topic=checker.DEFAULT_TOPICS["odom"])
        action=dict(common,cycle_sequence=seq,control_source="solver",event_semantics="publisher_command",
                    requested_known=True,requested_n=[3.,4.],final_n=[3.,4.],left_publish_success=True,right_publish_success=True,
                    left_publish_start_steady_ns=steady+3_000_000,left_publish_end_steady_ns=steady+3_001_000,
                    right_publish_start_steady_ns=steady+3_002_000,right_publish_end_steady_ns=steady+3_003_000,
                    left_sim_time_ns=sim,right_sim_time_ns=sim,map_scale=1.,lower_n=-25.,upper_n=25.,
                    left_clock_epoch=0,right_clock_epoch=0,left_clock_age_ns=1_000_000,right_clock_age_ns=1_000_000,
                    previous_anchor_known=index>0,previous_final_n=[3.,4.],plant_acceptance_observed=False,
                    force_measured=False,execution_atomicity_proven=False,publish_error="")
        cycle=dict(common,timer_entry_steady_ns=steady,state_copy_steady_ns=steady+500_000,
                   reference_ready_steady_ns=steady+1_000_000,solve_start_steady_ns=steady+1_100_000,
                   solve_end_steady_ns=steady+2_900_000,publish_end_steady_ns=steady+3_100_000,
                   controller_state_6=state[:5]+[.2],state_kind="controller_mixed",received_odom_sequence=41+seq,
                   received_imu_sequence=71+seq,odom_stamp_ns=sim,imu_stamp_ns=sim,backend_time_ms=1.8,
                   budget_ms=200.,success=True,deadline_miss=False,rejection_reason="",applied_sequence=seq,solve_invoked=True)
        records.extend([record("clock",bag-4_000_000,{"clock":stamp(sim)}),record("odom",bag-3_000_000,odom),
                        record("state",bag-2_500_000,snapshot),record("imu",bag-2_000_000,imu),
                        record("left",bag-1_000_000,{"data":3.}),record("right",bag-900_000,{"data":4.}),
                        record("applied",bag,action),record("cycle",bag+1_000_000,cycle),
                        record("status",bag+1_100_000,{"data":"{}"})])
    records.extend([record("path",499*NS,{"poses":[{"position":{"x":1.,"y":2.}}]}),
                    record("profile",499*NS,{"data":[1.,1.]})])
    records.sort(key=lambda r:r.bag_ns)
    return records,summary,context

def role_records(records,role):
    return [r for r in records if r.topic==checker.DEFAULT_TOPICS[role]]

def run(records,summary,context,cfg=None):
    return checker.validate_events(records,TYPES,summary,context,cfg)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.records,self.summary,self.context=fixture()

    def check_failure(self,code,records=None,summary=None,context=None):
        report,_,_=run(records or self.records,summary or self.summary,context or self.context)
        self.assertFalse(report["passed"])
        self.assertIn(code,[x["code"] for x in report["failures"]])
        return report

    def test_complete_publisher_contract_is_not_plant_certification(self):
        report,timing,ledger=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"],report["failures"])
        self.assertTrue(report["source_event_contract_valid"])
        self.assertTrue(report["recorded_stream_complete"])
        self.assertTrue(report["published_command_timing_available"])
        for key in ("gp_labels_ready","exact_execution_timing_available","force_measured","plant_acceptance_observed","execution_atomicity_proven"):
            self.assertFalse(report[key])
        self.assertEqual(timing["closed_intervals"],2)
        self.assertEqual(ledger[-1]["status"],"end_unknown")
        self.assertNotIn("bag_end",json.dumps(ledger))

    def test_repeated_constant_action_still_has_distinct_events(self):
        report,_,ledger=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"])
        self.assertEqual([r["sequence"] for r in ledger],[1,2,3])

    def test_received_sequence_does_not_have_to_start_with_logging_sequence(self):
        self.assertEqual(role_records(self.records,"state")[0].payload["received_odom_sequence"],42)
        self.assertTrue(run(self.records,self.summary,self.context)[0]["passed"])

    def test_body_twist_at_yaw_pi_over_two_is_not_rotated_again(self):
        self.assertTrue(run(self.records,self.summary,self.context)[0]["passed"])
        role_records(self.records,"state")[1].payload["state_6"][3:5]=[-4.,3.]
        self.check_failure("snapshot_not_atomic_odom")

    def test_mixed_imu_input_keeps_original_odom_and_imu_stamp(self):
        report,_,_=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"])
        role_records(self.records,"cycle")[1].payload["imu_stamp_ns"]+=1
        self.check_failure("controller_imu_source_missing")

    def test_new_odom_after_imu_can_restore_odom_r_without_erasing_last_imu_identity(self):
        for r in role_records(self.records,"cycle"):
            r.payload["state_kind"]="odom_atomic"
            r.payload["controller_state_6"][5]=.1
        self.assertTrue(run(self.records,self.summary,self.context)[0]["passed"])

    def test_postsolve_newer_state_cannot_replace_frozen_controller_input(self):
        role_records(self.records,"cycle")[0].payload["controller_state_6"][0]=99.
        self.check_failure("controller_input_not_frozen")

    def test_standby_no_solve_has_zero_source_ids_and_valid_actual_publication(self):
        r=role_records(self.records,"cycle")[1]
        r.payload.update(solve_invoked=False,state_kind="no_solve",controller_state_6=[0.]*6,
                         received_odom_sequence=0,received_imu_sequence=0,odom_stamp_ns=0,imu_stamp_ns=0,
                         state_copy_steady_ns=0,reference_ready_steady_ns=0,solve_start_steady_ns=0,solve_end_steady_ns=0,
                         backend_time_ms=0.,budget_ms=0.,success=False)
        self.assertTrue(run(self.records,self.summary,self.context)[0]["passed"])

    def test_first_armed_cycle_can_bind_recorded_prearm_raw_odom(self):
        first_cycle=role_records(self.records,"cycle")[0].payload
        old_odom=copy.deepcopy(role_records(self.records,"odom")[0].payload)
        old_stamp=9*NS+900_000_000
        old_odom["header"]["stamp"]=stamp(old_stamp)
        self.records.append(record("odom",499*NS+900_000_000,old_odom))
        self.records.sort(key=lambda r:r.bag_ns)
        first_cycle["received_odom_sequence"]=41
        first_cycle["odom_stamp_ns"]=old_stamp
        report,_,_=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"],report["failures"])
        self.assertIn("controller_snapshot_precedes_armed_window",[w["code"] for w in report["warnings"]])

    def test_postarm_missing_odom_snapshot_is_not_treated_as_prearm_exception(self):
        first_cycle=role_records(self.records,"cycle")[0].payload
        first_cycle["received_odom_sequence"]=400
        self.check_failure("controller_odom_source_missing")

    def test_prearm_and_postcapture_raw_outputs_retained_without_polluting_armed_matches(self):
        self.records.extend([record("left",499*NS,{"data":0.}),record("right",499*NS,{"data":0.}),
                             record("left",501*NS,{"data":0.}),record("right",501*NS,{"data":0.})])
        self.records.sort(key=lambda r:r.bag_ns)
        report,_,_=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"],report["failures"])
        self.assertEqual(report["physical_matching"]["left"]["outside_armed_matched_span_count"],2)

    def test_unmatched_interior_raw_output_rejected(self):
        self.records.append(record("left",500*NS+100_000_000,{"data":0.}))
        self.records.sort(key=lambda r:r.bag_ns)
        self.check_failure("physical_interior_records_unmatched")

    def test_ambiguous_equal_values_cannot_resolve_temporal_candidates(self):
        self.records.append(record("left",500*NS+2_000_000,{"data":3.}))
        self.records.sort(key=lambda r:r.bag_ns)
        self.check_failure("physical_match_missing_or_ambiguous")

    def test_wrong_raw_value_rejected_after_unique_time_match(self):
        role_records(self.records,"left")[1].payload["data"]=24.
        self.check_failure("physical_command_value_mismatch")

    def test_single_channel_loss_rejected(self):
        self.records.remove(role_records(self.records,"right")[1])
        self.check_failure("physical_match_missing_or_ambiguous")

    def test_joint_event_drop_rejected(self):
        self.records.remove(role_records(self.records,"applied")[1])
        report=self.check_failure("source_recorded_count_mismatch")
        self.assertFalse(report["recorded_stream_complete"])

    def test_common_actions_and_joint_drop_still_rejected_by_source_summary(self):
        for role in ("left","right","applied"):
            self.records.remove(role_records(self.records,role)[1])
        self.check_failure("source_recorded_count_mismatch")

    def test_common_state_action_cycle_drop_not_hidden_by_contiguous_prefix(self):
        for role in ("state","applied","cycle","left","right"):
            self.records.remove(role_records(self.records,role)[-1])
        self.check_failure("source_boundary_mismatch")

    def test_first_record_common_drop_rejected_even_if_remaining_sequence_contiguous(self):
        for role in ("state","applied","cycle","left","right"):
            self.records.remove(role_records(self.records,role)[0])
        self.check_failure("source_boundary_mismatch")

    def test_duplicate_sequence_rejected(self):
        role_records(self.records,"applied")[1].payload["sequence"]=1
        self.check_failure("sequence_gap_duplicate_or_regression")

    def test_source_restart_without_new_identity_rejected(self):
        role_records(self.records,"cycle")[2].payload["sequence"]=1
        self.check_failure("sequence_gap_duplicate_or_regression")

    def test_wrong_producer_rejected(self):
        role_records(self.records,"state")[1].payload["producer_instance_id"]="other"
        self.check_failure("source_identity_mismatch")

    def test_multiple_physical_publishers_rejected(self):
        self.context["physical_publisher_counts"]["left"]=2
        self.check_failure("physical_publisher_count")

    def test_partial_publication_invalidates_adjacent_intervals(self):
        role_records(self.records,"applied")[1].payload["right_publish_success"]=False
        self.records.remove(role_records(self.records,"right")[1])
        report,_,ledger=run(self.records,self.summary,self.context)
        self.assertIn("partial_or_failed_publication",[x["code"] for x in report["failures"]])
        self.assertEqual([r["status"] for r in ledger],["invalid","invalid","end_unknown"])

    def test_queue_overflow_rejected(self):
        self.summary["queue_dropped_total"]=1
        self.summary["streams"]["applied"]["dropped"]=1
        self.check_failure("logger_queue_overflow")

    def test_abnormal_shutdown_does_not_claim_complete(self):
        self.summary["normal_end"]=False
        report=self.check_failure("session_end_unknown_or_unflushed")
        self.assertFalse(report["recorded_stream_complete"])

    def test_interrupted_synchronous_cycle_is_not_hidden_by_recorded_counts(self):
        self.summary["cycle_invocations_started"]=4
        self.summary["interrupted_cycle_sequence"]=4
        self.check_failure("started_completed_cycle_count_mismatch")

    def test_channel_reset_mid_joint_call_prevents_interval_closure(self):
        role_records(self.records,"applied")[1].payload["right_clock_epoch"]=1
        report,_,ledger=run(self.records,self.summary,self.context)
        self.assertIn("channel_clock_epoch_mismatch",[x["code"] for x in report["failures"]])
        self.assertEqual([row["status"] for row in ledger],["invalid","invalid","end_unknown"])

    def test_unknown_steady_clock_domain_rejected(self):
        self.context["steady_clock_domain"]="unknown"
        self.check_failure("steady_domain_unknown")

    def test_clock_regression_without_epoch_rejected(self):
        for role in ("state","applied","cycle"):
            role_records(self.records,role)[1].payload["sim_time_ns"]=1*NS
        self.check_failure("unsegmented_clock_regression")

    def test_clock_epoch_change_is_never_bridged(self):
        for role in ("state","applied","cycle"):
            for r in role_records(self.records,role)[1:]:
                r.payload["clock_epoch"]=1
                if role=="applied":
                    r.payload["left_clock_epoch"]=r.payload["right_clock_epoch"]=1
        report,_,ledger=run(self.records,self.summary,self.context)
        self.assertFalse(report["published_command_timing_available"])
        self.assertEqual(ledger[0]["status"],"invalid")
        self.assertEqual(ledger[1]["status"],"closed_publisher_interval")

    def test_paused_clock_cannot_invent_physical_dt(self):
        second=role_records(self.records,"applied")[1].payload
        second["left_sim_time_ns"]=second["right_sim_time_ns"]=10*NS
        second["clock_status"]="paused"
        report,_,ledger=run(self.records,self.summary,self.context)
        self.assertFalse(report["published_command_timing_available"])
        self.assertEqual(ledger[0]["status"],"invalid")
        self.assertEqual(ledger[0]["left"]["sim_duration_s"],0.)

    def test_missing_clock_snapshot_quality_cannot_pass(self):
        r=role_records(self.records,"state")[0]
        r.payload.update(clock_status="not_received",sim_time_ns=0,clock_receive_steady_ns=0,valid=False,quality_reason="clock_missing")
        self.check_failure("invalid_snapshot")

    def test_fresh_receive_does_not_make_old_source_stamp_fresh(self):
        r=role_records(self.records,"state")[0]
        r.payload["odom_stamp_ns"]-=2*NS
        self.check_failure("source_stamp_outside_declared_clock_window")

    def test_future_source_stamp_is_not_hidden_by_fresh_receive(self):
        role_records(self.records,"state")[0].payload["odom_stamp_ns"]+=2*NS
        self.check_failure("source_stamp_outside_declared_clock_window")

    def test_source_capture_boundary_uses_steady_only(self):
        self.summary["start_steady_ns"]=101*NS
        self.check_failure("source_event_outside_capture")

    def test_missing_source_end_boundary_rejected(self):
        del self.summary["end_steady_ns"]
        self.check_failure("session_capture_boundary_unknown")

    def test_unknown_match_window_not_defaulted_to_success(self):
        del self.context["physical_match_window_ns"]
        self.check_failure("physical_match_window_unknown_or_excessive")

    def test_degenerate_quaternion_rejected(self):
        q=role_records(self.records,"odom")[1].payload["pose"]["pose"]["orientation"]
        for key in q:
            q[key]=0.
        self.check_failure("degenerate_quaternion")

    def test_nonfinite_sensor_payload_rejected(self):
        role_records(self.records,"odom")[1].payload["twist"]["twist"]["linear"]["x"]=math.nan
        self.check_failure("invalid_payload")

    def test_unknown_frames_rejected(self):
        self.context["frame_contract_verified"]=False
        self.check_failure("frame_contract_unverified")

    def test_mapping_rejects_accidental_second_scale(self):
        role_records(self.records,"applied")[0].payload["map_scale"]=25.
        self.check_failure("command_mapping_mismatch")

    def test_backend_timeout_cannot_be_success(self):
        role_records(self.records,"cycle")[0].payload["deadline_miss"]=True
        self.check_failure("late_solution_accepted")

    def test_400ms_interval_is_reported_as_actual_long_hold(self):
        # Shift all events after the first by +200ms in each declared domain.
        for r in self.records:
            if r.bag_ns>=500*NS+150_000_000:
                object.__setattr__(r,"bag_ns",r.bag_ns+200_000_000)
                p=r.payload
                if r.topic in (checker.DEFAULT_TOPICS[x] for x in ("state","applied","cycle")):
                    for k in list(p):
                        if k.endswith("steady_ns") or k in ("sim_time_ns","odom_stamp_ns","imu_stamp_ns","left_sim_time_ns","right_sim_time_ns"):
                            if p[k]: p[k]+=200_000_000
                elif r.topic==checker.DEFAULT_TOPICS["clock"]:
                    p["clock"]=stamp(checker.stamp_ns(p["clock"])+200_000_000)
                elif "header" in p:
                    p["header"]["stamp"]=stamp(checker.stamp_ns(p["header"]["stamp"])+200_000_000)
        report,timing,ledger=run(self.records,self.summary,self.context)
        self.assertTrue(report["passed"],report["failures"])
        self.assertAlmostEqual(ledger[0]["left"]["sim_duration_s"],.4)
        self.assertIn("long_publisher_hold",[w["code"] for w in report["warnings"]])
        self.assertFalse(timing["is_sensor_to_actuator_end_to_end"])

    def test_metadata_counts_checked_against_scan(self):
        cfg=checker.Config(expected_counts={topic:0 for topic in TYPES})
        report,_,_=run(self.records,self.summary,self.context,cfg)
        self.assertIn("metadata_actual_count_mismatch",[x["code"] for x in report["failures"]])

    def test_physical_claim_cannot_be_upgraded(self):
        role_records(self.records,"applied")[0].payload["force_measured"]=True
        self.check_failure("unsupported_physical_claim")

    def test_report_path_in_bag_rejected_before_reader(self):
        with tempfile.TemporaryDirectory() as td:
            bag=Path(td)/"bag"
            bag.mkdir()
            with mock.patch.object(checker,"read_bag") as read,contextlib.redirect_stderr(io.StringIO()):
                code=checker.main([str(bag),"--session-summary",str(Path(td)/"session.json"),
                                   "--run-context",str(Path(td)/"context.json"),"--output-dir",str(bag/"reports")])
            self.assertEqual(code,1)
            read.assert_not_called()

    def test_readonly_cli_hashes_original_bag_before_and_after(self):
        with tempfile.TemporaryDirectory() as td:
            bag=Path(td)/"bag";bag.mkdir()
            (bag/"metadata.yaml").write_text("readonly fixture",encoding="utf-8")
            source=Path(td)/"summary.json";source.write_text(json.dumps(self.summary),encoding="utf-8")
            context=Path(td)/"context.json";context.write_text(json.dumps(self.context),encoding="utf-8")
            output=Path(td)/"new_reports"
            before=checker.hash_bag(bag)
            with mock.patch.object(checker,"read_bag",return_value=(self.records,TYPES,{"storage_id":"mcap"})),contextlib.redirect_stdout(io.StringIO()):
                code=checker.main([str(bag),"--session-summary",str(source),"--run-context",str(context),"--output-dir",str(output)])
            self.assertEqual(code,0)
            self.assertEqual(before,checker.hash_bag(bag))
            report=json.loads((output/"contract_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["original_bag_unchanged"])
            self.assertTrue((output/"interval_ledger.jsonl").is_file())

    def test_reader_mutation_is_reported_as_failed_readonly_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            bag=Path(td)/"bag";bag.mkdir()
            (bag/"metadata.yaml").write_text("original",encoding="utf-8")
            source=Path(td)/"summary.json";source.write_text(json.dumps(self.summary),encoding="utf-8")
            context=Path(td)/"context.json";context.write_text(json.dumps(self.context),encoding="utf-8")
            output=Path(td)/"reports"
            def mutate(*args):
                (bag/"metadata.yaml").write_text("mutated",encoding="utf-8")
                return self.records,TYPES,{}
            with mock.patch.object(checker,"read_bag",side_effect=mutate),contextlib.redirect_stdout(io.StringIO()):
                code=checker.main([str(bag),"--session-summary",str(source),"--run-context",str(context),"--output-dir",str(output)])
            self.assertEqual(code,2)
            report=json.loads((output/"contract_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["original_bag_unchanged"])

if __name__=="__main__":
    unittest.main()
