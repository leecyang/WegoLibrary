"""Traceint 微信授权与个人资料接口封装。"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, Tuple, TypeVar

import requests
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout

logger = logging.getLogger(__name__)

# auth.html 实测需走 HTTP；wechatAuth / GraphQL / wxApp 走 HTTPS
AUTH_HTML_URL = "http://wechat.v2.traceint.com/index.php/urlNew/auth.html"
WECHAT_AUTH_URL = "https://wechat.v2.traceint.com/index.php/wxApp/wechatAuth.html"
GRAPHQL_URL = "https://wechat.v2.traceint.com/index.php/graphql/"
DEVICES_URL = "https://wechat.v2.traceint.com/index.php/wxApp/devices.html"
GET_TIME_URL = "https://wechat.v2.traceint.com/index.php/wxApp/getTime.html"
REDIRECT_R = "https://web.traceint.com/web/index.html"
MINIPROGRAM_REFERER = "https://servicewechat.com/wx3b9352e6b254ed2b/25/page-frame.html"

TRACEINT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.67(0x18004239) "
    "NetType/WIFI Language/zh_CN"
)

INDEX_QUERY = (
    "query index($pos: String!, $param: [hash]) { userAuth { oftenseat { list { id info "
    "lib_id seat_key status } } message { new(from: \"system\") { has from_user title num } "
    "indexMsg { message_id title content isread isused from_user create_time } } reserve { "
    "reserve { token status user_id user_nick sch_name lib_id lib_name lib_floor seat_key "
    "seat_name date exp_date exp_date_str validate_date hold_date diff diff_str mark_source "
    "isRecordUser isChooseSeat isRecord mistakeNum openTime threshold daynum closeTime "
    "timerange forbidQrValid renewTimeNext forbidRenewTime forbidWechatCancle } getSToken } "
    "currentUser { user_id user_nick user_mobile user_sex user_sch_id user_sch user_last_login "
    "user_avatar(size: MIDDLE) user_adate user_student_no user_student_name area_name user_deny "
    "{ deny_deadline } sch { sch_id sch_name activityUrl isShowCommon isBusy } subscribe_remind } "
    "record { recordRegInfo { reg_start reg_end } recordShortlistInfo } } ad(pos: $pos, param: "
    "$param) { name pic url } homeIconAd: ad(pos: \"home-icon\", param: $param) { name pic url } }"
)

INDEX_QUERY_MINIMAL = "query index { userAuth { currentUser { user_id user_nick } } }"

# 换票后校验的重试次数（Traceint 在频繁请求时可能 RST/TLS EOF）
_VALIDATE_RETRIES = 4
_VALIDATE_RETRY_DELAY_SEC = 2.0
_DUAL_AUTH_DELAY_SEC = max(
    0.0,
    int(os.getenv("TRACEINT_DUAL_AUTH_DELAY_MS", "1")) / 1000,
)

T = TypeVar("T")

_RETRYABLE_REQUEST_ERRORS = (
    SSLError,
    ConnectionError,
    Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
)

_WECHAT_AUTH_ERROR_MARKERS = (
    "授权错误",
    "微信授权失败",
    "code been used",
    "IS_LOGIN = false",
)

_WECHAT_SESSION_EXPIRED_MARKERS = (
    "登录状态已经失效",
    "无法重新登录",
)


def _safe_response_json(resp: requests.Response) -> dict[str, Any]:
    """解析 Traceint 响应 JSON，失败时返回空 dict 而非抛未处理异常。"""
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"_data": data}
    except (json.JSONDecodeError, ValueError):
        text = (resp.text or "").strip()
        logger.warning(
            "Traceint 响应非 JSON status=%s body=%s",
            resp.status_code,
            text[:200],
        )
        return {"_raw": text, "_status": resp.status_code}


def _graphql_headers(cookie: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Host": "wechat.v2.traceint.com",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "App-Version": "2.2.5",
        "Origin": "https://web.traceint.com",
        "Referer": MINIPROGRAM_REFERER,
        "User-Agent": TRACEINT_UA,
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _wxapp_headers(cookie: str) -> dict[str, str]:
    return {
        "Host": "wechat.v2.traceint.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "App-Version": "2.2.5",
        "Origin": "https://web.traceint.com",
        "Referer": MINIPROGRAM_REFERER,
        "User-Agent": TRACEINT_UA,
        "Cookie": cookie,
    }


@dataclass
class WechatProfileSnapshot:
    traceint_user_id: Optional[int]
    nick: Optional[str]
    avatar: Optional[str]
    student_name: Optional[str]
    student_no: Optional[str]
    sch: Optional[str]
    area_name: Optional[str]
    fetched_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceint_user_id": self.traceint_user_id,
            "nick": self.nick,
            "avatar": self.avatar,
            "student_name": self.student_name,
            "student_no": self.student_no,
            "sch": self.sch,
            "area_name": self.area_name,
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass
class DualExchangeTicket:
    authorization: str
    auth_serverid: Optional[str]
    auth_session: requests.Session
    wechat_sess_id: str
    wechat_serverid: Optional[str]


def parse_code_from_url(url: str) -> Tuple[str, str]:
    """
    从授权回调 URL 仅解析 code/state，不对 GraphQL 回调 URL 发 GET。
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("url 不能为空")

    query = urllib.parse.urlparse(url).query
    query_params = urllib.parse.parse_qs(query)
    codes = query_params.get("code")
    if not codes:
        raise ValueError("链接中未找到 code 参数，请粘贴微信授权后的完整链接")

    code = codes[-1]
    state = "1"
    states = query_params.get("state")
    if states and states[-1]:
        state = states[-1]
    return code, state


def _is_transient_request_error(exc: BaseException) -> bool:
    if isinstance(exc, _RETRYABLE_REQUEST_ERRORS):
        return True
    if isinstance(exc, RequestException):
        return True
    msg = str(exc).lower()
    return (
        "ssl" in msg
        or "connection" in msg
        or "eof" in msg
        or "timed out" in msg
        or "connectionpool" in msg
    )


def _call_with_retry(
    fn: Callable[[], T],
    *,
    action: str,
    retries: int = _VALIDATE_RETRIES,
    delay_sec: float = _VALIDATE_RETRY_DELAY_SEC,
) -> T:
    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            return fn()
        except _RETRYABLE_REQUEST_ERRORS as exc:
            last_exc = exc
            logger.warning(
                "%s  transient error (attempt %s/%s): %s",
                action,
                attempt + 1,
                retries,
                exc,
            )
            if attempt + 1 < retries:
                time.sleep(delay_sec * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _decode_response_text(resp: requests.Response) -> str:
    try:
        return resp.content.decode("utf-8", errors="replace")
    except Exception:
        return resp.text or ""


def _wechat_auth_response_has_error(resp: requests.Response) -> bool:
    text = _decode_response_text(resp)
    return any(marker in text for marker in _WECHAT_AUTH_ERROR_MARKERS)


def _is_wechat_session_expired_message(msg: str) -> bool:
    return any(marker in msg for marker in _WECHAT_SESSION_EXPIRED_MARKERS)


def _traceint_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": TRACEINT_UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Referer": MINIPROGRAM_REFERER,
            "Connection": "keep-alive",
        }
    )
    return session


def _prewarm_session(session: requests.Session, url: str) -> None:
    try:
        session.get(url, timeout=5)
    except Exception as exc:
        logger.debug("Traceint prewarm failed for %s: %s", url, exc)


def _extract_cookie_from_set_cookie(set_cookie: Optional[str], name: str) -> Optional[str]:
    if not set_cookie:
        return None
    pattern = rf"(?i){re.escape(name)}=([^;,\s]+)"
    m = re.search(pattern, set_cookie)
    return m.group(1) if m else None


def _collect_cookie_value(
    session: requests.Session,
    resp: requests.Response,
    name: str,
) -> Optional[str]:
    value = session.cookies.get(name) or resp.cookies.get(name)
    if value:
        return value
    value = _extract_cookie_from_set_cookie(resp.headers.get("set-cookie"), name)
    if value:
        return value
    for hist in getattr(resp, "history", []):
        value = hist.cookies.get(name) or _extract_cookie_from_set_cookie(
            hist.headers.get("set-cookie"), name
        )
        if value:
            return value
    return None


def _build_oauth_params(code: str, state: str) -> dict[str, Any]:
    try:
        state_val: Any = int(state)
    except (TypeError, ValueError):
        state_val = state
    return {"r": REDIRECT_R, "code": code, "state": state_val}


def exchange_authorization(
    code: str,
    state: str = "1",
    http_session: Optional[requests.Session] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    ① GET urlNew/auth.html → Authorization (JWT)
    须使用 HTTP 端点。若要同一 code 同时拿 JWT 与签到 Session，需与
    wechatAuth 并发请求，避免 OAuth code 被单边消耗。
    """
    session = http_session or _traceint_session()
    params = _build_oauth_params(code, state)
    authorization: Optional[str] = None
    serverid: Optional[str] = None

    for allow_redirects in (False, True):
        try:
            resp = session.get(
                AUTH_HTML_URL,
                params=params,
                allow_redirects=allow_redirects,
                timeout=15,
            )
        except Exception as exc:
            logger.warning("auth.html 请求失败 (redirects=%s): %s", allow_redirects, exc)
            continue

        authorization = _collect_cookie_value(session, resp, "Authorization")
        serverid = _collect_cookie_value(session, resp, "SERVERID")
        if authorization:
            logger.info(
                "auth.html 换票成功 status=%s redirects=%s",
                resp.status_code,
                allow_redirects,
            )
            return authorization, serverid

    logger.warning(
        "auth.html 未返回 Authorization（请确认 code 未在浏览器中提前打开、且未先调用 wechatAuth）"
    )
    return None, serverid


def exchange_wechat_sess_id(
    code: str,
    state: str = "1",
    http_session: Optional[requests.Session] = None,
) -> str:
    """
    ② GET wxApp/wechatAuth.html → wechatSESS_ID
    使用独立 Session，避免 auth 换票写入的 Authorization 干扰签到 Session 签发。
    注意：wechatAuth 在授权失败页也会 Set-Cookie；必须检查页面是否为授权错误。
    """
    session = http_session or _traceint_session()
    params = _build_oauth_params(code, state)
    wechat_sess_id: Optional[str] = None
    last_error_page = False

    for allow_redirects in (False, True):
        try:
            resp = session.get(
                WECHAT_AUTH_URL,
                params=params,
                allow_redirects=allow_redirects,
                timeout=15,
            )
        except Exception as exc:
            raise ValueError("请求微信签到授权接口失败，请稍后重试") from exc

        wechat_sess_id = _collect_cookie_value(session, resp, "wechatSESS_ID")
        last_error_page = _wechat_auth_response_has_error(resp)
        if wechat_sess_id and not last_error_page:
            break

    if wechat_sess_id and last_error_page:
        raise ValueError(
            "微信签到授权失败：Traceint 返回授权错误页（通常是 code 已被使用）。"
            "请重新扫码获取最新回调链接；系统会并发换取 JWT 和签到 Session"
        )

    if not wechat_sess_id:
        raise ValueError(
            "未能换取签到会话（wechatSESS_ID）：请确认先完成预约授权且 code 为最新；"
            "勿在浏览器中先打开该链接"
        )

    return wechat_sess_id


def exchange_dual_authorization_and_session(
    code: str,
    state: str = "1",
) -> DualExchangeTicket:
    """
    用同一 OAuth code 并发换取 JWT 与 wxApp 签到 Session。

    Traceint/微信 code 是一次性凭据；顺序调用时先成功的一侧会让另一侧返回
    code been used。并发请求是单链接双换票唯一可行的形式。
    """
    auth_session = _traceint_session()
    wechat_session = _traceint_session()
    _prewarm_session(auth_session, GRAPHQL_URL)
    _prewarm_session(wechat_session, GET_TIME_URL)
    start_barrier = threading.Barrier(2)

    def _exchange_authorization_raced() -> Tuple[Optional[str], Optional[str]]:
        start_barrier.wait()
        if _DUAL_AUTH_DELAY_SEC:
            time.sleep(_DUAL_AUTH_DELAY_SEC)
        return exchange_authorization(code, state, auth_session)

    def _exchange_wechat_sess_id_raced() -> str:
        start_barrier.wait()
        return exchange_wechat_sess_id(code, state, wechat_session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        sess_future = executor.submit(
            _exchange_wechat_sess_id_raced,
        )
        auth_future = executor.submit(
            _exchange_authorization_raced,
        )
        auth_error: Optional[BaseException] = None
        sess_error: Optional[BaseException] = None

        try:
            authorization, auth_serverid = auth_future.result()
        except BaseException as exc:
            authorization, auth_serverid = None, None
            auth_error = exc

        try:
            wechat_sess_id = sess_future.result()
        except BaseException as exc:
            wechat_sess_id = None
            sess_error = exc

    wechat_serverid = wechat_session.cookies.get("SERVERID")

    if not authorization or not wechat_sess_id:
        details: list[str] = []
        if not authorization:
            details.append("JWT 未换到")
            if auth_error:
                details.append(str(auth_error))
        if not wechat_sess_id:
            details.append("签到 Session 未换到")
            if sess_error:
                details.append(str(sess_error))
        raise ValueError(
            "同一回调链接未能完成可用双换票（"
            + "；".join(details)
            + "）。请重新扫码生成最新链接后立即粘贴，且不要先在浏览器打开该链接"
        )

    return DualExchangeTicket(
        authorization=authorization,
        auth_serverid=auth_serverid,
        auth_session=auth_session,
        wechat_sess_id=wechat_sess_id,
        wechat_serverid=wechat_serverid,
    )


def build_session_cookie_string(
    authorization: str,
    wechat_sess_id: str,
    serverid: Optional[str] = None,
) -> str:
    """合并 JWT + Session（仅用于换票后 GraphQL 校验等，不可用于 wxApp 签到）。"""
    parts = [f"Authorization={authorization}", f"wechatSESS_ID={wechat_sess_id}"]
    if serverid:
        parts.append(f"SERVERID={serverid}")
    return "; ".join(parts)


def build_checkin_session_id(
    wechat_sess_id: str,
    serverid: Optional[str] = None,
) -> str:
    """
    签到/保活入库用的 session_id。
    wxApp（sign.html / devices.html）只认 wechatSESS_ID，携带 Authorization 会导致登录失效。
    """
    parts = [f"wechatSESS_ID={wechat_sess_id}"]
    if serverid:
        parts.append(f"SERVERID={serverid}")
    return "; ".join(parts)


def normalize_checkin_session_id(session_id: str) -> str:
    """从旧版合并 Cookie 中提取签到所需字段，去掉 Authorization。"""
    values: dict[str, str] = {}
    for part in (session_id or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key == "Authorization":
            continue
        values[key] = value
    if "wechatSESS_ID" not in values:
        return session_id
    ordered = ["wechatSESS_ID", "SERVERID"]
    return "; ".join(f"{k}={values[k]}" for k in ordered if k in values)


def validate_authorization(
    authorization: str,
    serverid: Optional[str] = None,
    http_session: Optional[requests.Session] = None,
) -> Optional[str]:
    """
    GraphQL index 校验 JWT。
    网络异常且重试仍失败时返回警告文案（不阻断保存）；业务错误仍抛 ValueError。
    """
    body = {
        "operationName": "index",
        "variables": {},
        "query": INDEX_QUERY_MINIMAL,
    }
    session = http_session or _traceint_session()
    # 复用换票 Session 时不再重复设置 Cookie 头，避免与 session.cookies 冲突
    if http_session is None:
        cookie_parts = [f"Authorization={authorization}"]
        if serverid:
            cookie_parts.append(f"SERVERID={serverid}")
        headers = _graphql_headers("; ".join(cookie_parts))
    else:
        headers = _graphql_headers()

    def _do_validate() -> dict[str, Any]:
        resp = session.post(GRAPHQL_URL, json=body, headers=headers, timeout=20)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return _safe_response_json(resp)

    try:
        payload = _call_with_retry(_do_validate, action="JWT validate")
    except Exception as exc:
        if _is_transient_request_error(exc):
            logger.warning("JWT 校验因网络异常跳过: %s", exc)
            return (
                "预约凭证暂未校验（Traceint 连接异常，可能因请求过于频繁）。"
                "凭据已保存，请等待数分钟后再试签到"
            )
        logger.exception("JWT 校验未预期错误")
        return (
            "预约凭证暂未校验（服务响应异常）。凭据已保存，请稍后试签到；"
            "若仍失败请重新扫码授权"
        )

    if payload.get("errors"):
        err = payload["errors"][0] if payload["errors"] else {}
        msg = err.get("msg") or str(err)
        raise ValueError(
            f"JWT 无效或已过期（{msg}）。请重新扫码粘贴最新链接，且勿在浏览器中先打开该链接"
        )

    user_auth = (payload.get("data") or {}).get("userAuth")
    current_user = (user_auth or {}).get("currentUser") if user_auth else None
    if not current_user or not current_user.get("user_id"):
        if payload.get("_raw"):
            logger.warning("JWT 校验因网络异常跳过: %s", payload.get("_raw"))
            return (
                "预约凭证暂未校验（Traceint 返回异常）。凭据已保存，请稍后重试签到"
            )
        raise ValueError("JWT 校验未返回用户信息，请重新扫码粘贴最新授权链接")
    return None


def validate_wechat_sess_id(
    wechat_sess_id: str,
    authorization: str,
    serverid: Optional[str] = None,
    http_session: Optional[requests.Session] = None,
) -> Optional[str]:
    """
    用与签到相同的 keep_alive(devices.html) 做软性校验。
    网络抖动仍只返回警告；若 Traceint 明确返回登录失效，则阻断保存。
    """
    del http_session  # 换票 Session 与保活探测分离，避免 Cookie 互相干扰

    from app.core import WegolibCore

    session_cookie = build_checkin_session_id(wechat_sess_id, serverid)
    time.sleep(0.5)

    try:
        core = WegolibCore(session_cookie)
        result = core.keep_alive()
    except Exception as exc:
        if _is_transient_request_error(exc):
            logger.warning("签到会话保活校验网络异常: %s", exc)
        else:
            logger.warning("签到会话保活校验异常: %s", exc)
        return (
            "签到会话暂未在线校验（连接异常，可能因请求过于频繁）。"
            "凭据已保存，请直接尝试签到；若仍失败请等待数分钟后重新扫码"
        )

    if result.get("success"):
        return None

    msg = str(result.get("message") or "")
    logger.warning("签到会话保活校验未通过: %s", msg)
    if _is_wechat_session_expired_message(msg):
        raise ValueError(
            "换到的签到会话不可用：Traceint 保活返回登录状态已失效。"
            "请重新扫码并立即粘贴最新回调链接，系统会并发完成 JWT 与签到 Session 换票"
        )
    return (
        "签到会话暂未通过在线校验（凭据已保存）。"
        "请直接尝试签到；若仍提示登录失效，请等待 5–10 分钟后重新扫码授权"
    )


def fetch_user_auth(authorization: str, serverid: Optional[str] = None) -> Optional[WechatProfileSnapshot]:
    """GraphQL index 查询个人资料（JWT 已校验后调用）。"""
    cookie_parts = [f"Authorization={authorization}"]
    if serverid:
        cookie_parts.append(f"SERVERID={serverid}")

    headers = {
        "Host": "wechat.v2.traceint.com",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "App-Version": "2.2.5",
        "Origin": "https://web.traceint.com",
        "Referer": MINIPROGRAM_REFERER,
        "User-Agent": TRACEINT_UA,
        "Cookie": "; ".join(cookie_parts),
    }
    body = {
        "operationName": "index",
        "variables": {"pos": "App-首页", "param": []},
        "query": INDEX_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("GraphQL index 请求失败: %s", exc)
        return None

    if payload.get("errors"):
        logger.warning("GraphQL index 返回错误: %s", payload.get("errors"))
        return None

    user_auth = (payload.get("data") or {}).get("userAuth")
    if not user_auth:
        return None

    current_user = user_auth.get("currentUser")
    if not current_user:
        return None

    return _map_current_user(current_user)


def _map_current_user(current_user: dict[str, Any]) -> WechatProfileSnapshot:
    user_id = current_user.get("user_id")
    try:
        traceint_user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        traceint_user_id = None

    return WechatProfileSnapshot(
        traceint_user_id=traceint_user_id,
        nick=current_user.get("user_nick") or None,
        avatar=current_user.get("user_avatar") or None,
        student_name=current_user.get("user_student_name") or None,
        student_no=current_user.get("user_student_no") or None,
        sch=current_user.get("user_sch") or None,
        area_name=current_user.get("area_name") or None,
        fetched_at=datetime.now(),
    )


def parse_url_to_session_and_profile(
    url: str,
) -> Tuple[str, Optional[WechatProfileSnapshot], Optional[str]]:
    """
    一次粘贴、双换票：
    同一 code → 并发 auth.html(JWT) + wechatAuth.html(Session，独立 Session)
    → GraphQL 验 JWT → keep_alive 验 Session → 入库 wechatSESS_ID。
    返回 (session_id, profile, warning)。
    """
    code, state = parse_code_from_url(url)
    ticket = exchange_dual_authorization_and_session(code, state)
    authorization = ticket.authorization
    auth_serverid = ticket.auth_serverid
    wechat_sess_id = ticket.wechat_sess_id
    wechat_serverid = ticket.wechat_serverid

    warnings: list[str] = []
    jwt_warn = validate_authorization(
        authorization,
        auth_serverid,
        http_session=ticket.auth_session,
    )
    if jwt_warn:
        warnings.append(jwt_warn)
    sess_warn = validate_wechat_sess_id(
        wechat_sess_id, authorization, wechat_serverid
    )
    if sess_warn:
        warnings.append(sess_warn)

    profile: Optional[WechatProfileSnapshot] = None
    try:
        profile = fetch_user_auth(authorization, auth_serverid)
    except Exception as exc:
        logger.warning("获取微信个人资料失败: %s", exc)

    session_id = build_checkin_session_id(wechat_sess_id, wechat_serverid)
    warning = " ".join(warnings) if warnings else None
    return session_id, profile, warning
