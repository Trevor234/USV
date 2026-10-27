#!/usr/bin/env python3
"""Ownership exclusions never grant signals or mask a new inaccessible PID."""
import copy
import hashlib
from types import SimpleNamespace
import unittest
from unittest import mock
import run_p1_vrx_validation as vrx


class ExistingEnvironmentRisks(unittest.TestCase):
    def tree(self):
        t=object.__new__(vrx.OwnedTree)
        t.env={"ROS_DOMAIN_ID":"97","GZ_PARTITION":"p1_unique"}
        t.tracked={};t.root_pids=set()
        ident={"pid":42,"state":"S","start_ticks":123,"ppid":1,"pgid":42,"sid":42}
        t.preexisting_unreadable={42:{**ident,"uid":1000,"cmdline_sha256":hashlib.sha256(b"ssh-agent").hexdigest()}}
        return t,ident

    def observe(self,t,ident,command=b"ssh-agent",uid=1000):
        with mock.patch.object(vrx.Path,"read_bytes",side_effect=[PermissionError("env"),command]), \
             mock.patch.object(vrx.Path,"stat",return_value=SimpleNamespace(st_uid=uid)), \
             mock.patch.object(vrx.os,"getuid",return_value=1000,create=True), \
             mock.patch.object(vrx,"proc_identity",return_value=ident):
            return t.scoped(42)

    def test_unchanged_preexisting_unreadable_identity_is_observation_only(self):
        t,ident=self.tree()
        self.assertFalse(self.observe(t,ident))
        self.assertEqual(t.tracked,{})
        self.assertEqual(t.root_pids,set())
        self.assertEqual(len(t.preexisting_unreadable),1)

    def test_new_same_uid_inaccessible_pid_fails(self):
        t,ident=self.tree();t.preexisting_unreadable.clear()
        with self.assertRaises(PermissionError):self.observe(t,ident)

    def test_tracked_owned_pid_cannot_use_preexisting_exclusion(self):
        t,ident=self.tree();t.tracked[42]=copy.deepcopy(ident)
        with self.assertRaises(PermissionError):self.observe(t,ident)

    def test_pid_reuse_and_parent_session_change_fail(self):
        for key in ["start_ticks","ppid","pgid","sid"]:
            with self.subTest(field=key):
                t,ident=self.tree();ident[key]+=1
                with self.assertRaises(PermissionError):self.observe(t,ident)

    def test_changed_command_cannot_use_old_identity_exclusion(self):
        t,ident=self.tree()
        with self.assertRaises(PermissionError):self.observe(t,ident,b"p1_solver_worker")

    def test_other_uid_remains_unowned_and_unsignalled(self):
        t,ident=self.tree()
        self.assertFalse(self.observe(t,ident,uid=0))
        self.assertEqual(t.tracked,{})

    def test_readable_scope_requires_both_domain_and_partition(self):
        t,_=self.tree()
        for env,expected in [(b"ROS_DOMAIN_ID=97\0GZ_PARTITION=p1_unique\0",True),
                             (b"ROS_DOMAIN_ID=97\0GZ_PARTITION=external\0",False),
                             (b"ROS_DOMAIN_ID=96\0GZ_PARTITION=p1_unique\0",False)]:
            with self.subTest(env=env),mock.patch.object(vrx.Path,"read_bytes",return_value=env):
                self.assertEqual(t.scoped(42),expected)

    def test_each_parameter_dump_has_bounded_independent_discovery(self):
        import ast,inspect,textwrap
        function=ast.parse(textwrap.dedent(inspect.getsource(vrx.run)))
        dumps=[n for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
               and n.func.id=="command" and len(n.args)>=3 and isinstance(n.args[1],ast.List)
               and n.args[1].elts and isinstance(n.args[1].elts[0],ast.Constant) and n.args[1].elts[0].value=="param"]
        self.assertEqual(len(dumps),3)
        for call in dumps:
            constants=[n.value for n in call.args[1].elts if isinstance(n,ast.Constant)]
            self.assertIn("--no-daemon",constants)
            for flag,value in [("--spin-time","3"),("--timeout","10")]:
                self.assertEqual(constants[constants.index(flag)+1],value)
            self.assertEqual(call.args[2].value,20)

    def test_prelaunch_context_does_not_access_uncreated_owned_tree(self):
        import ast,inspect,textwrap
        function=ast.parse(textwrap.dedent(inspect.getsource(vrx.run))).body[0]
        contexts=[n for n in function.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=="context" for t in n.targets)]
        self.assertEqual(len(contexts),1)
        loads={n.id for n in ast.walk(contexts[0].value) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
        self.assertNotIn("tree",loads)

    def test_constructor_records_unknown_environment_without_granting_ownership(self):
        t,ident=self.tree();supervisor=mock.Mock()
        with mock.patch.object(vrx,"proc_table",return_value=[ident]), \
             mock.patch.object(vrx.Path,"stat",return_value=SimpleNamespace(st_uid=1000)), \
             mock.patch.object(vrx.os,"getuid",return_value=1000,create=True), \
             mock.patch.object(vrx.Path,"read_bytes",side_effect=[PermissionError("env"),b"ssh-agent"]):
            actual=vrx.OwnedTree(supervisor,t.env)
        self.assertEqual(actual.tracked,{})
        self.assertEqual(actual.root_pids,set())
        self.assertIn(42,actual.preexisting_unreadable)
        args,kwargs=supervisor.event.call_args
        self.assertEqual(args,("preexisting_environment_unreadable",))
        self.assertFalse(kwargs["ownership_granted"])
        self.assertFalse(kwargs["environment_scope_known"])


class PhysicalDiscoveryRisks(unittest.TestCase):
    def probe(self,endpoints,returncode=None):
        import ast,inspect,textwrap
        parsed=ast.parse(textwrap.dedent(inspect.getsource(vrx.run)))
        function=next(n for n in ast.walk(parsed) if isinstance(n,ast.FunctionDef) and n.name=="legacy_physical_identity_ready")
        node=mock.Mock();node.get_publishers_info_by_topic.side_effect=lambda t:endpoints.get(t,[])
        legacy=mock.Mock();legacy.process.poll.return_value=returncode
        namespace={"legacy":legacy,"node":node,"physical_owner":"mpc_controller_node", "c":{"output_topics":{"left":"left","right":"right"}}}
        exec(compile(ast.Module(body=[function],type_ignores=[]),"actual_discovery_gate","exec"),namespace)
        return namespace[function.name]()

    def endpoint(self,name="mpc_controller_node",kind="std_msgs/msg/Float64"):
        return SimpleNamespace(node_name=name,topic_type=kind)

    def test_missing_or_unknown_identity_waits_without_granting_ownership(self):
        self.assertFalse(self.probe({"left":[self.endpoint("_NODE_NAME_UNKNOWN_")],"right":[self.endpoint()]}))
        self.assertFalse(self.probe({"left":[self.endpoint()]}))

    def test_both_actual_named_single_owners_are_ready(self):
        self.assertTrue(self.probe({"left":[self.endpoint()],"right":[self.endpoint()]}))

    def test_extra_foreign_or_wrong_type_is_immediate_failure(self):
        for left in [[self.endpoint(),self.endpoint()], [self.endpoint("foreign")], [self.endpoint(kind="std_msgs/msg/String")]]:
            with self.subTest(left=left),self.assertRaises(RuntimeError):
                self.probe({"left":left,"right":[self.endpoint()]})

    def test_owned_legacy_exit_is_not_discovery_readiness(self):
        with self.assertRaises(RuntimeError):self.probe({"left":[self.endpoint()],"right":[self.endpoint()]},127)


class ParameterDocumentRisks(unittest.TestCase):
    def test_warning_prefix_preserved_outside_exact_parameter_body(self):
        raw="[WARN] rcl deprecation\n/node:\n  ros__parameters:\n    Q: [20.0, 20.0]\n    label: '[WARN] literal value'\n"
        p,body=vrx.parameter_dump_document(raw,"/node")
        self.assertEqual(p,{"Q":[20.0,20.0],"label":"[WARN] literal value"})
        self.assertTrue(body.startswith("/node:"))
        self.assertIn("[WARN] rcl deprecation",raw)

    def test_missing_duplicate_and_foreign_header_rejected(self):
        for raw in ["Node not found\n", "/other:\n  ros__parameters: {}\n", "/node:\n  ros__parameters: {}\n/node:\n  ros__parameters: {}\n"]:
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):vrx.parameter_dump_document(raw,"/node")

    def test_extra_root_or_malformed_parameter_mapping_rejected(self):
        for raw in ["/node:\n  ros__parameters: {}\n/other: {}\n", "/node:\n  ros__parameters: []\n", "/node:\n  other: {}\n"]:
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):vrx.parameter_dump_document(raw,"/node")

    def test_diagnostics_inside_body_are_not_arbitrarily_stripped(self):
        import yaml
        with self.assertRaises(yaml.YAMLError):vrx.parameter_dump_document("/node:\n  ros__parameters: {}\n[WARN] corrupt trailing text\n","/node")


if __name__=="__main__":
    unittest.main()
