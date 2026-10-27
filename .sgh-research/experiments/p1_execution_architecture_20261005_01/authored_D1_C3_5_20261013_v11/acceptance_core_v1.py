"""Typed dependency evaluation for a bounded, explicitly scoped contract."""
from __future__ import annotations
import hashlib,json,math,os,stat,time
from pathlib import Path

STATES=('passed','failed','unknown','not_run')
PROFILE='frozen-N10-synthetic-shadow-components'
PHASES=('B4','M0b','B5','M4')
QUALIFICATIONS=('strict_full_chain','C3_general','D1','B4','M0b','B5','M4','F6','P1','execute',
                'dynamic_20s_R5','mixed_turn','true_master_clock','research_conclusion')

def require(value,code):
    if not value:raise ValueError(code)

def finite_tree(x):
    if type(x) is float:require(math.isfinite(x),'nonfinite_json')
    elif type(x) is int:require(-(1<<63)<=x<(1<<64),'integer_out_of_native_domain')
    elif type(x) is list:
        for v in x:finite_tree(v)
    elif type(x) is dict:
        for k,v in x.items():require(type(k) is str,'nonstring_JSON_key');finite_tree(v)
    return x

def strict_json(raw):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'duplicate_json_key');out[k]=v
        return out
    return finite_tree(json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_json'))))

def digest(raw):return hashlib.sha256(raw).hexdigest()

class Reader:
    """No-follow component-wise reads with stable FD/name and finite budgets."""
    def __init__(self,seconds=120,max_bytes=512*1024*1024,max_files=5000):
        self.deadline=time.monotonic()+seconds;self.max_bytes=max_bytes;self.max_files=max_files
        self.hashes={};self.total=0
    def raw(self,path,limit=128*1024*1024,remember=True):
        p=Path(path);require(p.is_absolute() and '..' not in p.parts,'absolute_normalized_input_required')
        directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);fd=None
        try:
            for part in p.parts[1:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
                os.close(directory);directory=child
            fd=os.open(p.name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
            before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=limit,'bounded_regular_input_required')
            pieces=[];size=0
            while True:
                require(time.monotonic()<=self.deadline,'offline_reader_time_budget')
                b=os.read(fd,min(1048576,limit+1-size))
                if not b:break
                pieces.append(b);size+=len(b);require(size<=limit,'input_byte_budget')
            after=os.fstat(fd);named=os.stat(p.name,dir_fd=directory,follow_symlinks=False)
            identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            require(identity(before)==identity(after)==identity(named) and size==before.st_size,'input_changed_during_read')
            raw=b''.join(pieces)
        finally:
            if fd is not None:os.close(fd)
            os.close(directory)
        if remember:
            key=str(p);value=digest(raw)
            if key not in self.hashes:self.total+=len(raw)
            require(self.total<=self.max_bytes and len(self.hashes)<self.max_files,'aggregate_reader_budget')
            require(key not in self.hashes or self.hashes[key]==value,'input_changed_between_reads');self.hashes[key]=value
        return raw
    def json(self,path,limit=32*1024*1024):return strict_json(self.raw(path,limit))
    def verify(self,pin):
        require(type(pin) is dict and type(pin.get('sha256')) is str and len(pin['sha256'])==64,'pin_shape')
        raw=self.raw(pin['path']);require(digest(raw)==pin['sha256'],'fixed_input_SHA_differs:'+pin['path'])
        if 'bytes' in pin:require(type(pin['bytes']) is int and pin['bytes']==len(raw),'fixed_input_size_differs')
        return raw
    def unchanged(self):
        return all(digest(self.raw(p,remember=False))==h for p,h in self.hashes.items())

def exact_status(value):
    require(type(value) is str and value in STATES,'exact_four_state_required')
    return value

def combine(values):
    require(type(values) is list and bool(values),'nonempty_required_dependencies')
    for v in values:exact_status(v)
    if 'failed' in values:return 'failed'
    if 'unknown' in values:return 'unknown'
    if 'not_run' in values:return 'not_run'
    return 'passed'

def assess(rules,required,phase_requires,profile=PROFILE):
    require(profile==PROFILE,'unsupported_acceptance_profile')
    require(type(rules) is dict and bool(rules),'nonempty_rule_results')
    for name,row in rules.items():
        require(type(name) is str and type(row) is dict,'rule_result_shape')
        exact_status(row.get('status'))
    require(type(required) is list and required and len(set(required))==len(required),'component_required_shape')
    require(set(phase_requires)==set(PHASES),'exact_phase_dependency_set_required')
    require(all(k in rules for k in required),'missing_required_component')
    component=combine([rules[k]['status'] for k in required]);stages={}
    for phase in PHASES:
        deps=phase_requires[phase];require(type(deps) is list and deps and len(set(deps))==len(deps),'phase_required_shape')
        states=[]
        for dep in deps:
            if dep in rules:states.append(rules[dep]['status'])
            elif dep in stages:states.append(stages[dep]['status'])
            else:raise ValueError('missing_or_forward_phase_dependency:'+dep)
        status=combine(states)
        stages[phase]={'status':status,'required':deps,'all_required_passed':status=='passed',
                      'profile_supports_phase_qualification':False,'qualified':False}
    return {'component_status':component,'component_acceptance_passed':component=='passed',
            'stages':stages,'qualifications':{k:False for k in QUALIFICATIONS},
            'qualification_limit':'this contract profile accepts bounded frozen shadow components only; stage support requires a new execution contract'}

def report_result(report,key,rc):
    require(type(rc) is int,'subprocess_returncode_exact_integer')
    require(type(report) is dict and type(report.get(key)) is bool,'checker_result_exact_boolean')
    return 'passed' if rc==0 and report[key] is True else 'failed'
