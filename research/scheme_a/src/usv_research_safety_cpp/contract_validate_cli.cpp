// Pure contract validation: no rclcpp init, node, backend or publisher.
#include "protocol.hpp"
#include <iostream>
int main(int argc,char **argv){
  try{if(argc!=4)throw std::runtime_error("expected FILE SHA256 MODE");auto c=p1::load_contract(argv[1],argv[2]);p1::validate_contract_mode(c,argv[3]);
    std::cout<<p1::Json{{"schema_valid",true},{"mode_valid",true},{"physical_execute_release_enabled",p1::physical_execute_release_enabled},{"spec_sha256",p1::full_contract_spec_sha256}}.dump()<<std::endl;return 0;
  }catch(const std::exception & e){std::cerr<<e.what()<<std::endl;return 2;}
}
