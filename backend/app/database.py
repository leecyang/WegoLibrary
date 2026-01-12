from typing import Optional, List
import os
from pathlib import Path
from sqlmodel import Field, SQLModel, create_engine, Session, select
from datetime import datetime
from sqlalchemy import inspect, text

# ============ 数据模型 ============

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)

class Config(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # user_id 保留用于兼容或作为非关联的标识，但在新系统中主要使用 owner_id
    user_id: str = Field(index=True, default="legacy") 
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")
    session_id: str
    major: int
    minor: int
    is_active: bool = True
    last_keepalive: Optional[datetime] = None
    last_checkin: Optional[datetime] = None
    last_checkin_result: Optional[str] = None
    last_log: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    auto_checkin_expire_at: Optional[datetime] = None

# ============ 数据库连接 ============

def _get_sqlite_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    raw_path = os.getenv("SQLITE_DB_PATH") or os.getenv("SQLITE_FILE") or "data/database.db"
    path = Path(raw_path)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()

    if path.exists() and path.is_dir():
        path = (path / "database.db").resolve()

    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


engine = create_engine(_get_sqlite_url(), connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    
    # 简单的自动迁移逻辑
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        with engine.connect() as conn:
            if "config" in existing_tables:
                columns = [col["name"] for col in inspector.get_columns("config")]
                
                if "user_id" not in columns:
                    print("Migrating: Adding user_id column to config table")
                    conn.execute(text("ALTER TABLE config ADD COLUMN user_id VARCHAR DEFAULT 'legacy'"))
                    conn.execute(text("CREATE INDEX ix_config_user_id ON config (user_id)"))
                
                if "created_at" not in columns:
                    print("Migrating: Adding created_at column to config table")
                    conn.execute(text("ALTER TABLE config ADD COLUMN created_at DATETIME"))
                
                if "owner_id" not in columns:
                    print("Migrating: Adding owner_id column to config table")
                    conn.execute(text("ALTER TABLE config ADD COLUMN owner_id INTEGER REFERENCES user(id)"))
                
                if "auto_checkin_expire_at" not in columns:
                    print("Migrating: Adding auto_checkin_expire_at column to config table")
                    conn.execute(text("ALTER TABLE config ADD COLUMN auto_checkin_expire_at DATETIME"))

            # 确保 User 表存在（SQLModel.metadata.create_all 应该已经创建了，但如果是新加的可能需要检查）
            
            conn.commit()
    except Exception as e:
        print(f"Migration warning: {e}")

# ============ 用户相关操作 ============

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()

def create_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

def get_all_users(session: Session) -> List[User]:
    return list(session.exec(select(User)).all())

def delete_user(session: Session, user_id: int):
    user = session.get(User, user_id)
    if user:
        # 同时删除关联的配置
        config = get_config_by_owner(session, user_id)
        if config:
            session.delete(config)
        session.delete(user)
        session.commit()

# ============ 配置相关操作 ============

def get_config_by_owner(session: Session, owner_id: int) -> Optional[Config]:
    """获取指定用户(owner_id)的配置"""
    statement = select(Config).where(Config.owner_id == owner_id)
    return session.exec(statement).first()

def get_all_configs(session: Session) -> List[Config]:
    """获取所有配置（管理员用）"""
    return list(session.exec(select(Config)).all())

def get_all_active_configs(session: Session) -> List[Config]:
    """获取所有活跃用户的配置（用于定时任务）"""
    statement = select(Config).where(Config.is_active == True)
    return list(session.exec(statement).all())

def update_config_by_owner(
    session: Session,
    owner_id: int,
    session_id: str,
    major: int,
    minor: int
) -> Config:
    """更新或创建用户配置"""
    config = get_config_by_owner(session, owner_id)
    if not config:
        config = Config(
            owner_id=owner_id,
            user_id=f"user_{owner_id}", # 兼容旧字段
            session_id=session_id,
            major=major,
            minor=minor
        )
        session.add(config)
    else:
        config.session_id = session_id
        config.major = major
        config.minor = minor
        config.is_active = True
    session.commit()
    session.refresh(config)
    return config

def log_keepalive_by_owner(session: Session, owner_id: int, success: bool, msg: str):
    """记录指定用户的保活日志"""
    config = get_config_by_owner(session, owner_id)
    if config:
        config.last_keepalive = datetime.now()
        config.last_log = f"KeepAlive: {msg}"
        session.add(config)
        session.commit()

def log_checkin_by_owner(session: Session, owner_id: int, success: bool, msg: str):
    """记录指定用户的签到日志"""
    config = get_config_by_owner(session, owner_id)
    if config:
        config.last_checkin = datetime.now()
        config.last_checkin_result = msg
        config.last_log = f"CheckIn: {msg}"
        session.add(config)
        session.commit()

def update_session_id_for_config(session: Session, config: Config, new_session_id: str):
    """更新配置的 session_id"""
    config.session_id = new_session_id
    session.add(config)
    session.commit()

# ============ 兼容旧接口（已标记为废弃，保留至完全重构完成） ============
# 下面的函数如果不再被 main.py 调用，可以删除。
# 考虑到我们要修改 main.py，这些其实可以删掉了，但我先保留一些辅助函数如果需要的话。
# 暂时不保留旧的 get_config_by_user (str) 接口，强迫上层修改。
