# AI Test Platform - 用户认证 API
# 登录 / 注册 / 获取当前用户

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.database import async_session
from app.models import User
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from app.auth import hash_password, verify_password, create_access_token, require_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=dict)
async def register(data: UserRegister):
    """用户注册"""
    async with async_session() as session:
        # 检查用户名是否已存在
        result = await session.execute(select(User).where(User.username == data.username))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )

        user = User(
            username=data.username,
            display_name=data.display_name or data.username,
            password_hash=hash_password(data.password),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        token = create_access_token(user.id, user.username)
        return {
            "success": True,
            "message": "注册成功",
            "data": {
                "access_token": token,
                "token_type": "bearer",
                "user": {"id": user.id, "username": user.username, "display_name": user.display_name},
            },
        }


@router.post("/login", response_model=dict)
async def login(data: UserLogin):
    """用户登录"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == data.username))
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被禁用",
            )

        token = create_access_token(user.id, user.username)
        return {
            "success": True,
            "message": "登录成功",
            "data": {
                "access_token": token,
                "token_type": "bearer",
                "user": {"id": user.id, "username": user.username, "display_name": user.display_name},
            },
        }


@router.get("/me", response_model=dict)
async def get_me(user: User = Depends(require_user)):
    """获取当前登录用户信息"""
    return {
        "success": True,
        "data": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }
