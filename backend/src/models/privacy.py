from sqlalchemy import Column,Integer,String,JSON,Float,Text
from ..config.database import Base
class PrivacyBudget(Base):
    __tablename__='privacy_budget'
    id=Column(Integer,primary_key=True)
    total_epsilon=Column(Float,nullable=False)
    sample_cap=Column(Integer,nullable=False)
    spent_epsilon=Column(Float,nullable=False,default=0.0)
class PrivacyRelease(Base):
    __tablename__='privacy_releases'
    id=Column(Integer,primary_key=True)
    fingerprint=Column(String(64),unique=True,nullable=False,index=True)
    run_id=Column(Integer,nullable=False)
    state=Column(String(20),nullable=False,default='charged')
    epsilon=Column(Float,nullable=False)
    sample_cap=Column(Integer,nullable=False)
    mechanism=Column(String(40),nullable=False)
    sensitivity=Column(Text,default='')
    references=Column(JSON,nullable=False)
    noisy=Column(JSON,nullable=False)
    created_by=Column(String(120),nullable=False)
    created_at=Column(String(40),nullable=False)
    published_at=Column(String(40),default='')
