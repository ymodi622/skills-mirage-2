from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# Synchronous PyMongo Client
sync_client = MongoClient(settings.DATABASE_URL)
sync_db = sync_client[settings.DATABASE_NAME]

# Asynchronous Motor Client
async_client = AsyncIOMotorClient(settings.DATABASE_URL)
async_db = async_client[settings.DATABASE_NAME]

def get_db():
    """FastAPI dependency for accessing synchronous MongoDB database."""
    return sync_db

async def get_async_db():
    """FastAPI dependency for accessing asynchronous MongoDB database."""
    return async_db

