from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create(db: Session, *, email: str, full_name: str, password_hash: str, role: str = "customer") -> User:
    user = User(email=normalize_email(email), full_name=full_name.strip(), password_hash=password_hash, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, *, role: str | None = None, limit: int = 100, offset: int = 0) -> tuple[list[User], int]:
    query = select(User)
    if role:
        query = query.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total


def set_active(db: Session, user: User, active: bool) -> User:
    user.is_active = active
    db.commit()
    db.refresh(user)
    return user


def count_by_role(db: Session, role: str) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == role)) or 0
