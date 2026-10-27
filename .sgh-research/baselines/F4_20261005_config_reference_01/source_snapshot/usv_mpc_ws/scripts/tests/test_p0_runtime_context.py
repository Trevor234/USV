"""Graph readiness must reject identity/type pollution before capture is armed."""

import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "capture_p0_runtime_context.py"
SPEC = importlib.util.spec_from_file_location("p0_runtime_context", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def endpoint(name, topic_type):
    return {"node_name": name, "topic_type": topic_type}


def valid_graph():
    graph = {}
    for topic, topic_type in MODULE.DEFAULT_TYPES.items():
        if topic.startswith("/research/") or "/thrusters/" in topic:
            publisher = "mpc_controller_node"
        else:
            publisher = "bridge_or_planner"
        graph[topic] = {
            "expected_type": topic_type,
            "publishers": [endpoint(publisher, topic_type)],
            "subscriptions": [endpoint("rosbag2_recorder", topic_type)],
        }
    return graph


class GraphReadinessTests(unittest.TestCase):
    def gate(self, graph):
        return MODULE.graph_gate(graph, "/wamv/thrusters/left/thrust",
                                 "/wamv/thrusters/right/thrust", "mpc_controller_node")

    def test_one_original_controller_and_recorder_is_ready(self):
        self.assertEqual(self.gate(valid_graph()), [])

    def test_unrelated_subscriber_does_not_substitute_for_recorder(self):
        graph = valid_graph()
        topic = "/research/cycle_timing"
        graph[topic]["subscriptions"] = [endpoint("plotter", graph[topic]["expected_type"])]
        self.assertIn("recorder_subscription_count:" + topic + ":0", self.gate(graph))

    def test_second_physical_publisher_rejects_capture(self):
        graph = valid_graph()
        topic = "/wamv/thrusters/left/thrust"
        graph[topic]["publishers"].append(endpoint("other_controller", "std_msgs/msg/Float64"))
        self.assertIn("physical_publisher_identity:" + topic, self.gate(graph))

    def test_second_recorder_rejects_ambiguous_count_proof(self):
        graph = valid_graph()
        topic = "/research/control/applied"
        graph[topic]["subscriptions"].append(endpoint("rosbag2_recorder_2", graph[topic]["expected_type"]))
        self.assertIn("recorder_subscription_count:" + topic + ":2", self.gate(graph))

    def test_wrong_research_publisher_and_type_rejected(self):
        graph = valid_graph()
        topic = "/research/state_snapshot"
        graph[topic]["publishers"] = [endpoint("stale_replay", "std_msgs/msg/String")]
        errors = self.gate(graph)
        self.assertIn("research_publisher_identity:" + topic, errors)
        self.assertIn("unexpected_type:" + topic, errors)

    def test_missing_clock_or_recorder_type_rejected(self):
        graph = valid_graph()
        graph["/clock"]["publishers"] = []
        graph["/clock"]["subscriptions"][0]["topic_type"] = "std_msgs/msg/Float64"
        errors = self.gate(graph)
        self.assertIn("publisher_missing:/clock", errors)
        self.assertIn("recorder_type_mismatch:/clock", errors)


if __name__ == "__main__":
    unittest.main()
