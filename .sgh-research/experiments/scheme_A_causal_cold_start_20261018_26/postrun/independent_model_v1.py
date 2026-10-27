# Independent scalar dynamics and objective retained from the audited batch23 Python implementation.
# Parent source SHA256: ed9de103ff30b3e70fcfbc781b045f3d4b7f247aa9229f13a2e6012c1a776d3a
from pathlib import Path
import hashlib,json,math
import numpy as np

def require(v,m):
 if not v:raise ValueError(m)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def load(p):return json.loads(Path(p).read_text())

def matrix(v,shape):
 a=np.asarray(v,dtype=float);require(a.size==math.prod(shape) and np.isfinite(a).all(),'finite matrix and exact shape');return a.reshape(shape,order='F')

def forward(x,control,c):
 h=c['hydro'];step=c['dt']/4
 a=h['mass']-h['Xu_dot'];b=h['mass']-h['Yv_dot'];d=h['mass']*h['xg']-h['Yr_dot'];e=h['mass']*h['xg']-h['Nv_dot'];f=h['Iz']-h['Nr_dot'];det=b*f-d*e
 def ode(s):
  psi,u,v,r=s[2:];tl,tr=control;c13=-b*v-d*r;c23=a*u
  du=-h['Xu']-h['Xuu']*abs(u);dv=-h['Yv']-h['Yvv']*abs(v);dvr=-h['Yr']-h['Yrr']*abs(r);drv=-h['Nv']-h['Nvv']*abs(v);dr=-h['Nr']-h['Nrr']*abs(r)
  ru=tl+tr-c13*r-du*u;rv=-c23*r-dv*v-dvr*r;rr=h['d_thruster']*(tr-tl)+c13*u+c23*v-drv*v-dr*r
  return np.array([math.cos(psi)*u-math.sin(psi)*v,math.sin(psi)*u+math.cos(psi)*v,r,ru/a,(f*rv-d*rr)/det,(-e*rv+b*rr)/det])
 y=x.copy()
 for _ in range(4):
  k1=ode(y);k2=ode(y+.5*step*k1);k3=ode(y+.5*step*k2);k4=ode(y+step*k3);y=y+step/6*(k1+2*k2+2*k3+k4)
 y[2]=math.atan2(math.sin(y[2]),math.cos(y[2]));return y

def objective(x,u,reference,anchor,c):
 q=np.array(c['Q']);r=np.array(c['R']);rd=np.array(c['Rd']);dt=c['dt'];err=x-reference;du=u-np.column_stack([anchor,u[:,:-1]])
 parts={
 'stage_position_dt_scaled':float(dt*np.sum(q[:2,None]*err[:2,:-1]**2)),
 'stage_velocity_dt_scaled':float(dt*np.sum(q[3:,None]*err[3:,:-1]**2)),
 'stage_heading_dt_scaled':float(dt*np.sum(2*q[2]*(1-np.cos(err[2,:-1])))),
 'stage_absolute_control_dt_scaled':float(dt*np.sum(r[:,None]*u**2)),
 'stage_control_increment_dt_scaled':float(dt*np.sum(rd[:,None]*du**2)),
 'terminal_state_not_dt_scaled':float(c['Qf_scale']*(sum(q[i]*err[i,-1]**2 for i in [0,1,3,4,5])+2*q[2]*(1-math.cos(err[2,-1]))))}
 parts['total']=math.fsum(parts.values());return parts

