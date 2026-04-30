import re
from typing import Annotated
from pydantic import BaseModel, AfterValidator


def _loose_email(v: str) -> str:
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
        raise ValueError('value is not a valid email address')
    return v.lower()


LooseEmail = Annotated[str, AfterValidator(_loose_email)]


class UserCreate(BaseModel):
    email: LooseEmail
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: LooseEmail
    password: str
