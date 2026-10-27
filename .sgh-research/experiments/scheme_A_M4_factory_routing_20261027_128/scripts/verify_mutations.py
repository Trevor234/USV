from pathlib import Path
import difflib, json, shlex
from run_matrix import ROOT, command, pin, save, verify_record

out=ROOT/'evidence/mutations01'
out.mkdir(exist_ok=False)
build=ROOT/'build/validation01'
baseline=json.loads((ROOT/'evidence/validation01/verification.json').read_text())
assert baseline['complete'] and baseline['case_count']==78, 'baseline_required'
source=ROOT/'implementation/admission_guard/src/mpc_solver.cpp'
original=source.read_text()
dynamic='make_dynamic_mpc(const MpcParams & params)\n{\n  validate_model_parameters(params);'
direct='make_casadi_dynamic_mpc(const MpcParams & params)\n{\n  validate_model_parameters(params);'
finite='std::all_of(values.begin(), values.end(), [](double x) { return std::isfinite(x); })'
fallback='return make_casadi_dynamic_mpc(params);'
specs=[
    ('delete_dynamic_admission',dynamic,dynamic.replace('  validate_model_parameters(params);',''),
     'NAN_HYDRO','nonfinite_rejected_before_allocation'),
    ('delete_direct_admission',direct,direct.replace('  validate_model_parameters(params);',''),
     'DIRECT_NAN_HYDRO','nonfinite_factory_rejected'),
    ('check_only_first_parameter',finite,'std::isfinite(values[0])',
     'INF_HYDRO','nonfinite_factory_rejected'),
    ('break_finite_fallback',fallback,'throw std::runtime_error("mutation_disabled_fallback");',
     'CAPSULE_NULL','selected_backend'),
]
commands=json.loads((build/'compile_commands.json').read_text())
recipe=next(r for r in commands if 'route_admission_guard_on.dir' in r['command'])
base_compile=shlex.split(recipe['command'])
base_link=shlex.split((build/'CMakeFiles/factory_admission_guard_on.dir/link.txt').read_text())
# Resolve relative CMake object/archive paths against their original build.
for i,arg in enumerate(base_link):
    if not arg.startswith('-') and not Path(arg).is_absolute() and (build/arg).is_file():
        base_link[i]=str(build/arg)
route_object=next(a for a in base_link if a.endswith('mpc_solver.cpp.o'))
records=[]
for name,needle,replacement,case,expected in specs:
    directory=out/name; directory.mkdir()
    occurrences=original.count(needle)
    item={'name':name,'occurrences':occurrences,'prepared':occurrences==1,'caught':False,
          'required_assertion':expected,'case':case}
    if occurrences!=1:
        item['failure']='unprepared';records.append(item);continue
    mutated=original.replace(needle,replacement,1)
    assert mutated!=original
    candidate=directory/'mpc_solver.cpp';candidate.write_text(mutated)
    (directory/'mutation.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),mutated.splitlines(True),fromfile='original',tofile=name)))
    obj=directory/'factory.o'
    compile_args=base_compile[:]
    compile_args[compile_args.index('-o')+1]=str(obj)
    compile_args[compile_args.index('-c')+1]=str(candidate)
    compiled=command(compile_args,directory/'compile')
    item['compiled']=compiled['returncode']==0
    if not item['compiled']:
        item['failure']='compile_failure_is_not_capture';records.append(item);continue
    exe=directory/'factory_mutant'
    link_args=[str(obj) if a==route_object else a for a in base_link]
    link_args[link_args.index('-o')+1]=str(exe)
    linked=command(link_args,directory/'link')
    item['linked']=linked['returncode']==0
    if not item['linked']:
        item['failure']='link_failure_is_not_capture';records.append(item);continue
    run=command([exe,case,directory/'case'],directory/'process',timeout=30)
    item['run_returncode']=run['returncode']
    if run['returncode']!=0:
        item['failure']='process_failure_is_not_capture';records.append(item);continue
    row=json.loads((directory/'case/result.json').read_text())
    try:verify_record(row,'admission_guard','on')
    except AssertionError as e:
        item['assertion']=str(e);item['caught']=str(e)==expected
    except Exception as e:
        item['failure']='non_assertion_'+type(e).__name__
    item['ELF']=pin(exe)
    records.append(item)
result={'complete':len(records)==4 and all(r['prepared'] and r['caught']for r in records),
        'mutations':records,'prepared_count':sum(r['prepared']for r in records),
        'caught_count':sum(r['caught']for r in records),
        'discipline':'Only intended runtime AssertionError counts; compiler, linker, crash, timeout, missing data do not'}
save(out/'verification.json',result)
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if result['complete']else 2)
