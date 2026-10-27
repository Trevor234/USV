// SPDX-License-Identifier: MIT
#include "foreign_protocol.hpp"
#include <gtest/gtest.h>
namespace {
const std::string H(64,'a'), M(64,'b'), RUN="owned_C310_unit", BOOT="unit-boot";
c310::Applied message(){c310::Applied m;m.schema_version="p0-contract-v1";m.run_id=RUN+"-publisher";m.producer_instance_id="original-owner";m.config_hash=H;m.sequence=23;m.control_source="shutdown_zero";m.final_n={0.,0.};m.left_publish_success=true;m.right_publish_success=true;return m;}
c310::Json command(){auto bytes=c310::encode(message());return {{"schema","p1-C3.10-foreign-Applied-command-v1"},{"run_id",RUN},{"boot_id",BOOT},{"original_owner_manifest_sha256",H},{"original_applied_cdr_hex",p1_owned::hex(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size())},{"original_applied_cdr_sha256",p1_owned::sha256_bytes(bytes)},{"driver_pid",1000},{"driver_start_ticks",1234},{"driver_tool_sha256",H},{"close_request_sha256",H},{"close_observed_ns",1000},{"owner_exit_proof_sha256",H}};}
c310::Json gate(){return {{"schema","p1-C3.10-foreign-Applied-emit-v1"},{"run_id",RUN},{"boot_id",BOOT},{"driver_pid",1000},{"driver_start_ticks",1234},{"driver_tool_sha256",H},{"command_sha256",H},{"foreign_manifest_sha256",M},{"issued_ns",2000}};}
c310::Json contract(){return {{"schema","p1-C3.10-foreign-Applied-contract-v1"},{"topic","/research/control/applied"},{"ros_type","usv_research_interfaces/msg/AppliedControl"},{"packet_labels",c310::Json::array({"clone_zero_first","clone_nonzero","clone_zero_repeat"})},{"max_packets",3},{"max_cdr_bytes",8192},{"nonzero_final_n",c310::Json::array({1.0,-1.0})},{"physical_publisher_endpoints",0},{"stage_qualified",false},{"execute_qualified",false}};}
TEST(C310ForeignProtocol, ExactContractPasses){EXPECT_NO_THROW(c310::contract(contract()));}
TEST(C310ForeignProtocol, ContractExtraAndWrongTopicFail){auto j=contract();j["extra"]=true;EXPECT_ANY_THROW(c310::contract(j));
 j=contract();j["topic"]="/wamv/thrusters/left/thrust";EXPECT_ANY_THROW(c310::contract(j));}
TEST(C310ForeignProtocol, ContractNeverGrantsExecution){auto j=contract();j["execute_qualified"]=true;EXPECT_ANY_THROW(c310::contract(j));
 j=contract();j["physical_publisher_endpoints"]=1;EXPECT_ANY_THROW(c310::contract(j));}
TEST(C310ForeignProtocol, ContractFixedPacketPopulation){auto j=contract();j["max_packets"]=4;EXPECT_ANY_THROW(c310::contract(j));
 j=contract();j["packet_labels"][2]="other";EXPECT_ANY_THROW(c310::contract(j));}
TEST(C310ForeignProtocol, ContractBooleanCannotReplaceInteger){auto j=contract();j["max_packets"]=true;EXPECT_ANY_THROW(c310::contract(j));}
TEST(C310ForeignProtocol, ExactCommandPreservesOriginalCdrBytes){auto j=command();auto bytes=c310::command(j,RUN,BOOT);EXPECT_EQ(bytes,c310::unhex(j["original_applied_cdr_hex"]));EXPECT_EQ(c310::decode(bytes).sequence,23);}
TEST(C310ForeignProtocol, CommandIdentityMismatchFails){auto j=command();j["run_id"]="other";EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));
 j=command();j["boot_id"]="other";EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));}
TEST(C310ForeignProtocol, CommandCdrDigestMismatchFails){auto j=command();j["original_applied_cdr_sha256"]=H;EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));}
TEST(C310ForeignProtocol, CommandRequiresTerminalSourceAndZero){auto j=command();auto m=message();m.final_n[0]=1.0;auto bytes=c310::encode(m);j["original_applied_cdr_hex"]=p1_owned::hex(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size());j["original_applied_cdr_sha256"]=p1_owned::sha256_bytes(bytes);EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));
 m=message();m.control_source="solver";bytes=c310::encode(m);j["original_applied_cdr_hex"]=p1_owned::hex(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size());j["original_applied_cdr_sha256"]=p1_owned::sha256_bytes(bytes);EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));}
TEST(C310ForeignProtocol, CommandRejectsBooleanAndNegativePid){auto j=command();j["driver_pid"]=true;EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));
 j=command();j["driver_pid"]=-1;EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));}
TEST(C310ForeignProtocol, CommandExactFieldsetRequired){auto j=command();j.erase("owner_exit_proof_sha256");EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));
 j=command();j["execute_qualified"]=false;EXPECT_ANY_THROW(c310::command(j,RUN,BOOT));}
TEST(C310ForeignProtocol, FullTypedCloneChangesOnlyRequestedFinalField){auto original=message();auto mutated=c310::decode(c310::encode(original));mutated.final_n={1.,-1.};auto result=c310::decode(c310::encode(mutated));EXPECT_EQ(result.sequence,original.sequence);EXPECT_EQ(result.producer_instance_id,original.producer_instance_id);EXPECT_EQ(result.control_source,"shutdown_zero");EXPECT_EQ(result.final_n[0],1.);EXPECT_EQ(result.final_n[1],-1.);result.final_n=original.final_n;EXPECT_EQ(c310::encode(result),c310::encode(original));}
TEST(C310ForeignProtocol, EmitFreshCurrentFullBindingPasses){EXPECT_NO_THROW(c310::emit(gate(),command(),H,M,2001));}
TEST(C310ForeignProtocol, EmitTtlBoundaryIsInclusive){EXPECT_NO_THROW(c310::emit(gate(),command(),H,M,3500002000ULL));
 EXPECT_ANY_THROW(c310::emit(gate(),command(),H,M,3500002001ULL));}
TEST(C310ForeignProtocol, EmitFutureAndBeforeCloseFail){EXPECT_ANY_THROW(c310::emit(gate(),command(),H,M,1999));
 auto j=gate();j["issued_ns"]=999;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));}
TEST(C310ForeignProtocol, EmitWrongDriverAndManifestFail){auto j=gate();j["driver_start_ticks"]=1235;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));
 j=gate();j["foreign_manifest_sha256"]=H;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));}
TEST(C310ForeignProtocol, EmitWrongCommandAndExtraFieldFail){auto j=gate();j["command_sha256"]=M;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));
 j=gate();j["extra"]=0;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));}
TEST(C310ForeignProtocol, EmitNumericIdentityCannotUseEquivalentFloat){auto j=gate();j["driver_pid"]=1000.0;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));
 j=gate();j["driver_start_ticks"]=1234.0;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));}
TEST(C310ForeignProtocol, EmitIdentityCannotUseBooleanOrNumericText){auto j=gate();j["driver_pid"]=true;EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));
 j=gate();j["driver_pid"]="1000";EXPECT_ANY_THROW(c310::emit(j,command(),H,M,2001));}
TEST(C310ForeignProtocol, RejectDuplicateJsonKeysIncludingNested){EXPECT_ANY_THROW(c310::strict_json("{\"a\":1,\"a\":2}"));
 EXPECT_ANY_THROW(c310::strict_json("{\"a\":[{\"b\":1,\"b\":2}]}"));}
TEST(C310ForeignProtocol, SameKeyInSeparateObjectsIsValid){EXPECT_NO_THROW(c310::strict_json("{\"a\":{\"x\":1},\"b\":{\"x\":2}}"));}
TEST(C310ForeignProtocol, CdrHexDomainFiniteAndExact){EXPECT_EQ(c310::unhex("0001ff"),std::string("\x00\x01\xff",3));
 EXPECT_ANY_THROW(c310::unhex("0"));
 EXPECT_ANY_THROW(c310::unhex("AB"));
 EXPECT_ANY_THROW(c310::unhex(std::string(16386,'0')));}
TEST(C310ForeignProtocol, InvalidSerializedPayloadCannotBecomeMessage){EXPECT_ANY_THROW(c310::decode(std::string("bad")));}
} // namespace
