#!/usr/bin/env python3
"""Create-only final source/header/binary freeze and scoped preservation audit."""
import hashlib,importlib.util,json,pathlib,re,subprocess,sys
D=pathlib.Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_6_20261013_v12'
P=D.parent/'scheme_A_C3_5_20261013_10'
sys.path.insert(0,str(N.parent/'authored_D1_C3_5_20261013_v11'))
import acceptance_core_v1 as C
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False);f.write('\n')
def main():
 reader=C.Reader(seconds=300,max_bytes=512*1024*1024,max_files=6000)
 spec=importlib.util.spec_from_file_location('parent_protection',P/'archive_to_MPC_v1.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 before=m.protected()
 inventory=reader.json(P/'archive_inventory_v1.json')
 C.require(C.digest(reader.raw(P/'archive_inventory_v1.json'))=='854e2441a7e6cced193a9feb3c1bf73349dc8551b8ffd12b9a64ea3fb8c515e3','parent_archive_inventory')
 for pin in inventory['entries']:
  for root in (P,pathlib.Path('/home/trevor/MPC/scheme_A_C3_5_20261013_10')):
   reader.verify({'path':str(root/pin['relative_path']),'sha256':pin['sha256'],'bytes':pin['bytes']})
 build=reader.json(D/'component/attempt03/build_result.json');native=reader.json(D/'component/attempt03/native_result.json')
 C.require(build['returncode']==build['probe_returncode']==0 and build['native_passed'] is True and native['passed'] is True and native['count']==50,'native_current_result')
 for path,expected in build['sources_before'].items():C.require(C.digest(reader.raw(path))==expected,'compiled_source_current_identity')
 for path,expected in build['actual_compile_dependency_pins'].items():C.require(C.digest(reader.raw(path))==expected,'current_header_identity')
 binary=D/'component/attempt03/test_command_anchor_v1';C.require(C.digest(reader.raw(binary))==build['binary_sha256']=='1856472ccc23674504a2a2bc4a703daf31ef97419ab5861c181aa18afe3ff1aa','binary_identity')
 history=reader.json(D/'historical/attempt03/result.json');negative=reader.json(D/'historical/attempt03/negative_summary.json');decoder=reader.json(D/'negatives/native_input_v1/result.json')
 C.require(history['passed'] is True and (history['jobs'],history['activations'],history['anchor_mismatches'])==(23,22,21),'historical_result')
 C.require(negative['passed'] is True and negative['count']==10 and decoder['passed'] is True and decoder['count']==12 and decoder['negative_count']==11,'negative_results')
 lock=reader.json(D/'historical/attempt03/input_lock_v1.json')
 for pin in [*lock['sources'],*lock['records'].values(),lock['probe']]:reader.verify(pin)
 earlier=reader.json(D/'historical/attempt01/input_lock_v1.json')
 C.require(C.digest(reader.raw(D/'historical/attempt01/historical_anchor_audit_v1.py.snapshot'))==earlier['sources'][0]['sha256'],'failed_source_snapshot_retained')
 docs=list(D.glob('*.md'))+list((D/'source_audit').glob('*.md'));links=0
 for doc in docs:
  for target in re.findall(r'\]\((/[^)]+)\)',reader.raw(doc).decode()):
   links+=1;C.require(pathlib.Path(re.sub(r':\d+$','',target)).exists(),'document_link_target')
 root=D/'final_frozen_snapshot';root.mkdir(exist_ok=False)
 pairs=[];seen=set()
 paths=[('source',p) for p in sorted(N.rglob('*')) if p.is_file()]+[('source',pathlib.Path(__file__).resolve())]
 paths+=[('compile_dependency',pathlib.Path(p)) for p in build['actual_compile_dependency_pins']]
 paths+=[('compiler',pathlib.Path(build['compiler'])),('binary',binary)]
 paths+=[('contract',D/p) for p in ('preregister/anchor_component_scope_v1.json','historical/attempt03/input_lock_v1.json','component/attempt03/build_result.json')]
 for kind,path in paths:
  if str(path) in seen:continue
  seen.add(str(path));raw=reader.raw(path);dest=root/(f'{len(pairs)+1:04d}_'+path.name)
  with dest.open('xb') as f:f.write(raw)
  C.require(reader.raw(dest)==raw,'new_frozen_readback')
  pairs.append({'kind':kind,'original':str(path),'copy':str(dest),'sha256':C.digest(raw),'bytes':len(raw)})
 C.require(reader.unchanged(),'final_inputs_changed')
 after=m.protected();C.require(before==after,'parent_protection_changed')
 manifest={'schema':'p1-C3.6-A-final-freeze/v1','files':pairs,'all_pairs_verified':True,'native_binary_sha256':build['binary_sha256'],'compiler_reported_dependency_count':len(build['actual_compile_dependency_pins']),'new_author_files':6,'scope':'authored sources/probe/registered policy and compiler-reported headers; not complete OS/toolchain/plant/WCET qualification','stage_qualified':False,'research_conclusion':False}
 write(root/'manifest.json',manifest)
 parent_result=reader.json(P/'acceptance/full_attempt03/result.json')
 qa={'schema':'p1-C3.6-A-final-QA/v1','passed':True,'parent_before':before,'parent_after':after,'sealed_C3_5_pairs':len(inventory['entries']),'new_frozen_pairs':len(pairs),'native_cases':50,'historical_native_predicate_cases':22,'coherent_negative_copies':10,'decoder_cases':12,'decoder_negative_cases':11,'compiler_reported_dependency_count':len(build['actual_compile_dependency_pins']),'primary_documents':len(docs),'local_links_verified':links,'fixed_source_header_input_hashes':reader.hashes,'actual_ROS_or_actuator_launch':False,'qualifications':parent_result['qualifications'],'current_unified_runtime_anchor_contract':'unknown','engineering_time_policy':'not_run','new_independent_runtime_review':'not_run'}
 write(D/'postrun/final_QA.json',qa)
 write(D/'postrun/failure_inventory.json',{'first_historical_attempt':{'path':str(D/'historical/attempt01/failure.json'),'status':'failed','reason':'checker conflated Source check and Witness commit timestamps','source_snapshot_sha256':earlier['sources'][0]['sha256'],'resolution':'source-linked bounded order plus exact ready/activation joins'},'native_attempts':{'attempt01':'44 passed before guard refinements','attempt02':'50 passed before strict native decoder refinement','attempt03':'50 passed, final native decoder12 also passed'},'old_evidence_overwritten':False,'old_expected_updated':False})
 write(D/'batch_status_prepared.json',{'schema':'scheme-A-C3.6-A-status/v1','date':'2026-10-13','component_status':'passed','C3_6_overall_complete':False,'current_unified_runtime_anchor_contract':'unknown','native_cases':50,'historical_predicate_cases':22,'coherent_negatives':10,'native_decoder_cases':12,'qualifications':parent_result['qualifications'],'stages':parent_result['assessment']['stages'],'delivery_verified':False,'next':'source-linked new runtime adapter and authenticated owner lifecycle; finite engineering policy and recipe before current runs/phase contract/M4'})
 print(json.dumps({k:v for k,v in qa.items() if k not in ('fixed_source_header_input_hashes','qualifications')},ensure_ascii=False))
if __name__=='__main__':main()
