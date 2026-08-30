"""Registration, login, and current-user endpoints."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserResponse
from app.security.authentication import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(data: UserCreate, database: DatabaseSession) -> User:
    """Create a user with a securely hashed password."""
    normalized_email = str(data.email).lower()
    existing_user = database.scalar(select(User).where(User.email == normalized_email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        name=data.name.strip(),
        email=normalized_email,
        hashed_password=hash_password(data.password),
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, database: DatabaseSession) -> TokenResponse:
    """Verify credentials and return a JWT access token."""
    normalized_email = str(data.email).lower()
    user = database.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user
