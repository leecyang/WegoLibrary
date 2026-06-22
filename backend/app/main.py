from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List, Any
from sqlmodel import Session
from datetime import timedelta, datetime
from contextlib import asynccontextmanager
import json
import urllib.parse
import requests

from app.database import (
    create_db_and_tables, User, Config, Announcement,
    get_config_by_owner, update_config_by_owner,
    log_checkin_by_owner, log_keepalive_by_owner,
    create_user, get_user_by_username, get_all_configs, delete_user,
    get_all_users, get_announcement, get_or_create_announcement,
    get_profile_display, build_wechat_profile_response, get_wechat_connection_status,
    deactivate_session_by_owner,
)
from app.traceint_client import (
    parse_url_to_session_and_profile,
    parse_url_to_authorization_and_profile,
    parse_url_to_checkin_session,
    parse_code_from_url,
)
from app.scheduler import start_scheduler, shutdown_scheduler, keep_alive_for_user, start_auto_checkin_for_user, stop_auto_checkin_for_user
from app.core import WegolibCore
from app.auth import (
    get_session, get_current_user, get_current_admin,
    create_access_token, verify_password, get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES, clear_auth_session_cookie,
    create_persistent_auth_session, revoke_auth_session_token,
    set_auth_session_cookie, AUTH_SESSION_COOKIE_NAME,
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

class WechatProfilePayload(BaseModel):
    traceint_user_id: Optional[int] = None
    nick: Optional[str] = None
    avatar: Optional[str] = None
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    sch: Optional[str] = None
    area_name: Optional[str] = None
    fetched_at: Optional[str] = None

class ConfigRequest(BaseModel):
    session_id: Optional[str] = None
    major: Optional[int] = None
    minor: Optional[int] = None
    venue_major: Optional[int] = None
    venue_minor: Optional[int] = None
    profile: Optional[WechatProfilePayload] = None

class ParseSessionIdRequest(BaseModel):
    url: str

class AdminUserConfigResponse(BaseModel):
    user_id: int
    username: str
    is_configured: bool
    last_checkin: str
    status: str # "Active" or "Inactive"
    profile_display: str = "none"
    wechat_nick: Optional[str] = None
    wechat_student_name: Optional[str] = None
    wechat_student_no: Optional[str] = None
    wechat_sch: Optional[str] = None
    wechat_avatar: Optional[str] = None

class AnnouncementResponse(BaseModel):
    has_announcement: bool
    content: str
    published_at: Optional[str] = None

class AdminAnnouncementResponse(BaseModel):
    draft_content: str
    published_content: str
    is_published: bool
    updated_at: Optional[str] = None
    published_at: Optional[str] = None

class LocationPresetResponse(BaseModel):
    school: str
    area_name: str
    label: str
    venue_major: int
    venue_minor: int

class UpdateAnnouncementDraftRequest(BaseModel):
    content: str = ""

ANNOUNCEMENT_MAX_LENGTH = 2000
WECHAT_CONNECT_HELP_TEXT = (
    "微信连接失败。请先确认：1. 今天已经打开过“我去图书馆”小程序页面；"
    "2. 回到微信重新授权后，再复制新的回调链接粘贴。"
)
WECHAT_TWO_STEP_HELP_TEXT = (
    "连续授权失败，已切换为两步连接。请重新授权并粘贴第一条新链接，"
    "完成后按页面提示再次授权。请不要使用微信内置网页打开链接，改用其他浏览器。"
)
WECHAT_SECOND_STEP_HELP_TEXT = (
    "第一步已经完成。请回到微信重新授权，再粘贴新生成的第二条链接完成连接。"
    "请不要使用微信内置网页打开链接，改用其他浏览器。"
)
WECHAT_SESSION_ONLY_HELP_TEXT = (
    "微信连接失败。你的用户资料已经同步，无需重复获取。"
    "请重新授权后粘贴一条新链接，系统将直接更新签到凭据。"
    "请不要使用微信内置网页打开链接，改用其他浏览器。"
)
WECHAT_PENDING_EXPIRE_MINUTES = 15
WECHAT_AVATAR_ALLOWED_HOSTS = {
    "static.wechat.v2.traceint.com",
    "wechat.v2.traceint.com",
}
DEFAULT_LOCATION_PRESET_MAJOR = 20
DEFAULT_LOCATION_PRESET_MINOR = 9
DEFAULT_LOCATION_PRESET_SCHOOL = "南京农业大学（卫岗校区/滨江校区）"
DEFAULT_LOCATION_PRESET_AREA = "滨江校区"
CHECKIN_RATE_LIMIT_WINDOW_SECONDS = 60
CHECKIN_RATE_LIMIT_MAX_ATTEMPTS = 2
_manual_checkin_attempts: dict[int, list[datetime]] = {}


def _enforce_manual_checkin_rate_limit(user_id: int) -> None:
    now = datetime.now()
    window_start = now - timedelta(seconds=CHECKIN_RATE_LIMIT_WINDOW_SECONDS)
    recent_attempts = [
        attempt_at
        for attempt_at in _manual_checkin_attempts.get(user_id, [])
        if attempt_at > window_start
    ]
    if len(recent_attempts) >= CHECKIN_RATE_LIMIT_MAX_ATTEMPTS:
        retry_after = max(
            1,
            int(
                CHECKIN_RATE_LIMIT_WINDOW_SECONDS
                - (now - min(recent_attempts)).total_seconds()
            ),
        )
        _manual_checkin_attempts[user_id] = recent_attempts
        raise HTTPException(
            status_code=429,
            detail=f"签到操作太频繁，请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )

    recent_attempts.append(now)
    _manual_checkin_attempts[user_id] = recent_attempts

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
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
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
    auth_session_token = create_persistent_auth_session(session, user.id)
    set_auth_session_cookie(response, auth_session_token, request)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    revoke_auth_session_token(session, request.cookies.get(AUTH_SESSION_COOKIE_NAME))
    clear_auth_session_cookie(response)
    return {"message": f"用户 {current_user.username} 已退出登录"}

# ============ Business Routes ============

def _profile_payload_to_dict(profile: Optional[WechatProfilePayload]) -> Optional[dict[str, Any]]:
    if profile is None:
        return None
    data = profile.model_dump(exclude_none=True)
    if not data.get("nick"):
        return None
    return data

def _snapshot_to_response_dict(snapshot) -> dict[str, Any]:
    if snapshot is None:
        return {}
    data = snapshot.to_dict()
    return data

def _proxied_wechat_avatar_url(avatar: Optional[str]) -> Optional[str]:
    if not avatar:
        return avatar
    parsed = urllib.parse.urlparse(avatar)
    if parsed.scheme not in {"http", "https"}:
        return avatar
    if parsed.hostname not in WECHAT_AVATAR_ALLOWED_HOSTS:
        return avatar
    return f"/api/wechat-avatar?url={urllib.parse.quote(avatar, safe='')}"

def _proxy_wechat_profile_avatar(profile: Optional[dict]) -> Optional[dict]:
    if not profile:
        return profile
    data = dict(profile)
    data["avatar"] = _proxied_wechat_avatar_url(data.get("avatar"))
    return data

def _format_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None

def _normalize_announcement_content(content: Optional[str]) -> str:
    normalized = (content or "").strip()
    if len(normalized) > ANNOUNCEMENT_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"公告正文不能超过 {ANNOUNCEMENT_MAX_LENGTH} 个字符",
        )
    return normalized

def _build_public_announcement_response(announcement: Optional[Announcement]) -> AnnouncementResponse:
    if not announcement or not announcement.is_published or not announcement.published_content:
        return AnnouncementResponse(has_announcement=False, content="", published_at=None)

    return AnnouncementResponse(
        has_announcement=True,
        content=announcement.published_content,
        published_at=_format_datetime(announcement.published_at),
    )

def _build_admin_announcement_response(announcement: Optional[Announcement]) -> AdminAnnouncementResponse:
    if not announcement:
        return AdminAnnouncementResponse(
            draft_content="",
            published_content="",
            is_published=False,
            updated_at=None,
            published_at=None,
        )

    return AdminAnnouncementResponse(
        draft_content=announcement.draft_content or "",
        published_content=announcement.published_content or "",
        is_published=announcement.is_published,
        updated_at=_format_datetime(announcement.updated_at),
        published_at=_format_datetime(announcement.published_at),
    )

def _clear_pending_traceint_authorization(user: User) -> None:
    user.pending_traceint_code = None
    user.pending_traceint_profile = None
    user.pending_traceint_at = None


@app.post("/api/parse-sessionid")
def parse_sessionid(
    req: ParseSessionIdRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")

    try:
        parse_code_from_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=WECHAT_CONNECT_HELP_TEXT) from exc

    failures = current_user.wechat_authorization_failures or 0
    config = get_config_by_owner(session, current_user.id)
    has_synced_wechat_profile = bool(
        config and config.wechat_profile_at and config.wechat_nick
    )
    pending_expired = (
        current_user.pending_traceint_at is not None
        and current_user.pending_traceint_at
        < datetime.now() - timedelta(minutes=WECHAT_PENDING_EXPIRE_MINUTES)
    )
    if pending_expired:
        _clear_pending_traceint_authorization(current_user)

    try:
        if current_user.pending_traceint_code:
            code, _ = parse_code_from_url(url)
            if code == current_user.pending_traceint_code:
                raise ValueError("第二步需要重新授权生成一条新链接")
            session_id, warning = parse_url_to_checkin_session(url)
            profile_response = json.loads(current_user.pending_traceint_profile or "null")
            _clear_pending_traceint_authorization(current_user)
            current_user.wechat_authorization_failures = 0
            session.add(current_user)
            session.commit()
            return {
                "session_id": session_id,
                "profile": profile_response,
                "warning": warning,
                "requires_second_link": False,
            }

        if has_synced_wechat_profile:
            session_id, warning = parse_url_to_checkin_session(url)
            current_user.wechat_authorization_failures = 0
            session.add(current_user)
            session.commit()
            return {
                "session_id": session_id,
                "profile": None,
                "warning": warning,
                "requires_second_link": False,
            }

        if failures >= 1:
            code, _ = parse_code_from_url(url)
            _authorization, _serverid, profile_snapshot, warning = (
                parse_url_to_authorization_and_profile(url)
            )
            profile_response = (
                _snapshot_to_response_dict(profile_snapshot) if profile_snapshot else None
            )
            current_user.pending_traceint_code = code
            current_user.pending_traceint_profile = json.dumps(profile_response)
            current_user.pending_traceint_at = datetime.now()
            session.add(current_user)
            session.commit()
            return {
                "session_id": None,
                "profile": profile_response,
                "warning": warning,
                "requires_second_link": True,
            }

        session_id, profile_snapshot, warning = parse_url_to_session_and_profile(url)
    except ValueError as exc:
        current_user.wechat_authorization_failures = (
            current_user.wechat_authorization_failures or 0
        ) + 1
        session.add(current_user)
        session.commit()
        if current_user.pending_traceint_code:
            detail = WECHAT_SECOND_STEP_HELP_TEXT
        elif has_synced_wechat_profile:
            detail = WECHAT_SESSION_ONLY_HELP_TEXT
        elif current_user.wechat_authorization_failures >= 1:
            detail = WECHAT_TWO_STEP_HELP_TEXT
        else:
            detail = WECHAT_CONNECT_HELP_TEXT
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("parse-sessionid 未处理异常")
        raise HTTPException(status_code=400, detail=WECHAT_CONNECT_HELP_TEXT) from exc

    current_user.wechat_authorization_failures = 0
    session.add(current_user)
    session.commit()

    profile_response = _snapshot_to_response_dict(profile_snapshot) if profile_snapshot else None
    return {
        "session_id": session_id,
        "profile": profile_response,
        "warning": warning,
        "requires_second_link": False,
    }

@app.get("/api/wechat-avatar")
def proxy_wechat_avatar(url: str, current_user: User = Depends(get_current_user)):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in WECHAT_AVATAR_ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="头像地址不允许代理")

    try:
        upstream = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                    "MicroMessenger/8.0.67(0x18004239) NetType/WIFI Language/zh_CN"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            timeout=15,
        )
        upstream.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="头像获取失败") from exc

    content_type = upstream.headers.get("content-type") or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="头像响应不是图片")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )

@app.get("/api/announcement", response_model=AnnouncementResponse)
def get_public_announcement(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    announcement = get_announcement(session)
    return _build_public_announcement_response(announcement)

@app.get("/api/location-presets", response_model=List[LocationPresetResponse])
def get_location_presets(
    _current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    grouped: dict[tuple[str, str], dict[tuple[int, int], int]] = {}
    for config in get_all_configs(session):
        school = (config.wechat_sch or "").strip()
        area_name = (config.wechat_area_name or "").strip()
        if not school or not area_name:
            continue

        try:
            venue_major = int(config.major)
            venue_minor = int(config.minor)
        except (TypeError, ValueError):
            continue

        if not (1 <= venue_major <= 65535 and 1 <= venue_minor <= 65535):
            continue
        if (
            venue_major == DEFAULT_LOCATION_PRESET_MAJOR
            and venue_minor == DEFAULT_LOCATION_PRESET_MINOR
            and (
                school != DEFAULT_LOCATION_PRESET_SCHOOL
                or area_name != DEFAULT_LOCATION_PRESET_AREA
            )
        ):
            continue

        location_key = (school, area_name)
        beacon_key = (venue_major, venue_minor)
        beacon_counts = grouped.setdefault(location_key, {})
        beacon_counts[beacon_key] = beacon_counts.get(beacon_key, 0) + 1

    presets: list[LocationPresetResponse] = []
    for (school, area_name), beacon_counts in grouped.items():
        (venue_major, venue_minor), _count = sorted(
            beacon_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[0]
        presets.append(
            LocationPresetResponse(
                school=school,
                area_name=area_name,
                label=f"{school} · {area_name}",
                venue_major=venue_major,
                venue_minor=venue_minor,
            )
        )

    return sorted(presets, key=lambda preset: preset.label)

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
            "profile_display": "none",
            "wechat_profile": None,
            "wechat_connection_status": "disconnected",
        }

    now = datetime.now()
    auto_checkin_enabled = bool(config.auto_checkin_expire_at and config.auto_checkin_expire_at > now)
    profile_display = get_profile_display(config)

    return {
        "is_configured": bool(config.session_id),
        "session_id_preview": config.session_id[:20] + "..." if config.session_id else "",
        "major": config.major,
        "minor": config.minor,
        "venue_major": config.major,
        "venue_minor": config.minor,
        "last_checkin": config.last_checkin.strftime("%Y-%m-%d %H:%M:%S") if config.last_checkin else "从未",
        "last_checkin_result": config.last_checkin_result or "",
        "auto_checkin_enabled": auto_checkin_enabled,
        "profile_display": profile_display,
        "wechat_profile": _proxy_wechat_profile_avatar(build_wechat_profile_response(config)),
        "wechat_connection_status": get_wechat_connection_status(config),
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

    profile_dict = _profile_payload_to_dict(req.profile)
    try:
        update_config_by_owner(
            session,
            current_user.id,
            session_id,
            int(target_major),
            int(target_minor),
            profile=profile_dict,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("保存配置失败")
        raise HTTPException(status_code=400, detail="保存配置失败，请重试") from exc

    try:
        keep_alive_for_user(current_user.id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("保存后保活失败: %s", exc)

    return {"message": "配置已保存"}

@app.post("/api/checkin")
def trigger_checkin(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    config = get_config_by_owner(session, current_user.id)

    if not config or not config.session_id:
        raise HTTPException(status_code=400, detail="未配置，请先连接微信")

    _enforce_manual_checkin_rate_limit(current_user.id)

    core = WegolibCore(config.session_id)
    result = core.sign_in(config.major, config.minor)

    log_checkin_by_owner(session, current_user.id, result["success"], result["message"])

    if result["success"]:
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

@app.get("/api/admin/announcement", response_model=AdminAnnouncementResponse)
def get_admin_announcement(admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    announcement = get_announcement(session)
    return _build_admin_announcement_response(announcement)

@app.put("/api/admin/announcement/draft", response_model=AdminAnnouncementResponse)
def update_admin_announcement_draft(
    req: UpdateAnnouncementDraftRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    announcement = get_or_create_announcement(session)
    announcement.draft_content = _normalize_announcement_content(req.content)
    announcement.updated_at = datetime.now()
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return _build_admin_announcement_response(announcement)

@app.post("/api/admin/announcement/publish", response_model=AdminAnnouncementResponse)
def publish_admin_announcement(admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    announcement = get_or_create_announcement(session)
    draft_content = _normalize_announcement_content(announcement.draft_content)
    if not draft_content:
        raise HTTPException(status_code=400, detail="草稿为空，无法发布")

    now = datetime.now()
    announcement.draft_content = draft_content
    announcement.published_content = draft_content
    announcement.is_published = True
    announcement.updated_at = now
    announcement.published_at = now
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return _build_admin_announcement_response(announcement)

@app.post("/api/admin/announcement/unpublish", response_model=AdminAnnouncementResponse)
def unpublish_admin_announcement(admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    announcement = get_or_create_announcement(session)
    announcement.is_published = False
    announcement.published_content = ""
    announcement.published_at = None
    announcement.updated_at = datetime.now()
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return _build_admin_announcement_response(announcement)

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
            info["is_configured"] = bool(config.session_id)
            info["status"] = "活跃" if config.is_active and config.session_id else "已登出"
            if config.last_checkin:
                info["last_checkin"] = config.last_checkin.strftime("%Y-%m-%d %H:%M:%S")
            info["profile_display"] = get_profile_display(config)
            info["wechat_nick"] = config.wechat_nick
            info["wechat_student_name"] = config.wechat_student_name
            info["wechat_student_no"] = config.wechat_student_no
            info["wechat_sch"] = config.wechat_sch
            info["wechat_avatar"] = _proxied_wechat_avatar_url(config.wechat_avatar)
        
        result.append(info)
    return result

@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: int, admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    """管理员：删除用户"""
    delete_user(session, user_id)
    return {"message": "用户已删除"}

@app.post("/api/admin/users/{user_id}/logout")
def admin_logout_user(user_id: int, admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    """管理员：停止指定用户当前微信会话续期，等待用户重新授权。"""
    if not deactivate_session_by_owner(session, user_id):
        raise HTTPException(status_code=400, detail="该用户尚未配置微信会话")
    stop_auto_checkin_for_user(user_id)
    return {"message": "用户已登出，重新授权前不会继续续期"}
