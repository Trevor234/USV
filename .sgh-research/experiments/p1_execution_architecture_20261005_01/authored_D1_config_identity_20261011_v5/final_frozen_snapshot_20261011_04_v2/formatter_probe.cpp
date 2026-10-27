#include <nlohmann/json.hpp>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
int main(){
  std::string line;
  while(std::getline(std::cin,line)){
    auto input=nlohmann::json::parse(line);nlohmann::json values=nlohmann::json::array(),tokens=nlohmann::json::array();
    for(const auto & h:input.at("ieee_bits")){
      auto bits=std::stoull(h.get<std::string>(),nullptr,16);double x;
      static_assert(sizeof(x)==sizeof(bits));std::memcpy(&x,&bits,sizeof(x));
      if(!std::isfinite(x))return 2;
      nlohmann::json value=x;values.push_back(value);tokens.push_back(value.dump());
    }
    nlohmann::json output={{"tokens",tokens},{"array_dump",values.dump()},
      {"nlohmann_version",std::to_string(NLOHMANN_JSON_VERSION_MAJOR)+"."+std::to_string(NLOHMANN_JSON_VERSION_MINOR)+"."+std::to_string(NLOHMANN_JSON_VERSION_PATCH)}};
    std::cout<<output.dump()<<std::endl;
  }
}
