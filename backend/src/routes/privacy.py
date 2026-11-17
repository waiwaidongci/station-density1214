from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.privacy import ReleaseInput
from ..services.auth import current_user,writer
from ..controllers.privacy import PrivacyController as C
router=APIRouter()
@router.get('/privacy/budget')
def budget(db=Depends(db_session),u=Depends(current_user)):return C.budget(db)
@router.get('/privacy/releases')
def releases(db=Depends(db_session),u=Depends(current_user)):return C.list(db)
@router.post('/privacy/releases')
def publish(data:ReleaseInput,db=Depends(db_session),u=Depends(writer)):return C.publish(db,u,data)
@router.get('/public/privacy/releases')
def public_releases(db=Depends(db_session)):return C.public(db)
