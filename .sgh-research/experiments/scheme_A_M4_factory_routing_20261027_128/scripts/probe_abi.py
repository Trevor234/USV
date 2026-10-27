from pathlib import Path
import json, sys
from run_matrix import ROOT, command, save

out=ROOT/'evidence/abi_probe01'
out.mkdir(exist_ok=False)
source=out/'probe.cpp'
source.write_text('#include <casadi/casadi.hpp>\nint main(){casadi::Opti o; o.subject_to(o.x() >= 0); return 0;}\n')
casadi=Path(json.loads((ROOT/'evidence/inputs/manifest_v1.json').read_text())['casadi_dir'])
results={}
for abi,flags in [('default',[]),('old',['-D_GLIBCXX_USE_CXX11_ABI=0'])]:
    results[abi]=command(['g++',*flags,source,f'-I{casadi}/include',f'-L{casadi}',f'-Wl,-rpath,{casadi}','-lcasadi','-o',out/('probe_'+abi)],out/('link_'+abi))
complete=results['old']['returncode']==0 and isinstance(results['default']['returncode'],int) and results['default']['returncode']!=0
save(out/'verification.json',{'complete':complete,'results':results,'meaning':'Link compatibility only; same probe as current production CMake, no runtime or timing qualification'})
print(json.dumps({'complete':complete,'default_rc':results['default']['returncode'],'old_rc':results['old']['returncode']}))
sys.exit(0 if complete else 2)
