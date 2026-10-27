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


if __name__=="__main__":
    unittest.main()
