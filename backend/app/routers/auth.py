from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.database import Database
from typing import Any

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.auth import Token, LoginRequest
from app.schemas.user import UserRegister, RegisterResponse
from app.services.auth_service import AuthService
from app.models.user import User

router = APIRouter()

@router.post("/register", response_model = RegisterResponse)
def register(register_data:UserRegister, db: Database = Depends(get_db)):
    res = AuthService.register_user(db=db, email=register_data.email, password=register_data.password)
    return res

@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, db: Database = Depends(get_db)) -> Any:
    """
    Authenticate user and return JWT access token.
    """
    user = AuthService.authenticate_user(db=db, email=login_data.email, password=login_data.password)
    access_token = create_access_token(subject=user.email)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/login/access-token", response_model=Token)
def login_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Database = Depends(get_db)) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = AuthService.authenticate_user(db=db, email=form_data.username, password=form_data.password)
    access_token = create_access_token(subject=user.email)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me")
def get_current_user_profile(current_user: User = Depends(AuthService.get_current_user)) -> Any:
    """
    Get current logged in user details.
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "created_at": current_user.created_at
    }


