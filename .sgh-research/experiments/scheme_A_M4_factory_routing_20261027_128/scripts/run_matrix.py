from pathlib import Path
import argparse, hashlib, json, math, os, subprocess, time

ROOT=Path(__file__).resolve().parents[1]
CASES=['NOMINAL','CUSTOM','SETTER_ERROR','CAPSULE_NULL','BAD_N','BAD_DT','NAN_HYDRO','INF_HYDRO',
       'NAN_WEIGHT','NEGATIVE_WEIGHT','DIRECT_NOMINAL','DIRECT_NAN_HYDRO','DIRECT_INF_HYDRO']
ENV={**os.environ, 'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
     'VECLIB_MAXIMUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1',
     'LD_LIBRARY_PATH':'/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'+
       ((':'+os.environ['LD_LIBRARY_PATH']) if os.environ.get('LD_LIBRARY_PATH') else '')}

def pin(p):
    b=Path(p).read_bytes(); return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}

def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f: json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n')

def command(args, prefix, timeout=120):
    start=time.monotonic()
    try:
        p=subprocess.run([str(a) for a in args],capture_output=True,text=True,env=ENV,timeout=timeout)
        rc=p.returncode; out=p.stdout; err=p.stderr
    except subprocess.TimeoutExpired as e:
        rc='timeout'; out=(e.stdout or b''); err=(e.stderr or b'')
        if isinstance(out,bytes):out=out.decode(errors='replace')
        if isinstance(err,bytes):err=err.decode(errors='replace')
    prefix.parent.mkdir(parents=True,exist_ok=True)
    with prefix.with_suffix('.stdout').open('x') as f:f.write(out)
    with prefix.with_suffix('.stderr').open('x') as f:f.write(err)
    result={'argv':[str(a)for a in args],'returncode':rc,'elapsed_s':time.monotonic()-start,
            'declared_runtime_environment':{k:ENV[k]for k in ['LD_LIBRARY_PATH','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']}}
    save(prefix.with_suffix('.json'),result)
    return result

def verify_record(row, variant, mode):
    id=row['case']; direct=id.startswith('DIRECT_'); on=mode=='on'
    assert row['ROS_initialized'] is False and row['stage_qualified'] is False, 'scope'
    assert row['created']==row['graph_freed']==row['capsule_freed'], 'capsule_balance'
    assert all(s['n']==30 for s in row['setter_calls']), 'setter_dimension'
    if direct and not on:
        assert row['available'] is False and not row['constructed'] and row['allocation_attempts']==0, 'direct_disabled'
        return
    if 'HYDRO' in id:
        if variant=='admission_guard':
            assert not row['constructed'] and row['exception_type']=='invalid_argument', 'nonfinite_factory_rejected'
            assert row['allocation_attempts']==0 and not row['setter_calls'], 'nonfinite_rejected_before_allocation'
            assert 'p_global' in row['exception'], 'nonfinite_reason'
        elif direct or variant=='baseline' or on:
            assert row['constructed'], 'historical_invalid_model_admitted'
        else:
            assert not row['constructed'] and row['exception'], 'checked_without_fallback_rejected'
        assert row['rows']==[] and row['native_solves']==0, 'invalid_model_never_solved'
        return
    if id in ['NAN_WEIGHT','NEGATIVE_WEIGHT']:
        assert not row['constructed'] and row['exception'], 'invalid_weight_rejected'
        return
    needs_fallback = direct or id in ['CAPSULE_NULL','BAD_N','BAD_DT'] or (id=='SETTER_ERROR' and variant!='baseline')
    if needs_fallback and not on:
        assert not row['constructed'] and 'no solver backend available' in row['exception'], 'fallback_disabled_error'
        assert row['native_solves']==0, 'fallback_disabled_no_solve'
        return
    expected_backend='casadi' if needs_fallback else 'acados'
    assert row['constructed'] and row['backend']==expected_backend, 'selected_backend'
    if id=='SETTER_ERROR' and variant=='baseline':
        assert row['reported_setter_failures']==1 and row['rows']==[], 'historical_ignored_status'
        return
    assert len(row['rows'])==2, 'cold_and_second_solve'
    for r in row['rows']:
        assert r['success'] is True and r['finite'] is True, 'finite_successful_solve'
        assert r['backend']==expected_backend, 'diagnostic_backend'
        assert r['X']['rows']==6 and r['X']['cols']==(20 if id=='BAD_N' else 21), 'state_shape'
        assert r['U']['rows']==2 and r['U']['cols']==(19 if id=='BAD_N' else 20), 'control_shape'
        assert r['trajectory']['rows']==6, 'warm_trajectory'
    assert row['native_solves']==(2 if expected_backend=='acados' else 0), 'real_native_solve_count'
    if expected_backend=='casadi':
        assert any('libcasadi_nlpsol_ipopt.so' in p for p in row['mapped_shared_objects']), 'real_ipopt_loaded'

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--attempt',required=True)
    parser.add_argument('--variants',nargs='+',default=['baseline','checked_init']); args=parser.parse_args()
    out=ROOT/'evidence'/args.attempt; out.mkdir(exist_ok=False)
    build=ROOT/'build'/args.attempt
    config=command(['cmake','-S',ROOT/'implementation/cmake','-B',build,'-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'],out/'configure')
    assert config['returncode']==0,'configure_failed'
    built=command(['cmake','--build',build,'-j2'],out/'build',timeout=180)
    if built['returncode']!=0:
        save(out/'verification.json',{'complete':False,'failures':['build_failed'],'build':built});return 2
    rows={}; failures=[]
    for variant in args.variants:
        for mode in ['off','on']:
            for id in CASES:
                key=f'{variant}/{mode}/{id}'; dest=out/'cases'/key
                meta=command([build/f'factory_{variant}_{mode}',id,dest],dest.parent/(id+'_process'),timeout=30)
                if meta['returncode']!=0:
                    failures.append({'case':key,'reason':'process_failure','meta':meta});continue
                row=json.loads((dest/'result.json').read_text()); rows[key]=row
                try:verify_record(row,variant,mode)
                except AssertionError as e:failures.append({'case':key,'reason':str(e)})
    mapped={p for r in rows.values()for p in r['mapped_shared_objects']}
    pins={p:pin(p)for p in mapped if Path(p).is_file()}
    result={'complete':not failures,'case_count':len(rows),'failures':failures,'runtime_shared_objects':pins,
            'ELF':{p.name:pin(p) for p in build.glob('factory_*')if p.is_file()},
            'scope':'standalone component routing, actual CasADi/IPOPT, no ROS or owned',
            'qualification':{k:False for k in ['M4','F6','P1','plant','hard_realtime']}}
    save(out/'verification.json',result)
    print(json.dumps({k:result[k]for k in ['complete','case_count','failures']},ensure_ascii=False))
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
