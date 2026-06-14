from pathlib import Path

import yaml


def test_bringup_yaml_configs_parse():
    config_dir = Path(__file__).resolve().parents[1] / "config"
    yaml_files = sorted(config_dir.glob("*.yaml"))
    assert yaml_files
    for path in yaml_files:
        with path.open("r", encoding="utf-8") as f:
            assert yaml.safe_load(f) is not None, path


def test_topic_contract_has_profile_stamp_contract():
    contract_path = Path(__file__).resolve().parents[1] / "config" / "topic_contract.yaml"
    text = contract_path.read_text(encoding="utf-8")
    assert "stamp_sec" in text
    assert "stamp_nanosec" in text
    assert "/path/reference" in text
    assert "/path/reference_profile" in text
