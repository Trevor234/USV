from pathlib import Path

import yaml


def _config_dir():
    return Path(__file__).resolve().parents[1] / "config"


def _load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_bringup_yaml_configs_parse():
    yaml_files = sorted(_config_dir().glob("*.yaml"))
    assert yaml_files
    for path in yaml_files:
        assert _load_yaml(path) is not None, path


def test_topic_contract_declares_profile_stamp_encoding():
    contract = _load_yaml(_config_dir() / "topic_contract.yaml")
    sync = contract["path_profile_sync"]
    assert sync["reference_topic"] == "/path/reference"
    assert sync["profile_topic"] == "/path/reference_profile"
    assert sync["stamp_encoding"]["layout_dim_labels"] == ["stamp_sec", "stamp_nanosec"]


def test_bag_topics_are_valid_and_documented_in_topic_contract():
    package_dir = Path(__file__).resolve().parents[1]
    topics = _load_yaml(package_dir / "config" / "bag_topics.yaml")["topics"]
    contract = (package_dir / "config" / "topic_contract.yaml").read_text(
        encoding="utf-8"
    )

    assert topics
    assert len(topics) == len(set(topics))
    assert all(isinstance(topic, str) and topic.startswith("/") for topic in topics)
    # 每个录制话题必须在契约中有说明, 避免清单与契约漂移。
    assert all(topic in contract for topic in topics)


def test_rosbag_qos_overrides_cover_recorded_topics_only():
    config_dir = _config_dir()
    topics = set(_load_yaml(config_dir / "bag_topics.yaml")["topics"])
    overrides = _load_yaml(config_dir / "rosbag_qos_overrides.yaml")

    # 只校验覆盖表自身合法且不引用未录制的话题;
    # 具体话题集合与 depth 由实测入包结果决定, 不在此钉死。
    assert overrides
    assert set(overrides).issubset(topics)
    for topic, profile in overrides.items():
        assert profile["reliability"] in {"best_effort", "reliable"}, topic
        assert profile["durability"] in {"volatile", "transient_local"}, topic
        assert profile["history"] in {"keep_last", "keep_all"}, topic
        assert profile["depth"] > 0, topic
