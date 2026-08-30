"""Reusable FastAPI endpoint dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.security.authentication import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
DatabaseSession = Annotated[Session, Depends(get_db)]
BearerToken = Annotated[str, Depends(oauth2_scheme)]


def get_current_user(token: BearerToken, database: DatabaseSession) -> User:
    """Return the active user identified by a valid bearer token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError as error:
        raise unauthorized from error

    user = database.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
