#include <nlohmann/json.hpp>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
using Json=nlohmann::json;
void require(bool v,const char *s){if(!v)throw std::runtime_error(s);}
inline std::string double_canonical(double v){require(std::isfinite(v),"owned nonfinite parameter");static_assert(sizeof(double)==8&&std::numeric_limits<double>::is_iec559,"IEEE754 double required");uint64_t bits=0;std::memcpy(&bits,&v,8);std::ostringstream out;out<<std::hex<<std::setw(16)<<std::setfill('0')<<bits;return out.str();}
inline Json canonical_parameters(const Json &rows){Json out=Json::object();for(auto it=rows.begin();it!=rows.end();++it)out[it.key()]={{"type",it.value().at("type")},{"canonical_value",it.value().at("canonical_value")}};return out;}
int main(){Json in;std::cin>>in;Json out;out["canonical_dump"]=canonical_parameters(in["rows"]).dump();out["bits"]=Json::array();for(const auto &x:in["bits"]){auto b=std::stoull(x.get<std::string>(),nullptr,16);double d;std::memcpy(&d,&b,8);out["bits"].push_back(double_canonical(d));}std::cout<<out.dump()<<std::endl;}
