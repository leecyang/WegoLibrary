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

class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.now)
    last_used_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    revoked_at: Optional[datetime] = None

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
    # 微信个人资料快照（粘贴授权链接时一次性写入，不做动态刷新）
    wechat_nick: Optional[str] = None
    wechat_avatar: Optional[str] = None
    wechat_student_name: Optional[str] = None
    wechat_student_no: Optional[str] = None
    wechat_sch: Optional[str] = None
    wechat_area_name: Optional[str] = None
    traceint_user_id: Optional[int] = None
    wechat_profile_at: Optional[datetime] = None

class Announcement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    draft_content: str = Field(default="")
    published_content: str = Field(default="")
    is_published: bool = Field(default=False)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)
    published_at: Optional[datetime] = None

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

                profile_columns = {
                    "wechat_nick": "VARCHAR",
                    "wechat_avatar": "VARCHAR",
                    "wechat_student_name": "VARCHAR",
                    "wechat_student_no": "VARCHAR",
                    "wechat_sch": "VARCHAR",
                    "wechat_area_name": "VARCHAR",
                    "traceint_user_id": "INTEGER",
                    "wechat_profile_at": "DATETIME",
                }
                for col_name, col_type in profile_columns.items():
                    if col_name not in columns:
                        print(f"Migrating: Adding {col_name} column to config table")
                        conn.execute(text(f"ALTER TABLE config ADD COLUMN {col_name} {col_type}"))

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
        auth_sessions = list(session.exec(select(AuthSession).where(AuthSession.user_id == user_id)).all())
        for auth_session in auth_sessions:
            session.delete(auth_session)
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

def get_auth_session_by_token_hash(session: Session, token_hash: str) -> Optional[AuthSession]:
    statement = select(AuthSession).where(AuthSession.token_hash == token_hash)
    return session.exec(statement).first()

def create_auth_session(
    session: Session,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
) -> AuthSession:
    auth_session = AuthSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    return auth_session

def update_auth_session(session: Session, auth_session: AuthSession) -> AuthSession:
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    return auth_session

def get_all_active_configs(session: Session) -> List[Config]:
    """获取所有活跃用户的配置（用于定时任务）"""
    statement = select(Config).where(Config.is_active == True)
    return list(session.exec(statement).all())

def apply_wechat_profile_to_config(config: Config, profile: dict) -> None:
    """将 profile 字典写入 Config 快照字段。"""
    config.wechat_nick = profile.get("nick")
    config.wechat_avatar = profile.get("avatar")
    config.wechat_student_name = profile.get("student_name")
    config.wechat_student_no = profile.get("student_no")
    config.wechat_sch = profile.get("sch")
    config.wechat_area_name = profile.get("area_name")
    raw_uid = profile.get("traceint_user_id")
    if raw_uid is not None:
        try:
            config.traceint_user_id = int(raw_uid)
        except (TypeError, ValueError):
            config.traceint_user_id = None
    else:
        config.traceint_user_id = None
    fetched_at = profile.get("fetched_at")
    if isinstance(fetched_at, datetime):
        config.wechat_profile_at = fetched_at
    elif isinstance(fetched_at, str):
        try:
            config.wechat_profile_at = datetime.fromisoformat(fetched_at)
        except ValueError:
            config.wechat_profile_at = datetime.now()
    else:
        config.wechat_profile_at = datetime.now()


def get_profile_display(config: Optional[Config]) -> str:
    """返回 profile 展示状态: none | pending | ready"""
    if not config or not (config.session_id or "").strip():
        return "none"
    if config.wechat_profile_at and config.wechat_nick:
        return "ready"
    return "pending"


# 登录态失效类错误（签到 Session 过期）
_WECHAT_SESSION_EXPIRED_MARKERS = (
    "登录状态已经失效",
    "无法重新登录",
    "登录状态已经失效无法重新登录",
)


def get_wechat_connection_status(config: Optional[Config]) -> str:
    """
    微信连接展示状态:
    - disconnected: 未配置 session
    - connected: 正常
    - expired: 登录态已失效（需重新授权）
    - unauthorized: 其他鉴权/签到失败
    """
    if not config or not (config.session_id or "").strip():
        return "disconnected"

    checkin_result = config.last_checkin_result or ""
    last_log = config.last_log or ""
    combined = f"{checkin_result} {last_log}"

    if any(marker in combined for marker in _WECHAT_SESSION_EXPIRED_MARKERS):
        return "expired"

    if checkin_result.startswith("签到失败"):
        return "unauthorized"

    if last_log and "KeepAlive" in last_log and "success" not in last_log.lower():
        if any(marker in last_log for marker in _WECHAT_SESSION_EXPIRED_MARKERS):
            return "expired"

    return "connected"


def build_wechat_profile_response(config: Optional[Config]) -> Optional[dict]:
    """构建 API 返回的 wechat_profile 对象。"""
    if get_profile_display(config) != "ready" or not config:
        return None
    return {
        "nick": config.wechat_nick,
        "avatar": config.wechat_avatar,
        "student_name": config.wechat_student_name,
        "student_no": config.wechat_student_no,
        "sch": config.wechat_sch,
        "area_name": config.wechat_area_name,
        "traceint_user_id": config.traceint_user_id,
    }


def update_config_by_owner(
    session: Session,
    owner_id: int,
    session_id: str,
    major: int,
    minor: int,
    profile: Optional[dict] = None,
) -> Config:
    """更新或创建用户配置；profile 非 None 时写入微信资料快照。"""
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
    if profile is not None:
        apply_wechat_profile_to_config(config, profile)
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

# ============ 公告相关操作 ============

def get_announcement(session: Session) -> Optional[Announcement]:
    return session.exec(select(Announcement)).first()

def get_or_create_announcement(session: Session) -> Announcement:
    announcement = get_announcement(session)
    if announcement:
        return announcement

    announcement = Announcement()
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return announcement

# ============ 兼容旧接口（已标记为废弃，保留至完全重构完成） ============
# 下面的函数如果不再被 main.py 调用，可以删除。
# 考虑到我们要修改 main.py，这些其实可以删掉了，但我先保留一些辅助函数如果需要的话。
# 暂时不保留旧的 get_config_by_user (str) 接口，强迫上层修改。
