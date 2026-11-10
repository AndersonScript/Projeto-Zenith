"""Simulação em Python da matemática de 'apontar osso' do akira_vida.gd.
Objetivo: provar que, para QUALQUER convenção de eixos dos ossos (aleatória), o braço termina
apontando exatamente para a direção alvo (em espaço do esqueleto)."""
import numpy as np

def q_mul(a,b):
    w1,x1,y1,z1=a; w2,x2,y2,z2=b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def q_inv(q): return np.array([q[0],-q[1],-q[2],-q[3]])/np.dot(q,q)
def q_norm(q): return q/np.linalg.norm(q)
def q_from_axis(ax,ang):
    ax=ax/np.linalg.norm(ax); return np.concatenate([[np.cos(ang/2)], np.sin(ang/2)*ax])
def q_to_mat(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def mat_to_q(m):
    t=np.trace(m)
    if t>0:
        s=np.sqrt(t+1)*2; return q_norm(np.array([s/4,(m[2,1]-m[1,2])/s,(m[0,2]-m[2,0])/s,(m[1,0]-m[0,1])/s]))
    i=np.argmax(np.diag(m)); j=(i+1)%3; k=(i+2)%3
    s=np.sqrt(m[i,i]-m[j,j]-m[k,k]+1)*2
    q=np.zeros(4); q[1+i]=s/4; q[0]=(m[k,j]-m[j,k])/s; q[1+j]=(m[j,i]+m[i,j])/s; q[1+k]=(m[k,i]+m[i,k])/s
    return q_norm(q)
def q_arc(a,b):
    """Quaternion(from, to) do Godot: menor arco."""
    a=a/np.linalg.norm(a); b=b/np.linalg.norm(b)
    d=np.dot(a,b)
    if d<-0.999999:
        perp=np.cross(a,[1,0,0]); 
        if np.linalg.norm(perp)<1e-3: perp=np.cross(a,[0,1,0])
        return q_from_axis(perp,np.pi)
    c=np.cross(a,b); return q_norm(np.array([1+d,*c]))
def q_slerp_id(q,w):
    """identidade -> q com peso w"""
    if q[0]<0: q=-q
    ang=2*np.arccos(np.clip(q[0],-1,1))
    if ang<1e-9: return np.array([1.,0,0,0])
    ax=q[1:]/np.linalg.norm(q[1:]); return q_from_axis(ax,ang*w)
def rot(q,v): return q_to_mat(q)@v

class Skel:
    """cadeia: bone0=parent(clavícula/peito) -> bone1=upper -> bone2=lower -> bone3=hand.
       Cada osso tem rest local (translação + rotação ALEATÓRIA = convenção de eixos qualquer)."""
    def __init__(self, rng, lat_sign=1.0, tpose_dir=None):
        self.n=4; self.parent=[-1,0,1,2]
        self.rest_q=[]; self.rest_t=[]
        # em T-pose o braço aponta pra lat_sign*X. O osso tem eixos arbitrários: escolhemos a rotação GLOBAL
        # de cada osso aleatória e derivamos o local, e a translação do filho = comprimento ao longo do eixo do osso
        # que, em global, aponta pra direção do braço.
        self.glob_q=[]
        d=np.array([lat_sign,0,0.0]) if tpose_dir is None else tpose_dir
        L=[0.0,0.30,0.27,0.08]
        gpos=[np.array([0.0,1.4,0.0])]
        for i in range(1,4): gpos.append(gpos[-1]+d*L[i])
        for i in range(4):
            self.glob_q.append(q_norm(rng.normal(size=4)))
        self.rest_q=[];self.rest_t=[]
        for i in range(4):
            if self.parent[i]==-1:
                self.rest_q.append(self.glob_q[i]); self.rest_t.append(gpos[i])
            else:
                p=self.parent[i]
                self.rest_q.append(q_mul(q_inv(self.glob_q[p]),self.glob_q[i]))
                self.rest_t.append(rot(q_inv(self.glob_q[p]),gpos[i]-gpos[p]))
        self.pose_q=[q.copy() for q in self.rest_q]
    def gpose(self,i):
        if self.parent[i]==-1: return self.rest_t[i].copy(), self.pose_q[i].copy()
        po,pq=self.gpose(self.parent[i])
        return po+rot(pq,self.rest_t[i]), q_mul(pq,self.pose_q[i])

def aim(sk,bone,child,target,w=1.0):
    po,pq=sk.gpose(bone); co,_=sk.gpose(child)
    cur=co-po; cur/=np.linalg.norm(cur)
    swing=q_arc(cur,target/np.linalg.norm(target))
    if w<1: swing=q_slerp_id(swing,w)
    if sk.parent[bone]==-1: pqq=np.array([1.,0,0,0])
    else: _,pqq=sk.gpose(sk.parent[bone])
    sk.pose_q[bone]=q_norm(q_mul(q_mul(q_mul(q_inv(pqq),swing),pqq),sk.pose_q[bone]))

if __name__=="__main__":
    rng=np.random.default_rng(7)
    worst=0.0; worst_w=0.0
    for trial in range(400):
        lat_sign=rng.choice([-1.0,1.0])
        sk=Skel(rng,lat_sign)
        up=np.array([0,1.0,0]); lat=np.array([lat_sign,0,0.]); fwd=np.cross(up,lat)
        t_up=(lat*0.17+up*-0.98+fwd*0.05); t_lo=(lat*0.06+up*-0.93+fwd*0.32)
        # aplica em 1 passo
        aim(sk,1,2,t_up); aim(sk,2,3,t_lo)
        p1,_=sk.gpose(1);p2,_=sk.gpose(2);p3,_=sk.gpose(3)
        d1=(p2-p1)/np.linalg.norm(p2-p1); d2=(p3-p2)/np.linalg.norm(p3-p2)
        e=max(np.linalg.norm(d1-t_up/np.linalg.norm(t_up)),np.linalg.norm(d2-t_lo/np.linalg.norm(t_lo)))
        worst=max(worst,e)
        # suavização exponencial: após N quadros converge e nunca passa do alvo
        sk2=Skel(np.random.default_rng(trial),lat_sign)
        for f in range(60):
            aim(sk2,1,2,t_up,0.15); aim(sk2,2,3,t_lo,0.15)
        q1,_=sk2.gpose(1);q2,_=sk2.gpose(2)
        worst_w=max(worst_w,np.linalg.norm((q2-q1)/np.linalg.norm(q2-q1)-t_up/np.linalg.norm(t_up)))
    print("erro máx (1 passo, 400 convenções aleatórias):",f"{worst:.2e}")
    print("erro máx (suavizado, 60 quadros):",f"{worst_w:.2e}")
    # comprimento dos ossos preservado?
    sk=Skel(rng,1.0); aim(sk,1,2,np.array([0.2,-1,0.1])); 
    p1,_=sk.gpose(1);p2,_=sk.gpose(2); print("comprimento do braço preservado:", abs(np.linalg.norm(p2-p1)-0.27)<1e-9 or abs(np.linalg.norm(p2-p1)-0.30)<1e-9, f"{np.linalg.norm(p2-p1):.3f}")
