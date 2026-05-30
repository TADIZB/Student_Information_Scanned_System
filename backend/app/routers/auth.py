"""Router xử lý đăng ký / đăng nhập / đăng xuất."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session as DBSession

from ..auth import (
    get_current_user,
    login_user,
    logout_user,
    register_hust,
    register_local,
)
from ..database import get_db
from ..models import User
from ..schemas import LoginPayload, RegisterHustPayload, RegisterLocalPayload

router = APIRouter(tags=["auth"])


@router.post("/register/hust", status_code=201)
def register_hust_route(
    payload: RegisterHustPayload, response: Response, db: DBSession = Depends(get_db)
):
    return register_hust(
        payload.email, payload.password, payload.full_name, payload.birth_date, response, db
    )


@router.post("/register/local", status_code=201)
def register_local_route(
    payload: RegisterLocalPayload, response: Response, db: DBSession = Depends(get_db)
):
    return register_local(
        payload.username, payload.password, payload.full_name, payload.birth_date, response, db
    )


@router.post("/login")
def login(payload: LoginPayload, response: Response, db: DBSession = Depends(get_db)):
    return login_user(payload.identifier, payload.password, response, db)


@router.post("/logout")
def logout(response: Response):
    return logout_user(response)


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "birth_date": current_user.birth_date,
    }
