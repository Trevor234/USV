#!/usr/bin/env python3
"""Bounded ASCII/IEEE canonical differential; isolated pure C++ source extraction."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import config_scope_v1 as scope
import owned_auth
N=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--run',type=Path,required=True);a=ap.parse_args()
 a.output.mkdir(exist_ok=False);header=N/'common/p1_owned_identity.hpp'
 lines=header.read_text().splitlines();selected=[next(s for s in lines if s.startswith('inline std::string double_canonical(')),next(s for s in lines if s.startswith('inline Json canonical_parameters('))]
 corpus=Path('/home/trevor/MPC/scheme_A_config_identity_20261011_04/preregister/formatter_corpus_contract_v1.json')
 bits=json.loads(corpus.read_text())['allowed_ieee_bits']
 dump(a.output/'preregister.json',{'before_compile':True,'scope':'ASCII typed parameter canonical JSON; exact frozen finite IEEE corpus; no universal decimal formatter',
      'header':{'path':str(header),'sha256':sha(header)},'extracted_functions':selected,'corpus':{'path':str(corpus),'sha256':sha(corpus)},'execute_qualified':False})
 source=a.output/'config_scope_probe_v1.cpp'
 source.open('x').write('#include <nlohmann/json.hpp>\n#include <cmath>\n#include <cstdint>\n#include <cstring>\n#include <iomanip>\n#include <iostream>\n#include <limits>\n#include <sstream>\n#include <stdexcept>\nusing Json=nlohmann::json;\nvoid require(bool v,const char *s){if(!v)throw std::runtime_error(s);}\n'+ '\n'.join(selected)+'\nint main(){Json in;std::cin>>in;Json out;out["canonical_dump"]=canonical_parameters(in["rows"]).dump();out["bits"]=Json::array();for(const auto &x:in["bits"]){auto b=std::stoull(x.get<std::string>(),nullptr,16);double d;std::memcpy(&d,&b,8);out["bits"].push_back(double_canonical(d));}std::cout<<out.dump()<<std::endl;}\n')
 binary=a.output/'config_scope_probe_v1'
 command=['g++','-std=c++17','-O1',str(source),'-o',str(binary)]
 dump(a.output/'compile_command.json',{'argv':command,'budget_seconds':30})
 with (a.output/'compile.log').open('xb') as log:rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=30).returncode
 if rc:raise RuntimeError('probe compile failed')
 reports=[]
 for role in scope.ROLES:
  manifest=json.loads((a.run/role/'owned_manifest.json').read_text());rows=manifest['effective_parameters'];domain=scope.check_parameters(rows)
  cpp=subprocess.run([str(binary)],input=json.dumps({'rows':rows,'bits':bits},allow_nan=False),text=True,capture_output=True,timeout=5)
  dump(a.output/(role+'_native_raw.json'),{'returncode':cpp.returncode,'stdout':cpp.stdout,'stderr':cpp.stderr})
  assert cpp.returncode==0;actual=json.loads(cpp.stdout);canonical=owned_auth.canonical_parameters(rows)
  expected=json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
  reports.append({'role':role,'parameters':domain['parameters'],'ASCII_IEEE_domain_passed':domain['passed'],
                  'original_cpp_canonical_dump_equal':actual['canonical_dump']==expected,'original_cpp_finite_bits_equal':actual['bits']==bits,
                  'canonical_sha256':hashlib.sha256(expected.encode()).hexdigest(),'actual_cpp_manifest_digest_equal':hashlib.sha256(expected.encode()).hexdigest()==manifest['effective_parameters_sha256']})
 result={'schema':'p1-C3.4-supported-config-differential/v1','passed':all(all(r[k] for k in ('ASCII_IEEE_domain_passed','original_cpp_canonical_dump_equal','original_cpp_finite_bits_equal','actual_cpp_manifest_digest_equal')) for r in reports),
         'roles':reports,'finite_ieee_bits_count':len(bits),'original_header_sha256':sha(header),'probe_source_sha256':sha(source),'probe_binary_sha256':sha(binary),
         'reference_decimal_formatter_scope':'inherited frozen corpus only; new universal decimal algorithm not claimed','Unicode_general_qualified':False,
         'strict_full_chain':False,'execute':False,'research_conclusion':False}
 dump(a.output/'result.json',result);print(json.dumps(result,sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
