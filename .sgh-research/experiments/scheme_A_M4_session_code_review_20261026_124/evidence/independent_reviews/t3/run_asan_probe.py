import subprocess,json,pathlib
r=pathlib.Path('/tmp/review123_t3_register')
p=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t3q_impl_20261025_99/implementation/t2_author')
cmd=['g++','-std=c++17','-O1','-g','-fsanitize=address','-fsanitize-address-use-after-scope','-fno-omit-frame-pointer','-I',str(p/'observer/src/shadow'),'-I',str(p/'common'),str(p/'observer/tests/test_t3_queue_pressure.cpp'),'-o',str(r/'q2_asan'),'-pthread']
b=subprocess.run(cmd,capture_output=True,text=True,timeout=180);(r/'asan_build.log').write_text(b.stdout+b.stderr)
rec={'compile':cmd,'compile_rc':b.returncode}
if b.returncode==0:
 q=subprocess.run([str(r/'q2_asan'),'T3-Q2',str(r/'q2_asan_run')],capture_output=True,text=True,timeout=30)
 (r/'asan_stdout.log').write_text(q.stdout);(r/'asan_stderr.log').write_text(q.stderr);rec['run_rc']=q.returncode;rec['asan_stack_use_after_scope']='stack-use-after-scope' in q.stderr
(r/'asan_probe.json').write_text(json.dumps(rec,indent=2)+'\n')
print(json.dumps(rec))
