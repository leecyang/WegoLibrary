from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import urllib.parse
import requests
import re
from sqlmodel import Session
from datetime import timedelta, datetime
from contextlib import asynccontextmanager

from app.database import (
    create_db_and_tables, engine, User, Config,
    get_config_by_owner, update_config_by_owner,
    log_checkin_by_owner, log_keepalive_by_owner,
    create_user, get_user_by_username, get_all_configs, delete_user,
    get_all_users
)
from app.scheduler import start_scheduler, shutdown_scheduler, keep_alive_for_user, start_auto_checkin_for_user, stop_auto_checkin_for_user
from app.core import WegolibCore
from app.auth import (
    get_session, get_current_user, get_current_admin,
    create_access_token, verify_password, get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    start_scheduler()
    yield
    shutdown_scheduler()

app = FastAPI(lifespan=lifespan)

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Models ============

class UserCreate(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ConfigRequest(BaseModel):
    session_id: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    venue_major: Optional[int] = None
    venue_minor: Optional[int] = None

class ParseSessionIdRequest(BaseModel):
    url: str

class AdminUserConfigResponse(BaseModel):
    user_id: int
    username: str
    is_configured: bool
    last_checkin: str
    status: str # "Active" or "Inactive"

# ============ Auth Routes ============

@app.post("/api/auth/register", response_model=UserResponse)
def register(user_in: UserCreate, session: Session = Depends(get_session)):
    user = get_user_by_username(session, user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="用户名已存在"
        )
    
    # 第一个注册的用户自动成为管理员（可选逻辑，方便测试）
    all_users = get_all_users(session)
    is_admin = len(all_users) == 0
    
    hashed_password = get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        password_hash=hashed_password,
        is_admin=is_admin
    )
    create_user(session, new_user)
    return {
        "id": new_user.id,
        "username": new_user.username,
        "is_admin": new_user.is_admin,
        "created_at": new_user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = get_user_by_username(session, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }

# ============ Business Routes ============

def _extract_wechat_sess_id_from_set_cookie(set_cookie: Optional[str]) -> Optional[str]:
    if not set_cookie:
        return None
    m = re.search(r"(?i)wechatSESS_ID=([^;,\s]+)", set_cookie)
    return m.group(1) if m else None

def _extract_wechat_sess_id_from_response(resp: requests.Response) -> Optional[str]:
    sid = resp.cookies.get("wechatSESS_ID")
    if sid:
        return sid
    return _extract_wechat_sess_id_from_set_cookie(resp.headers.get("set-cookie"))

@app.post("/api/parse-sessionid")
def parse_sessionid(req: ParseSessionIdRequest, current_user: User = Depends(get_current_user)):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")

    query = urllib.parse.urlparse(url).query
    query_params = urllib.parse.parse_qs(query)
    codes = query_params.get("code")
    if not codes:
        raise HTTPException(status_code=400, detail="链接中未找到 code 参数")

    code = codes[-1]
    
    state = "1"
    states = query_params.get("state")
    if states and states[-1]:
        state = states[-1]
    
    data = {"r": "https://web.traceint.com/web/index.html", "code": code, "state": state}

    session = requests.Session()

    try:
        r = session.get(
            "https://wechat.v2.traceint.com/index.php/wxApp/wechatAuth.html",
            params=data,
            allow_redirects=False,
            timeout=15,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="请求微信授权接口失败，请稍后重试")

    wechat_sess_id = _extract_wechat_sess_id_from_response(r)

    if not wechat_sess_id:
        try:
            r2 = session.get(
                "https://wechat.v2.traceint.com/index.php/wxApp/wechatAuth.html",
                params=data,
                allow_redirects=True,
                timeout=15,
            )
        except Exception:
            r2 = None

        if r2 is not None:
            for resp in list(getattr(r2, "history", [])) + [r2]:
                wechat_sess_id = _extract_wechat_sess_id_from_response(resp)
                if wechat_sess_id:
                    break

        if not wechat_sess_id:
            wechat_sess_id = session.cookies.get("wechatSESS_ID")

    if not wechat_sess_id:
        raise HTTPException(
            status_code=400,
            detail="未能从链接解析出 wechatSESS_ID：请确认已在微信内完成登录；且该链接的 code 可能为一次性，需重新扫码/重新复制最新链接",
        )

    return {"session_id": f"wechatSESS_ID={wechat_sess_id}"}

@app.get("/api/status")
def get_status(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    config = get_config_by_owner(session, current_user.id)

    if not config:
        return {
            "is_configured": False,
            "session_id_preview": "",
            "major": 0,
            "minor": 0,
            "venue_major": 0,
            "venue_minor": 0,
            "last_checkin": "从未",
            "last_checkin_result": "",
            "auto_checkin_enabled": False,
        }

    now = datetime.now()
    auto_checkin_enabled = bool(config.auto_checkin_expire_at and config.auto_checkin_expire_at > now)

    return {
        "is_configured": True,
        "session_id_preview": config.session_id[:20] + "..." if config.session_id else "",
        "major": config.major,
        "minor": config.minor,
        "venue_major": config.major,
        "venue_minor": config.minor,
        "last_checkin": config.last_checkin.strftime("%Y-%m-%d %H:%M:%S") if config.last_checkin else "从未",
        "last_checkin_result": config.last_checkin_result or "",
        "auto_checkin_enabled": auto_checkin_enabled,
    }

@app.post("/api/config")
def set_config(req: ConfigRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    current = get_config_by_owner(session, current_user.id)

    session_id = (req.session_id or "").strip()
    if not session_id:
        if current and current.session_id:
            session_id = current.session_id
        else:
            raise HTTPException(status_code=400, detail="session_id 不能为空")

    target_major = req.venue_major if req.venue_major is not None else req.major
    target_minor = req.venue_minor if req.venue_minor is not None else req.minor
    if target_major is None:
        target_major = current.major if current else 20
    if target_minor is None:
        target_minor = current.minor if current else 9

    update_config_by_owner(session, current_user.id, session_id, int(target_major), int(target_minor))
    # 为该用户触发一次保活验证
    keep_alive_for_user(current_user.id)
    return {"message": "配置已保存"}

@app.post("/api/checkin")
def trigger_checkin(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    config = get_config_by_owner(session, current_user.id)

    if not config or not config.session_id:
        raise HTTPException(status_code=400, detail="未配置，请先连接微信")

    core = WegolibCore(config.session_id)
    result = core.sign_in(config.major, config.minor)

    log_checkin_by_owner(session, current_user.id, result["success"], result["message"])

    now = datetime.now()
    expire_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    config.auto_checkin_expire_at = expire_at
    session.add(config)
    session.commit()
    start_auto_checkin_for_user(current_user.id, expire_at)

    return result

@app.post("/api/keepalive")
def trigger_keepalive(current_user: User = Depends(get_current_user)):
    keep_alive_for_user(current_user.id)
    return {"message": "已触发保活"}

@app.post("/api/auto-checkin/enable")
def enable_auto_checkin(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    config = get_config_by_owner(session, current_user.id)
    if not config or not config.session_id:
        raise HTTPException(status_code=400, detail="未配置，请先连接微信")
    now = datetime.now()
    expire_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    config.auto_checkin_expire_at = expire_at
    session.add(config)
    session.commit()
    start_auto_checkin_for_user(current_user.id, expire_at)
    return {"message": "开启成功"}

@app.post("/api/auto-checkin/disable")
def disable_auto_checkin(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    config = get_config_by_owner(session, current_user.id)
    if not config:
        raise HTTPException(status_code=400, detail="未配置，请先连接微信")
    config.auto_checkin_expire_at = None
    session.add(config)
    session.commit()
    stop_auto_checkin_for_user(current_user.id)
    return {"message": "关闭成功"}

# ============ Admin Routes ============

@app.get("/api/admin/users", response_model=List[AdminUserConfigResponse])
def get_admin_users(admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    """管理员：获取所有用户状态"""
    users = get_all_users(session)
    result = []
    for user in users:
        config = get_config_by_owner(session, user.id)
        
        info = {
            "user_id": user.id,
            "username": user.username,
            "is_configured": False,
            "last_checkin": "从未",
            "status": "未配置"
        }
        
        if config:
            info["is_configured"] = True
            info["status"] = "活跃" if config.is_active else "未激活"
            if config.last_checkin:
                info["last_checkin"] = config.last_checkin.strftime("%Y-%m-%d %H:%M:%S")
        
        result.append(info)
    return result

@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: int, admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    """管理员：删除用户"""
    delete_user(session, user_id)
    return {"message": "用户已删除"}

@app.post("/api/admin/users/{user_id}/checkin")
def admin_trigger_checkin(user_id: int, admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    """管理员：强制为指定用户签到"""
    config = get_config_by_owner(session, user_id)
    if not config or not config.session_id:
        raise HTTPException(status_code=400, detail="该用户未配置")
    
    core = WegolibCore(config.session_id)
    result = core.sign_in(config.major, config.minor)
    log_checkin_by_owner(session, user_id, result["success"], result["message"])
    return result
