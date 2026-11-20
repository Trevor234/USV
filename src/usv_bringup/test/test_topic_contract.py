from pathlib import Path
import pytest
import yaml

from usv_bringup.topic_contract import (
    extract_topics,
    generate_qos_overrides,
    get_record_topics,
    load_topic_contract,
    parse_qos_override,
    write_derived_qos_file,
)


def _config_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "config"


def test_load_topic_contract():
    path = _config_dir() / "topic_contract.yaml"
    contract = load_topic_contract(path)
    assert isinstance(contract, dict)
    assert "mpc_controller_node" in contract
    assert "path_profile_sync" in contract


def test_get_record_topics_matches_bag_topics():
    contract_path = _config_dir() / "topic_contract.yaml"
    record_topics = set(get_record_topics(contract_path))

    bag_topics_file = _config_dir() / "bag_topics.yaml"
    with bag_topics_file.open("r", encoding="utf-8") as f:
        expected_topics = set(yaml.safe_load(f)["topics"])

    # All 15 topics from bag_topics.yaml should be marked as record: true in topic_contract
    assert record_topics == expected_topics


def test_generate_qos_overrides_covers_all_sensor_data():
    contract_path = _config_dir() / "topic_contract.yaml"
    overrides = generate_qos_overrides(contract_path)

    # Must contain odom, imu, battery, fix, gps raw, mavlink
    required_topics = {
        "/mavros/local_position/odom",
        "/mavros/imu/data",
        "/usv/battery",
        "/mavros/global_position/raw/fix",
        "/mavros/gpsstatus/gps1/raw",
        "/uas1/mavlink_source",
        "/uas1/mavlink_sink",
    }
    assert required_topics.issubset(set(overrides.keys()))

    # Check mavlink depth 1000
    assert overrides["/uas1/mavlink_source"]["depth"] == 1000
    assert overrides["/uas1/mavlink_source"]["reliability"] == "best_effort"
    assert overrides["/uas1/mavlink_sink"]["depth"] == 1000
    assert overrides["/uas1/mavlink_sink"]["reliability"] == "best_effort"

    # Check sensor_data depth 5
    assert overrides["/mavros/local_position/odom"]["depth"] == 5
    assert overrides["/mavros/local_position/odom"]["reliability"] == "best_effort"
    assert overrides["/mavros/imu/data"]["depth"] == 5


def test_write_derived_qos_file(tmp_path):
    contract_path = _config_dir() / "topic_contract.yaml"
    out_file = tmp_path / "qos_derived.yaml"

    res = write_derived_qos_file(contract_path, out_file)
    assert res.is_file()

    with out_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "/uas1/mavlink_source" in data
    assert data["/uas1/mavlink_source"]["depth"] == 1000


def test_parse_qos_override_edge_cases():
    assert parse_qos_override(None) is None
    assert parse_qos_override("reliable depth=10") is None
    assert parse_qos_override("depth=10") is None

    sd = parse_qos_override("sensor_data")
    assert sd == {
        "reliability": "best_effort",
        "durability": "volatile",
        "history": "keep_last",
        "depth": 5,
    }

    be_custom = parse_qos_override("best_effort / transient_local / keep_last depth=42")
    assert be_custom == {
        "reliability": "best_effort",
        "durability": "transient_local",
        "history": "keep_last",
        "depth": 42,
    }
