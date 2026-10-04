from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Skills Mirage API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 300
    DATABASE_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "skills_mirage"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

