from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_recommendations():
    return {"message": "Recommendations endpoint"}
