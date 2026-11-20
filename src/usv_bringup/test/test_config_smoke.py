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
    from usv_bringup.topic_contract import generate_qos_overrides

    config_dir = _config_dir()
    topics = set(_load_yaml(config_dir / "bag_topics.yaml")["topics"])

    # 1. 验证动态派生的 QoS 覆盖表合法且属于录制话题子集
    derived_overrides = generate_qos_overrides(config_dir / "topic_contract.yaml")
    assert derived_overrides
    assert set(derived_overrides).issubset(topics)
    for topic, profile in derived_overrides.items():
        assert profile["reliability"] in {"best_effort", "reliable"}, topic
        assert profile["durability"] in {"volatile", "transient_local"}, topic
        assert profile["history"] in {"keep_last", "keep_all"}, topic
        assert profile["depth"] > 0, topic

    # 2. 验证静态兼容文件依然合法
    legacy_file = config_dir / "rosbag_qos_overrides.yaml"
    if legacy_file.is_file():
        overrides = _load_yaml(legacy_file)
        assert overrides
        assert set(overrides).issubset(topics)
        for topic, profile in overrides.items():
            assert profile["reliability"] in {"best_effort", "reliable"}, topic
            assert profile["durability"] in {"volatile", "transient_local"}, topic
            assert profile["history"] in {"keep_last", "keep_all"}, topic
            assert profile["depth"] > 0, topic


def test_scheme_mode_contract_matches_output_backend():
    """方案 ↔ FCU 模式是一一对应的硬契约, 写错就是船不动。

    A 输出速度 setpoint, 只有 GUIDED 执行; B 输出 RC 覆写, 只有 MANUAL
    下才经 ArduRover pilot 输入链成为舵/油主控制。2026-11-12 实船方案 B
    因 launch 未传 allowed_fcu_modes、节点默认 GUIDED, 切到 GUIDED 后
    原地不动 —— 契约必须由参数文件本身声明, 不能依赖 launch 兜底。
    """
    config_dir = _config_dir()
    expected = {"mpc_params_A.yaml": ["GUIDED"], "mpc_params_B.yaml": ["MANUAL"]}
    for filename, modes in expected.items():
        params = _load_yaml(config_dir / filename)["/**"]["ros__parameters"]
        assert params["allowed_fcu_modes"] == modes, filename
