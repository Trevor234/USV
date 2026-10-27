// Review-only source-linked probe. No ROS node, actuator or qualification.
#define P1_D1_SOURCE_BUNDLE_SHA256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#define P1_D1_F5_PARENT_MANIFEST_SHA256 "77737a5924f1bcd97996dee3c08e204a4a4c8fbf2f3716ff65d41fbc4bad6762"
#include "/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/publisher/include/usv_mpc_cpp/p1_startup_gate.hpp"
#include <iostream>

int main(int argc, char **argv) {
  using namespace usv_mpc;
  if (argc != 2) return 2;
  try {
    const std::filesystem::path root(argv[1]);
    const auto output = root / "publisher";
    std::filesystem::create_directory(output);
    std::ifstream boot_file("/proc/sys/kernel/random/boot_id");
    std::string boot; std::getline(boot_file, boot);
    const p1_startup::Json identity = {
      {"run_id", "review-link-race-publisher"},
      {"producer_instance_id", "review-link-race-publisher:probe"},
      {"steady_clock_domain", boot + ":steady_clock"},
      {"baseline_id", "F5_20261005_atomic_freeze_01"},
      {"config_hash", std::string(64, 'b')},
      {"nominal_config_hash", std::string(64, 'c')}
    };
    PublisherStartupGate gate(output, root / "release.json", identity);
    std::cout << p1_startup::Json({
      {"ready", true}, {"identity", gate.identity()},
      {"startup_manifest_sha256", gate.manifest_sha256()},
      {"scope", "original-header source-linked probe; no ROS"}}).dump() << std::endl;
    for (int i = 0; i < 2; ++i) {
      std::string command;
      if (!std::getline(std::cin, command) || command != "poll") return 3;
      bool arm_called = false;
      const bool released = gate.poll_release([&arm_called] {arm_called = true; return true;});
      std::string bytes; bool readable = false; std::string read_error;
      try {readable = p1_startup::read_regular_bounded(root / "release.json", bytes);}
      catch (const std::exception &error) {read_error = error.what();}
      std::cout << p1_startup::Json({
        {"poll_index", i + 1}, {"released", released}, {"arm_called", arm_called},
        {"gate", gate.observation()}, {"primitive_readable", readable},
        {"primitive_read_error", read_error}, {"primitive_bytes", bytes.size()}
      }).dump() << std::endl;
    }
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << std::endl; return 4;
  }
}
