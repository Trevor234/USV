// SPDX-License-Identifier: MIT
// Actual DDS finite component evidence producer, not a production Worker,
// native solver, or owned startup fixture. Original callback is source-linked.
#include <filesystem>
#include <sqlite3.h>
#include "c34_lease_access.hpp"

static p1::Json payload(const p1::Capability &m){return {
 {"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},{"contract_hash",m.contract_hash},
 {"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},{"clock_name",m.clock_name},
 {"backend",m.backend},{"matrix_layout",m.matrix_layout},{"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},
 {"pid",m.pid},{"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},
 {"pending_count",m.pending_count},{"fault_injection_enabled",m.fault_injection_enabled},{"fatal",m.fatal},{"reason",m.reason}};}
static void write_json(const std::filesystem::path &path,const p1::Json &value){
 std::ofstream out(path);if(!out)throw std::runtime_error("evidence write open failed");out<<value.dump(2)<<'\n';out.flush();if(!out)throw std::runtime_error("evidence write failed");}
struct Database {
 sqlite3 *db=nullptr;sqlite3_stmt *insert=nullptr;
 explicit Database(const std::filesystem::path &path){
  if(sqlite3_open_v2(path.c_str(),&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_EXCLUSIVE,nullptr)!=SQLITE_OK)throw std::runtime_error("SQLite open failed");
  const char *sql="PRAGMA journal_mode=DELETE;PRAGMA synchronous=FULL;CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT NOT NULL,type TEXT NOT NULL,serialization_format TEXT NOT NULL);CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER NOT NULL,timestamp INTEGER NOT NULL,data BLOB NOT NULL);INSERT INTO topics VALUES(1,'/p1_C34_component/worker_capability','usv_research_interfaces/msg/WorkerCapability','cdr');";
  if(sqlite3_exec(db,sql,nullptr,nullptr,nullptr)!=SQLITE_OK)throw std::runtime_error("SQLite schema failed");
  if(sqlite3_prepare_v2(db,"INSERT INTO messages(topic_id,timestamp,data) VALUES(1,?,?)",-1,&insert,nullptr)!=SQLITE_OK)throw std::runtime_error("SQLite prepare failed");
 }
 void add(int64_t ns,const void *bytes,size_t size){
  sqlite3_bind_int64(insert,1,ns);sqlite3_bind_blob(insert,2,bytes,int(size),SQLITE_TRANSIENT);
  if(sqlite3_step(insert)!=SQLITE_DONE)throw std::runtime_error("SQLite storage failed");sqlite3_reset(insert);sqlite3_clear_bindings(insert);
 }
 ~Database(){if(insert)sqlite3_finalize(insert);if(db)sqlite3_close(db);}
};
int main(int argc,char **argv){
 if(argc!=3){fprintf(stderr,"usage: c34_lease_wire OUTPUT CASE\n");return 2;}
 const std::filesystem::path output=argv[1];const std::string scenario=argv[2];
 try {
  if(!output.is_absolute()||!std::filesystem::create_directory(output))throw std::runtime_error("fresh absolute output required");
  rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);
  auto regulator=C34LeaseAccess::make((output/"observer_source.jsonl").string());
  const std::string topic="/p1_C34_component/worker_capability";
  auto producer=std::make_shared<rclcpp::Node>("p1_C34_component_evidence_producer",rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false));
  auto recorder=std::make_shared<rclcpp::Node>("p1_C34_component_SQLite_recorder",rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false));
  auto pub=producer->create_publisher<p1::Capability>(topic,rclcpp::QoS(32).reliable().transient_local());
  std::atomic<unsigned> observer_count{0},recorder_count{0};C34LeaseAccess::subscribe(*regulator,topic,observer_count);
  Database database(output/"capability.db3");std::ofstream record_source(output/"recorder_source.jsonl"),publish_source(output/"publisher_source.jsonl");
  if(!record_source||!publish_source)throw std::runtime_error("source open failed");
  auto subscription=recorder->create_generic_subscription(topic,"usv_research_interfaces/msg/WorkerCapability",rclcpp::QoS(32).reliable().transient_local(),
    [&](std::shared_ptr<rclcpp::SerializedMessage> message,const rclcpp::MessageInfo &info){
      const auto now=p1::monotonic_ns();const auto &cdr=message->get_rcl_serialized_message();
      if(cdr.buffer_length==0||cdr.buffer_length>1048576)throw std::runtime_error("wire CDR bound");
      const auto &rmw=info.get_rmw_message_info();const std::string bytes(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
      database.add(now,cdr.buffer,cdr.buffer_length);const auto sequence=++recorder_count;
      record_source<<p1::Json{{"type","actual_wire_storage"},{"sequence",sequence},{"receive_ns",now},{"publisher_gid",p1_owned::gid_json(rmw.publisher_gid)},
        {"serialized_bytes",cdr.buffer_length},{"cdr_sha256",p1_owned::sha256_bytes(bytes)},{"source_timestamp",rmw.source_timestamp},{"received_timestamp",rmw.received_timestamp}}.dump()<<'\n';
    });
  rclcpp::executors::SingleThreadedExecutor executor;executor.add_node(regulator->get_node_base_interface());executor.add_node(producer);executor.add_node(recorder);
  const auto deadline=p1::monotonic_ns()+15000000000LL;
  auto spin_until=[&](auto condition){while(!condition()){
      if(p1::monotonic_ns()>deadline)throw std::runtime_error("component bounded DDS timeout");executor.spin_some();std::this_thread::sleep_for(std::chrono::milliseconds(2));}};
  spin_until([&]{return pub->get_subscription_count()>=2;});
  auto good=C34LeaseAccess::valid(*regulator);std::vector<p1::Capability> messages;
  if(scenario=="invalid_foreign"){auto invalid=good;invalid.backend="other";auto foreign=good;foreign.run_id="foreign";foreign.fatal=true;messages={good,invalid,foreign,good};}
  else if(scenario=="fatal"){auto fatal=good;fatal.fatal=true;messages={good,fatal,good};}
  else if(scenario=="instance"){auto changed=good;changed.worker_instance=std::string(64,'f');changed.backend="other";messages={good,changed,good};}
  else if(scenario=="expired"||scenario=="duplicate"){messages={good,good};}
  else if(scenario=="no_valid"){auto invalid=good;invalid.backend="other";messages={invalid};}
  else throw std::runtime_error("undeclared component scenario");
  const auto actual_pub=p1_owned::publisher_endpoint(*pub,"usv_research_interfaces/msg/WorkerCapability");
  const p1::Json expected={{"run_id",good.run_id},{"boot_id",good.boot_id},{"contract_hash",good.contract_hash},{"nominal_hash",good.nominal_hash},{"pid",good.pid},{"fault_injection_enabled",good.fault_injection_enabled}};
  write_json(output/"manifest.json",{{"schema","p1-C3.4-capability-wire-component-v1"},{"scenario",scenario},{"evidence_producer_role","explicitly-seeded-source-linked-component; not production Worker or native solver"},
    {"source_bundle_sha256",P1_OWNED_SOURCE_BUNDLE_SHA256},{"binary_sha256",file_sha("/proc/self/exe")},{"pid",getpid()},{"boot_id",p1::boot_id()},{"expected",expected},{"timeout_ns",600000000},
    {"publisher",actual_pub},{"observer_subscription",C34LeaseAccess::endpoint(*regulator)},
    {"recorder_subscription",p1_owned::subscription_endpoint(*subscription,"usv_research_interfaces/msg/WorkerCapability")},
    {"component_verification_only",true},{"production_owned_startup_qualified",false},{"physical_publisher_endpoints",0},{"packet_freshness",false}});
  for(size_t i=0;i<messages.size();++i){
    if(i==1&&scenario=="expired")std::this_thread::sleep_for(std::chrono::milliseconds(650));
    rclcpp::Serialization<p1::Capability> serializer;rclcpp::SerializedMessage serialized;serializer.serialize_message(&messages[i],&serialized);
    const auto &cdr=serialized.get_rcl_serialized_message();const std::string bytes(reinterpret_cast<const char *>(cdr.buffer),cdr.buffer_length);
    const auto start=p1::monotonic_ns();pub->publish(messages[i]);const auto end=p1::monotonic_ns();
    publish_source<<p1::Json{{"type","component_publish"},{"sequence",i+1},{"payload",payload(messages[i])},{"publish_start_ns",start},{"publish_end_ns",end},
       {"publisher_gid",actual_pub["gid"]},{"cdr_bytes",cdr.buffer_length},{"cdr_hex",p1_owned::hex(cdr.buffer,cdr.buffer_length)},{"cdr_sha256",p1_owned::sha256_bytes(bytes)}}.dump()<<'\n';
    spin_until([&]{return observer_count==i+1&&recorder_count==i+1;});
  }
  C34LeaseAccess::close(*regulator);record_source.flush();publish_source.flush();
  if(!record_source||!publish_source)throw std::runtime_error("source flush failed");
  write_json(output/"terminal.json",{{"passed",true},{"publisher_count",messages.size()},{"observer_count",observer_count.load()},{"recorder_count",recorder_count.load()},
    {"actual_original_callback_state",C34LeaseAccess::state(*regulator)},{"component_verification_only",true},{"stage_qualified",false},{"execute_qualified",false}});
  executor.remove_node(regulator->get_node_base_interface());regulator.reset();rclcpp::shutdown();return 0;
 }catch(const std::exception &e){fprintf(stderr,"component failure: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 1;}
}
