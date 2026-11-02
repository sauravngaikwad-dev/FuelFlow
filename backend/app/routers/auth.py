from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import User
from app.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    OperatorLoginRequest,
    AdminCreateOperatorRequest,
    TokenResponse,
    UserProfileResponse,
)
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_role,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/user/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Public endpoint: Register a normal customer user account.
    Role is strictly locked to 'user' on the backend.
    Public registration cannot create operators or administrators.
    """
    existing_user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing_user:
        if existing_user.username == payload.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is already registered."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered."
            )

    new_user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="user",  # Strictly locked to 'user'
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(
        data={"sub": str(new_user.id), "username": new_user.username, "role": new_user.role}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user_id=new_user.id,
        username=new_user.username,
        role=new_user.role,
    )


@router.post("/user/login", response_model=TokenResponse)
@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """Public endpoint: Authenticate user credentials and return signed JWT token."""
    user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.username)
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been deactivated."
        )

    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/operator/login", response_model=TokenResponse)
def login_operator(payload: OperatorLoginRequest, db: Session = Depends(get_db)):
    """
    Operator/Admin sign-in endpoint.
    Strictly enforces that the authenticated user possesses 'operator' or 'admin' role.
    Normal users attempting to sign in here are rejected with HTTP 403 Forbidden.
    """
    user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.username)
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect operator username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated."
        )

    if user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You do not have operator or administrator privileges."
        )

    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/admin/create-operator", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def admin_create_operator(
    payload: AdminCreateOperatorRequest,
    current_admin: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected administrator endpoint: Create an authorized operator account.
    Cannot be called by regular users or unauthenticated clients.
    """
    existing_user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email is already registered."
        )

    operator = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="operator",
        is_active=True,
    )
    db.add(operator)
    db.commit()
    db.refresh(operator)

    return UserProfileResponse(
        id=operator.id,
        username=operator.username,
        email=operator.email,
        role=operator.role,
        is_active=operator.is_active,
        created_at=operator.created_at,
    )


@router.get("/me", response_model=UserProfileResponse)
def get_current_profile(current_user: User = Depends(get_current_user)):
    """Return the profile and role of the currently authenticated user."""
    return UserProfileResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
