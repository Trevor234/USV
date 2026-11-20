"""Topic contract parser and dynamic rosbag QoS override generator.

This module treats `topic_contract.yaml` as the Single Source of Truth (SSOT).
It extracts recording candidate topics and generates rosbag2 QoS overrides
dynamically, eliminating the need to manually maintain redundant YAML lists.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


def load_topic_contract(path: Path | str) -> dict[str, Any]:
    """Load topic contract YAML file safely."""
    contract_path = Path(path).resolve()
    if not contract_path.is_file():
        raise FileNotFoundError(f"Topic contract file not found: {contract_path}")
    with contract_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Topic contract root must be a YAML mapping: {contract_path}")
    return data


def extract_topics(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Recursively discover all topic entries declared in the contract.

    Merges attributes when the same topic is referenced in multiple sections
    (e.g., published by one node and subscribed by another).
    """
    topics: dict[str, dict[str, Any]] = {}

    def _traverse(node: Any) -> None:
        if isinstance(node, dict):
            if "topic" in node and isinstance(node["topic"], str) and node["topic"].startswith("/"):
                t_name = node["topic"]
                if t_name not in topics:
                    topics[t_name] = {}
                # Merge keys, prioritising truthy/explicit values
                for k, v in node.items():
                    if k == "record" and v is True:
                        topics[t_name]["record"] = True
                    elif k not in topics[t_name] or not topics[t_name][k]:
                        topics[t_name][k] = v
            for val in node.values():
                _traverse(val)
        elif isinstance(node, list):
            for item in node:
                _traverse(item)

    _traverse(contract)
    return topics


def parse_qos_override(qos_spec: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse a QoS specification string or dict into a rosbag2 override dict.

    Only returns an override dict for topics requiring non-default rosbag2
    subscription parameters (primarily BEST_EFFORT and custom depths).
    Returns None for standard reliable topics.
    """
    if not qos_spec:
        return None

    if isinstance(qos_spec, dict):
        reliability = str(qos_spec.get("reliability", "best_effort")).lower()
        if reliability == "best_effort":
            return {
                "reliability": "best_effort",
                "durability": str(qos_spec.get("durability", "volatile")).lower(),
                "history": str(qos_spec.get("history", "keep_last")).lower(),
                "depth": int(qos_spec.get("depth", 5)),
            }
        return None

    if isinstance(qos_spec, str):
        text = qos_spec.lower()
        if "sensor_data" in text:
            depth_match = re.search(r"depth=(\d+)", text)
            depth = int(depth_match.group(1)) if depth_match else 5
            return {
                "reliability": "best_effort",
                "durability": "volatile",
                "history": "keep_last",
                "depth": depth,
            }
        if "best_effort" in text:
            depth_match = re.search(r"depth=(\d+)", text)
            depth = int(depth_match.group(1)) if depth_match else 5
            durability = "transient_local" if "transient_local" in text else "volatile"
            history = "keep_all" if "keep_all" in text else "keep_last"
            return {
                "reliability": "best_effort",
                "durability": durability,
                "history": history,
                "depth": depth,
            }

    return None


def get_record_topics(contract_path: Path | str) -> list[str]:
    """Return all topics explicitly marked with `record: true` in the contract."""
    contract = load_topic_contract(contract_path)
    discovered = extract_topics(contract)
    return sorted(t for t, spec in discovered.items() if spec.get("record") is True)


def generate_qos_overrides(
    contract_path: Path | str,
    target_topics: list[str] | set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Generate rosbag2 QoS overrides dictionary from the topic contract.

    If target_topics is specified, only returns overrides for topics in target_topics.
    Otherwise, evaluates all topics marked for recording.
    """
    contract = load_topic_contract(contract_path)
    discovered = extract_topics(contract)

    if target_topics is not None:
        candidate_topics = set(target_topics)
    else:
        candidate_topics = {t for t, spec in discovered.items() if spec.get("record") is True}

    overrides: dict[str, dict[str, Any]] = {}
    for topic in sorted(candidate_topics):
        spec = discovered.get(topic)
        if not spec:
            continue
        qos_dict = parse_qos_override(spec.get("qos"))
        if qos_dict is not None:
            overrides[topic] = qos_dict

    return overrides


def write_derived_qos_file(
    contract_path: Path | str,
    output_path: Path | str,
    target_topics: list[str] | set[str] | None = None,
) -> Path:
    """Generate and write the QoS overrides YAML file to output_path."""
    overrides = generate_qos_overrides(contract_path, target_topics=target_topics)
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# ---------------------------------------------------------------------------\n"
        "# 自动生成文件: 由 topic_contract.yaml 动态派生\n"
        "# 严禁手动修改此文件，增改传感器请直接编辑 topic_contract.yaml\n"
        "# ---------------------------------------------------------------------------\n"
    )
    with out_file.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(overrides, f, sort_keys=True, allow_unicode=True)

    return out_file
