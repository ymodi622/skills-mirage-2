from datetime import datetime, timezone
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.models.user import User
from app.core.security import verify_password, get_password_hash
from app.core.config import settings
from app.core.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

class AuthService:
    @staticmethod
    def register_user(db: Database, email: str, password: str):
        # 1. Check if user already exists
        existing_user = db["users"].find_one({"email": email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists."
            )
        # 2. Hash password & prepare document
        hashed_pw = get_password_hash(password)
        new_user = {
            "email": email,
            "password": hashed_pw
        }
        # 3. Insert with error handling
        try:
            res = db["users"].insert_one(new_user)
            if not res.acknowledged or not res.inserted_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user record."
                )
            return {
                "message": "User registered successfully",
                "user_id": str(res.inserted_id)
            }
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists."
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while saving user."
            )
 


    @staticmethod
    def authenticate_user(db: Database, email: str, password: str) -> User:
        user_doc = db["users"].find_one({"email": email})
        if not user_doc or not verify_password(password, user_doc.get("password", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_doc["_id"] = str(user_doc["_id"])
        return User(**user_doc)

    @staticmethod
    def get_current_user(token: str = Depends(oauth2_scheme), db: Database = Depends(get_db)) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_email: str = payload.get("sub")
            if user_email is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        user_doc = db["users"].find_one({"email": user_email})
        if user_doc is None:
            raise credentials_exception
        user_doc["_id"] = str(user_doc["_id"])
        if "skills" in user_doc and isinstance(user_doc["skills"], list):
            user_doc["skills"] = [str(s) for s in user_doc["skills"]]
        return User(**user_doc)


