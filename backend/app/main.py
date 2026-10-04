from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, users, jobs, courses, skills, analytics, recommendations, chatbot

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["Users"])
app.include_router(jobs.router, prefix=f"{settings.API_V1_STR}/jobs", tags=["Jobs"])
app.include_router(courses.router, prefix=f"{settings.API_V1_STR}/courses", tags=["Courses"])
app.include_router(skills.router, prefix=f"{settings.API_V1_STR}/skills", tags=["Skills"])
app.include_router(analytics.router, prefix=f"{settings.API_V1_STR}/analytics", tags=["Analytics"])
app.include_router(recommendations.router, prefix=f"{settings.API_V1_STR}/recommendations", tags=["Recommendations"])
app.include_router(chatbot.router, prefix=f"{settings.API_V1_STR}/chatbot", tags=["Chatbot"])

@app.get("/")
def read_root():
    return {"message": "Welcome to Skills Mirage API"}
