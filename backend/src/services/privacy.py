import hashlib,json,threading
import numpy as np
from fastapi import HTTPException
from sqlalchemy import select,func
from ..config.settings import PRIVACY_TOTAL_EPSILON,PRIVACY_SAMPLE_CAP
from ..models.privacy import PrivacyBudget,PrivacyRelease
from ..utils.serialization import row,now
from .runs import get_run
from .audit import log
MECHANISM='laplace-counts-v1'
SENSITIVITY='相邻数据：增删一个微站。观测数/分区数/噪声数均为计数查询，任一计数变化不超过1，L1 敏感度 Δ=1；三项均分本次 ε，拉普拉斯尺度 b=3/ε；截断到 [0, 样本上限] 与四舍五入为后置处理，不额外消耗预算。'
_charge_lock=threading.Lock()
def ensure_budget(db):
    b=db.get(PrivacyBudget,1)
    if not b:
        b=PrivacyBudget(id=1,total_epsilon=PRIVACY_TOTAL_EPSILON,sample_cap=PRIVACY_SAMPLE_CAP,spent_epsilon=0.0)
        db.add(b);db.commit()
    return b
def budget_view(db):
    b=ensure_budget(db)
    return {'total_epsilon':b.total_epsilon,'spent_epsilon':round(b.spent_epsilon,6),'remaining_epsilon':round(max(0.0,b.total_epsilon-b.spent_epsilon),6),'sample_cap':b.sample_cap,'published':db.scalar(select(func.count()).select_from(PrivacyRelease).where(PrivacyRelease.state=='published'))}
def _fingerprint(run,records,epsilon,cap):
    payload={'mechanism':MECHANISM,'epsilon':epsilon,'sample_cap':cap,'parameters':run.parameters,'samples':sorted(([r['reference'],r['values']] for r in records),key=lambda x:x[0])}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _exact_counts(result):
    rows=result['rows']
    return {'stations':len(rows),'clusters':len({r['cluster'] for r in rows if r['cluster']!=-1}),'noise':sum(1 for r in rows if r['cluster']==-1)}
def _noisy(exact,epsilon,cap):
    rng=np.random.default_rng();scale=3.0/epsilon
    return {k:round(min(cap,max(0.0,v+float(rng.laplace(0.0,scale)))),3) for k,v in exact.items()}
def _component_spend(entries,new_refs,new_epsilon):
    parent=list(range(len(entries)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    seen={}
    for i,(_,refs) in enumerate(entries):
        for r in refs:
            j=seen.get(r)
            if j is None:seen[r]=i
            else:
                a,c=find(i),find(j)
                if a!=c:parent[a]=c
    comp={}
    for i,(eps,_) in enumerate(entries):comp[find(i)]=comp.get(find(i),0.0)+eps
    touched={find(seen[r]) for r in new_refs if r in seen}
    merged=new_epsilon+sum(comp.pop(t,0.0) for t in touched)
    return max([merged,*comp.values()])
def publish(db,user,data):
    run=get_run(db,data.run_id)
    if run.state!='completed' or not run.result:raise HTTPException(409,'仅已完成的研究可发布公开摘要')
    budget=ensure_budget(db);records=run.snapshot['records']
    if len(records)>budget.sample_cap:raise HTTPException(422,'样本数超出预先约定的样本上限 %d，不可公开发布'%budget.sample_cap)
    epsilon=data.epsilon;fp=_fingerprint(run,records,epsilon,budget.sample_cap)
    existing=db.scalar(select(PrivacyRelease).where(PrivacyRelease.fingerprint==fp))
    if existing:return _finish(db,user,existing,recovered=existing.state=='charged')
    noisy=_noisy(_exact_counts(run.result),epsilon,budget.sample_cap)
    refs=sorted(r['reference'] for r in records)
    with _charge_lock:
        budget=db.scalar(select(PrivacyBudget).where(PrivacyBudget.id==1).with_for_update())
        again=db.scalar(select(PrivacyRelease).where(PrivacyRelease.fingerprint==fp))
        if again:
            db.commit();return _finish(db,user,again,recovered=again.state=='charged')
        entries=[(x.epsilon,set(x.references)) for x in db.scalars(select(PrivacyRelease))]
        new_spent=_component_spend(entries,refs,epsilon)
        if new_spent>budget.total_epsilon+1e-9:
            db.rollback()
            log(db,user,'privacy.rejected',run.id,'需 ε=%.4f，超出剩余预算'%epsilon);db.commit()
            raise HTTPException(409,'隐私预算不足：本次需 ε=%.3f，剩余 %.3f；未扣费且未返回结果'%(epsilon,max(0.0,budget.total_epsilon-budget.spent_epsilon)))
        rel=PrivacyRelease(fingerprint=fp,run_id=run.id,state='charged',epsilon=epsilon,sample_cap=budget.sample_cap,mechanism=MECHANISM,sensitivity=SENSITIVITY,references=refs,noisy=noisy,created_by=user.email,created_at=now(),published_at='')
        db.add(rel);db.flush()
        budget.spent_epsilon=new_spent
        log(db,user,'privacy.charged',rel.id,'ε=%.4f，累计 %.4f/%.4f'%(epsilon,new_spent,budget.total_epsilon))
        db.commit()
    return _finish(db,user,rel,recovered=False)
def _finish(db,user,rel,recovered):
    if rel.state=='charged':
        rel.state='published';rel.published_at=now()
        log(db,user,'privacy.recovered' if recovered else 'privacy.published',rel.id,'指纹 '+rel.fingerprint[:12]);db.commit()
    return view(rel)
def view(rel):
    d=row(rel);d.pop('references',None);return d
def public_view(rel):
    return {'id':rel.id,'epsilon':rel.epsilon,'noisy':rel.noisy,'mechanism':rel.mechanism,'sensitivity':rel.sensitivity,'sample_cap':rel.sample_cap,'fingerprint':rel.fingerprint,'published_at':rel.published_at}
def list_releases(db):
    return [view(x) for x in db.scalars(select(PrivacyRelease).order_by(PrivacyRelease.id.desc()))]
def list_public(db):
    return [public_view(x) for x in db.scalars(select(PrivacyRelease).where(PrivacyRelease.state=='published').order_by(PrivacyRelease.id.desc()))]
