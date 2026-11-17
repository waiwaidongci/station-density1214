from pydantic import BaseModel,Field
class ReleaseInput(BaseModel):
    run_id:int
    epsilon:float=Field(gt=0,le=2.0)
