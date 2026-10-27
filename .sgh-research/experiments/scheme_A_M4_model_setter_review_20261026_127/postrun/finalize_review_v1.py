from pathlib import Path
import datetime,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
def pin(path):
 raw=Path(path).read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x')as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
inputs=json.loads((ROOT/'evidence/inputs/input_manifest_v1.json').read_text())
supplement=json.loads((ROOT/'evidence/inputs/factory_review_supplement_v1.json').read_text())
expected={**inputs['files'],supplement['path']:{'bytes':supplement['bytes'],'sha256':supplement['sha256']}}
input_drift=[p for p,record in expected.items()if not Path(p).is_file()or pin(p)!=record]
library_drift=[p for p,record in inputs['runtime_libraries'].items()if pin(p)!=record]
workspace_drift=[{'path':p,'current':pin(p)if Path(p).is_file()else None,'before':record}for p,record in inputs['workspace_files'].items()if not Path(p).is_file()or pin(p)!=record]
git_now=subprocess.check_output(['git','status','--porcelain=v1','-uall'],cwd=REPO,text=True)
previous=ROOT.parent/'scheme_A_M4_offline_hardening_20261026_126'
delivery=json.loads((previous/'evidence/delivery_population_v1.json').read_text())
protected={**{str(previous/p):rec for p,rec in delivery['files'].items()},
 **{str(previous/p['path']):{'bytes':p['bytes'],'sha256':p['sha256']}for p in delivery['excluded_build_files']}}
previous_drift=[p for p,rec in protected.items()if not Path(p).is_file()or pin(p)!=rec]
main=json.loads((ROOT/'evidence/attempt02/verification.json').read_text())
replay=json.loads((ROOT/'evidence/experimental_replay_v2/verification.json').read_text())
inventory=json.loads((ROOT/'postrun/patch_inventory_v2.json').read_text())
patches_ok=all(pin(p['path'])==p['pin']for p in inventory['patch_order'])
links={}
for name in ['behavior_baseline','behavior_packing_only','behavior_checked_init','experimental_f6']:
 p=ROOT/'build/attempt02/CMakeFiles'/(name+'.dir')/'link.txt';text=p.read_text()
 links[name]={'path':str(p),'pin':pin(p),'uses_fresh_codegen':'libgenerated_current.a'in text,'no_installed_solver_archive':'/usv_mpc_ws/install/'not in text}
dep=next((ROOT/'build/attempt02/CMakeFiles/experimental_f6.dir').rglob('*.o.d')).read_text()
shared_physical_headers=all(str(ROOT/'implementation/checked_init/include/usv_mpc_cpp'/n)in dep for n in ['p_global_pack.hpp','p_global_apply.hpp'])
checks={'current_source_inputs_unchanged':not input_drift,'native_runtime_libraries_unchanged':not library_drift,
 'previous126_population_current_bytes_preserved':not previous_drift,'registered_functional_matrix_passed':main['status']=='PASS'and main['failures']==[],
 'corrected_experimental_labels_19_passed':replay['passed']is True and len(replay['cases'])==19,
 'three_active_patches_pinned':patches_ok and len(inventory['patch_order'])==3,
 'fresh_link_recipe_verified':all(d['uses_fresh_codegen']and d['no_installed_solver_archive']for d in links.values()),
 'experiment_compiles_same_physical_common_headers':shared_physical_headers}
qualified={k:False for k in ['M4','F6','P1','plant','hard_realtime']}
verification={'schema':'model-setter-review127-final-v1','recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
 'status':'REVIEW_COMPLETE_WITH_INTEGRATION_GATES_OPEN'if all(checks.values())else'FAIL_STOP','checks':checks,
 'input_population':len(expected),'input_drift':input_drift,'runtime_library_drift':library_drift,
 'previous126_files_verified':len(protected),'previous126_drift':previous_drift,
 'workspace_scope':'Concurrent non-input workspace changes are retained and recorded, not restored or included in the reviewed patch.',
 'workspace_population_before':len(inputs['workspace_files']),'workspace_drift':workspace_drift,'git_porcelain_before':inputs['git_porcelain'],'git_porcelain_now':git_now,
 'links':links,'patches':inventory['patch_order'],'functional_check_count':len(main['checks']),
 'pure_packing_decision':'READY_FOR_SCOPED_LANDING_REVIEW','checked_initialization_decision':'COMPONENT_VALIDATED_FACTORY_GATE_OPEN',
 'runtime_model_update':'NOT_IMPLEMENTED_OWNER_REFERENCE_AND_RAW_BACKEND_GATES_OPEN',
 'production_edits':0,'ROS_initialized':False,'new_owned_runs':0,'qualification':qualified,'production_B_mode':'MANUAL+RC override',
 'historical126_process_failure':'retained, not superseded or waived by this new review'}
save(ROOT/'evidence/final_verification_v1.json',verification)
save(ROOT/'postrun/next_plan_v1.json',{'next_steps':['Actual factory routing/build-mode tests for new constructor rejection','RawBackend common-header reuse draft and cold/native policy regression','Worker unique-owner lifecycle and immutable capability descriptor design','Model/reference identity and target-tick activation contract','Only then separately scoped landing/freeze/necessary owned evidence'],
 'immediate_scope':'isolated component/interface work','automatic_production_landing':False,'automatic_owned_runs':0,'qualification':qualified})
(ROOT/'CURRENT.md').write_text('''# 第127批：模型共享packing/setter独立评审完成

纯packing16/16保持；checked原行为14/14保持，2项有意新增拒绝成立。实验层使用同一物理共同头，19/19；10项单元断言及4个实际变异通过。当前源码和生成C重新编译，没有链接旧安装solver归档；功能配方C O1/C++ O2，不认证发布性能。

三份当前补丁见`postrun/patch_inventory_v2.json`，均只在私有目录应用核对。生产源修改0、ROS/owned0；M4/F6/P1/plant/硬实时全false。126历史过程失败保留。

[完整报告](documents/方案A_第127批_模型共享setter独立评审与分项补丁_2026-10-26.md)

结论：纯packing可进入单项落位评审；checked初始化仍有工厂fallback门；运行时热更新的Worker所有者、完整reference绑定、实际RawBackend复用均未闭合。当前`postrun/next_plan_v1.json`按该顺序继续，不自动落位或启动owned。

保护与并发差额：`evidence/final_verification_v1.json`；不恢复或覆盖外部任务的工作区变化。MPC交付状态以独立回读回执为准。
''')
print(json.dumps({'status':verification['status'],'checks':checks,'input_files':len(expected),'previous126_files_verified':len(protected),'workspace_drift':len(workspace_drift)},ensure_ascii=False))
sys.exit(0 if all(checks.values())else 2)
