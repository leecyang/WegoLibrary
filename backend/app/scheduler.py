from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import (
    engine, Session, Config,
    get_all_active_configs, get_config_by_owner,
    update_session_id_for_config,
    log_checkin_by_owner
)
from app.core import WegolibCore
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def _keep_alive_single(session: Session, config: Config) -> bool:
    """为单个用户执行保活"""
    if not config.session_id:
        return False
    
    user_identifier = f"User(ID={config.owner_id})"

    try:
        core = WegolibCore(config.session_id)
        result = core.keep_alive()

        # 如果 session_id 被服务器更新
        if result.get("new_session_id"):
            update_session_id_for_config(session, config, result["new_session_id"])
            logger.info(f"Session ID updated for {user_identifier}...")

        # 记录保活结果
        config.last_keepalive = datetime.now()
        config.last_log = f"KeepAlive: {result['message']}"
        session.add(config)
        session.commit()

        if result["success"]:
            logger.info(f"Keep-alive success for {user_identifier}...")
        else:
            logger.warning(f"Keep-alive failed for {user_identifier}...: {result['message']}")

        return result["success"]
    except Exception as e:
        logger.error(f"Keep-alive error for {user_identifier}...: {e}")
        return False

def _checkin_single(session: Session, config: Config) -> bool:
    if not config.session_id:
        return False
    user_identifier = f"User(ID={config.owner_id})"
    try:
        core = WegolibCore(config.session_id)
        result = core.sign_in(config.major, config.minor)
        log_checkin_by_owner(session, config.owner_id, result["success"], result["message"])
        if result["success"]:
            logger.info(f"Auto check-in success for {user_identifier}...")
        else:
            logger.warning(f"Auto check-in failed for {user_identifier}...: {result['message']}")
        return result["success"]
    except Exception as e:
        logger.error(f"Auto check-in error for {user_identifier}...: {e}")
        return False

def keep_alive_job():
    """定时任务：为所有活跃用户执行保活"""
    with Session(engine) as session:
        configs = get_all_active_configs(session)

        if not configs:
            logger.debug("No active users to keep alive")
            return

        logger.info(f"Running keep-alive for {len(configs)} active user(s)")

        for config in configs:
            try:
                _keep_alive_single(session, config)
            except Exception as e:
                # 尝试获取标识
                uid = config.owner_id if config.owner_id else config.user_id
                logger.error(f"Keep-alive failed for User {uid}...: {e}")

def keep_alive_for_user(owner_id: int):
    """为指定用户执行保活（手动触发时使用）"""
    with Session(engine) as session:
        config = get_config_by_owner(session, owner_id)
        if config and config.is_active and config.session_id:
            _keep_alive_single(session, config)

def auto_checkin_job(owner_id: int):
    with Session(engine) as session:
        config = get_config_by_owner(session, owner_id)
        if not config or not config.is_active or not config.session_id:
            return
        _checkin_single(session, config)

def start_auto_checkin_for_user(owner_id: int, expire_at: datetime):
    trigger = IntervalTrigger(minutes=18, start_date=datetime.now() + timedelta(minutes=18), end_date=expire_at)
    job_id = f"auto_checkin_{owner_id}"
    scheduler.add_job(auto_checkin_job, trigger, id=job_id, replace_existing=True, kwargs={"owner_id": owner_id})
    logger.info(f"Auto check-in scheduled for User(ID={owner_id}) every 18 minutes until {expire_at}")

def stop_auto_checkin_for_user(owner_id: int):
    job_id = f"auto_checkin_{owner_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Auto check-in stopped for User(ID={owner_id})")
    except Exception:
        pass

def start_scheduler():
    trigger = IntervalTrigger(minutes=5)
    scheduler.add_job(keep_alive_job, trigger, id='keep_alive', replace_existing=True)
    now = datetime.now()
    with Session(engine) as session:
        configs = get_all_active_configs(session)
        for config in configs:
            if not config.owner_id:
                continue
            if not config.auto_checkin_expire_at:
                continue
            if config.auto_checkin_expire_at <= now:
                continue
            start_auto_checkin_for_user(config.owner_id, config.auto_checkin_expire_at)
    scheduler.start()
    logger.info("Scheduler started - will process all active users every 5 minutes")

def shutdown_scheduler():
    scheduler.shutdown()
