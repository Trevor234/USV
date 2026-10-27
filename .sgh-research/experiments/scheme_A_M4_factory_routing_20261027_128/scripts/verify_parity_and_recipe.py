from pathlib import Path
import json, math, platform, subprocess
from run_matrix import ROOT, command, pin, save

out=ROOT/'evidence/parity_and_recipe01';out.mkdir(exist_ok=False)
v=json.loads((ROOT/'evidence/validation01/verification.json').read_text())
assert v['complete'] and v['case_count']==78
directory=ROOT/'evidence/validation01/cases'
cases=['NOMINAL','CUSTOM','SETTER_ERROR','CAPSULE_NULL','BAD_N','BAD_DT','NEGATIVE_WEIGHT','DIRECT_NOMINAL']
ignored={'solve_time_ms_observation_only','mapped_shared_objects'}
max_difference=0.0
def compare(a,b,path=''):
    global max_difference
    assert type(a)==type(b), ('type',path)
    if isinstance(a,dict):
        assert a.keys()==b.keys(),('keys',path)
        for k in a:
            if k not in ignored:compare(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        assert len(a)==len(b),('length',path)
        for i,(x,y)in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
    elif isinstance(a,float):
        assert math.isfinite(a)and math.isfinite(b),('nonfinite',path)
        d=abs(a-b);max_difference=max(max_difference,d)
        assert d<=1e-8,('numeric',path,a,b)
    else:assert a==b,('value',path,a,b)

parity=[]
for mode in ['off','on']:
    for case in cases:
        a=json.loads((directory/'checked_init'/mode/case/'result.json').read_text())
        b=json.loads((directory/'admission_guard'/mode/case/'result.json').read_text())
        compare(a,b)
        parity.append({'mode':mode,'case':case,'passed':True})
commands=json.loads((ROOT/'build/validation01/compile_commands.json').read_text())
recipe_checks={}
recipes=[]
for variant in ['baseline','checked_init','admission_guard']:
    for mode in ['off','on']:
        target=f'factory_{variant}_{mode}'
        compiler=next(r for r in commands if f'route_{variant}_{mode}.dir' in r['command'])
        assert ('-DUSV_MPC_HAS_CASADI' in compiler['command'])==(mode=='on')
        assert ('-D_GLIBCXX_USE_CXX11_ABI=0' in compiler['command'])==(mode=='on')
        link=(ROOT/'build/validation01/CMakeFiles'/(target+'.dir')/'link.txt').read_text()
        assert '/usv_mpc_ws/install/'not in link
        assert str(ROOT/'implementation/libgenerated_current.a')in link
        assert all('/home/trevor/acados/lib/'+n in link for n in ['libacados.so','libhpipm.so','libblasfeo.so'])
        metadata=command(['readelf','-d',ROOT/'build/validation01'/target],out/(target+'_dynamic'))
        assert metadata['returncode']==0
        dynamic=(out/(target+'_dynamic.stdout')).read_text()
        assert ('libcasadi.so'in dynamic)==(mode=='on')
        assert 'libacados.so'in dynamic
        recipe_checks[target]=True
        recipes.append({'target':target,'factory_compile':compiler,'link':link,
                        'ELF':pin(ROOT/'build/validation01'/target)})
native_paths=['/home/trevor/acados/lib/libacados.so','/home/trevor/acados/lib/libhpipm.so']
for name in native_paths:
    assert name in v['runtime_shared_objects'],('registered_runtime_not_observed',name)
inputs=json.loads((ROOT/'evidence/inputs/manifest_v1.json').read_text())
for p,record in v['runtime_shared_objects'].items():
    if p in inputs['runtime_libraries']:assert record==inputs['runtime_libraries'][p],('runtime_pin',p)
save(out/'verification.json',{'complete':True,'finite_parity_cases':parity,
   'max_absolute_numeric_difference':max_difference,'recipe_checks':recipe_checks,'recipes':recipes,
   'host':{'machine':platform.machine(),'platform':platform.platform(),'python':platform.python_version()},
   'timing_comparison':False,'production_CMake_ament_build_performed':False,
   'scope':'Standalone builds reproduce both factory macros and Casadi ABI recipe; not a full ROS package/owned/Pi build'})
print(json.dumps({'complete':True,'finite_parity_cases':len(parity),'max_absolute_numeric_difference':max_difference,'recipes':len(recipes)}))
