import json,re,shlex,shutil,sys
from pathlib import Path
from offline_support import Evidence,ROOT,pin,save
e=Evidence('E07',sys.argv[1]);fixture=ROOT/'implementation/author/fixture';test=ROOT/'implementation/tests/test_resume_boundaries.cpp'
cases=['B2V-01-LEGAL','B2V-16-NO-HOLD','B2V-17a-MAX','B2V-17b-MIN','B2V-17c-CAP-EDGE','B2V-17d-PLUS','B2V-18-UBSAN','B2V-19-CAP','B2V-20a-LONG-HOLD','B2V-20b-RX-SKEW','B2V-21-ROS-RANGE']
save(e.out/'registration.json',{'cases':cases,'source':pin(fixture/'resume_stamp_mapping_v1.hpp'),'case_timeout_seconds':60,'auto_retry':0,'cap_boundary_policy':'exact cap not clipped; cap+1 explicitly capped/outside normal'})
def build(source,include,name):
 binary=e.out/name;r=e.command('build_'+name,['g++','-std=c++17','-O1','-fsanitize=undefined','-fno-sanitize-recover=all','-I',include,source,'-o',binary]);e.check('build.'+name,r.returncode==0);return binary if r.returncode==0 else None
def run(binary,case,out):
 r=e.command(case,[binary,case,out],timeout=60);p=out/'result.json';return r,json.loads(p.read_text())if p.is_file()else{}
binary=build(test,fixture,'mapping')
if binary:
 for case in cases:
  r,d=run(binary,case,e.out/'runs'/case);e.check(case,r.returncode==0 and d.get('passed')is True and bool(d.get('assertions'))and all(x['passed']is True for x in d['assertions']) and 'runtime error:'not in r.stderr)
legacy=ROOT/'implementation/author/tests/test_resume_mapping_v1.cpp'
old=build(legacy,fixture,'existing16')
if old:
 r=e.command('existing16',[old,e.out/'existing16_run'],timeout=60);p=e.out/'existing16_run/result.json';d=json.loads(p.read_text())if p.is_file()else{}
 e.check('existing_arithmetic_16_controls',r.returncode==0 and d.get('passed')is True and d.get('assertion_count')==16)
text=(fixture/'resume_stamp_mapping_v1.hpp').read_text()
old_guard='  if ((b > 0 && a > std::numeric_limits<int64_t>::max() - b)\n      || (b < 0 && a < std::numeric_limits<int64_t>::min() - b)) return false;'
for name,pattern,replacement,case,assertion in[
 ('overflow',old_guard,'  // arithmetic guard removed','B2V-17a-MAX',None),
 ('cap','return valid && !capped;','return valid;','B2V-19-CAP','cap_is_not_normal_recovery')]:
 directory=e.out/'mutations'/name;directory.mkdir(parents=True);prepared=text.count(pattern)==1;e.check('mutation.prepared.'+name,prepared)
 if not prepared:continue
 (directory/'resume_stamp_mapping_v1.hpp').write_text(text.replace(pattern,replacement));mut=build(test,directory,'mut_'+name)
 if mut:
  r,d=run(mut,case,directory/'run');failed=[x['name']for x in d.get('assertions',[])if x['passed']is False]
  caught=(r.returncode!=0 and 'runtime error: signed integer overflow'in r.stderr)if name=='overflow'else(r.returncode==2 and assertion in failed)
  e.check('mutation.caught.'+name,caught,{'mode':'UBSan'if name=='overflow'else'named_assertion','failed':failed})
base=ROOT.parent/'scheme_A_M4_rnw_s4_owned_20261025_119';flags=(base/'build/cmake/CMakeFiles/p1_m4_regulator_owned.dir/flags.make').read_text()
includes=shlex.split(re.search(r'^CXX_INCLUDES = (.*)$',flags,re.M).group(1));includes=[x.replace(str(base/'implementation/t2_author'),str(ROOT/'implementation/author'))for x in includes]
r=e.command('fixture_actual_compile',['g++','-std=c++17','-O0','-DP1_DRIVER_TOOL_SHA256="offline-compile-only"','-DP1_OWNED_SOURCE_BUNDLE_SHA256="offline-compile-only"',*includes,'-c',fixture/'synthetic_source_m4.cpp','-o',e.out/'fixture.o'],timeout=600)
e.check('actual_fixture_compiles',r.returncode==0)
source=(fixture/'synthetic_source_m4.cpp').read_text();guard=source.index('if(!mapped.normal_allowed()');publish=source.index('clock_->publish(c)',guard)
e.check('actual_publish_requires_valid_uncapped_representable',guard<publish and 'ros_time_representable(mapped.stamp_ns)'in source[guard:publish] and 'require(false,'in source[guard:publish])
result=e.finish(cases_registered=len(cases),legacy_arithmetic_assertions=16,helper_pin=pin(fixture/'resume_stamp_mapping_v1.hpp'),actual_fixture_compile_only=True,limitations_preserved=['4000000ns receive-skew regression','1100000000ns capped-hold regression'])
sys.exit(0 if result['status']=='PASS'else 2)
