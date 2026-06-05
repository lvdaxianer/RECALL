"""
日志滚动模块

提供日志按天滚动、自动压缩、过期清理功能

@author lvdaxianerplus
@date 2026-04-15
"""

import gzip
import os
import shutil
from datetime import date, datetime, timedelta
from glob import glob
from typing import List, Optional
from app.utils.logger import get_logger

log_rotation_logger = get_logger("日志滚动")

DEFAULT_LOG_DIR = "./logs"
DEFAULT_APP_NAME = "app"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_COMPRESS_TIME = "00:05"


def get_log_filename(app_name: str, log_date: date) -> str:
    """获取日志文件名"""
    return f"{app_name}-{log_date.strftime('%Y-%m-%d')}.log"


def get_compressed_filename(app_name: str, log_date: date) -> str:
    """获取压缩文件名"""
    return f"{app_name}-{log_date.strftime('%Y-%m-%d')}.log.gz"


def get_log_filepath(log_dir: str, app_name: str, log_date: date) -> str:
    """获取日志文件完整路径"""
    filename = get_log_filename(app_name, log_date)
    return os.path.join(log_dir, filename)


def get_compressed_filepath(log_dir: str, app_name: str, log_date: date) -> str:
    """获取压缩文件完整路径"""
    filename = get_compressed_filename(app_name, log_date)
    return os.path.join(log_dir, filename)


def find_log_files(
    log_dir: str,
    app_name: str,
    target_date: Optional[date] = None
) -> List[str]:
    """查找指定日期未压缩的日志文件"""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    log_file = get_log_filepath(log_dir, app_name, target_date)
    compressed_file = get_compressed_filepath(log_dir, app_name, target_date)

    results = []
    if os.path.exists(log_file) and not os.path.exists(compressed_file):
        results.append(log_file)
        log_rotation_logger.info("[日志滚动] 找到待压缩日志: {}", log_file)

    return results


def compress_log_file(source_path: str) -> Optional[str]:
    """压缩日志文件为 gzip 格式"""
    if not os.path.exists(source_path):
        log_rotation_logger.warning("[日志滚动] 压缩失败，文件不存在: {}", source_path)
        return None

    source_size = os.path.getsize(source_path)
    target_path = f"{source_path}.gz"

    try:
        with open(source_path, 'rb') as f_in:
            with gzip.open(target_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        target_size = os.path.getsize(target_path)
        compression_ratio = (1 - target_size / source_size) * 100 if source_size > 0 else 0

        log_rotation_logger.info(
            "[日志滚动] 压缩成功, source={}, size={}KB->{}KB, 压缩率={:.1f}%",
            source_path, source_size // 1024, target_size // 1024, compression_ratio
        )

        os.remove(source_path)
        log_rotation_logger.info("[日志滚动] 删除原文件成功, path={}", source_path)

        return target_path

    except Exception as e:
        log_rotation_logger.error("[日志滚动] 压缩失败, path={}, error={}", source_path, str(e))
        return None


def cleanup_old_compressed_logs(
    log_dir: str,
    app_name: str,
    retention_days: int = DEFAULT_RETENTION_DAYS
) -> int:
    """清理过期的压缩包"""
    cutoff_date = date.today() - timedelta(days=retention_days)

    pattern = os.path.join(log_dir, f"{app_name}-*.log.gz")
    compressed_files = glob(pattern)

    deleted_count = 0
    for compressed_file in compressed_files:
        try:
            filename = os.path.basename(compressed_file)
            date_str = filename.replace(f"{app_name}-", "").replace(".log.gz", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            if file_date < cutoff_date:
                os.remove(compressed_file)
                deleted_count += 1
                log_rotation_logger.info("[日志滚动] 删除过期压缩包: {}", compressed_file)

        except Exception as e:
            log_rotation_logger.warning("[日志滚动] 删除压缩包失败, path={}, error={}", compressed_file, str(e))

    log_rotation_logger.info(
        "[日志滚动] 清理过期压缩包完成, deleted_count={}, retention_days={}",
        deleted_count, retention_days
    )

    return deleted_count


def compress_yesterday_logs(
    log_dir: str = DEFAULT_LOG_DIR,
    app_name: str = DEFAULT_APP_NAME
) -> List[str]:
    """压缩昨日的日志文件"""
    yesterday = date.today() - timedelta(days=1)
    log_rotation_logger.info("[日志滚动] 开始压缩昨日日志, date={}", yesterday)

    files_to_compress = find_log_files(log_dir, app_name, yesterday)

    if not files_to_compress:
        log_rotation_logger.info("[日志滚动] 无需压缩的日志文件")
        return []

    compressed_files = [
        result for result in (compress_log_file(f) for f in files_to_compress)
        if result
    ]

    log_rotation_logger.info("[日志滚动] 昨日日志压缩完成, compressed_count={}", len(compressed_files))
    return compressed_files


class LogRotationScheduler:
    """日志滚动调度器"""

    def __init__(
        self,
        log_dir: str = DEFAULT_LOG_DIR,
        app_name: str = DEFAULT_APP_NAME,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        compress_time: str = "00:05"
    ):
        """
        初始化日志滚动调度器

        @param log_dir - 日志目录
        @param app_name - 应用名称
        @param retention_days - 压缩包保留天数
        @param compress_time - 每日压缩执行时间（格式 HH:MM）
        """
        self.log_dir = log_dir
        self.app_name = app_name
        self.retention_days = retention_days
        self.compress_time = compress_time
        self._scheduler = None

    def _get_compress_job(self):
        """获取压缩任务的闭包"""
        def compress_job():
            """压缩昨日日志并清理过期压缩包"""
            log_rotation_logger.info("[日志滚动] 调度任务开始执行")
            try:
                compress_yesterday_logs(self.log_dir, self.app_name)
                cleanup_old_compressed_logs(self.log_dir, self.app_name, self.retention_days)
                log_rotation_logger.info("[日志滚动] 调度任务执行完成")
            except Exception as e:
                log_rotation_logger.error("[日志滚动] 调度任务执行失败, error={}", str(e))
        return compress_job

    def start(self):
        """启动调度器"""
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        if self._scheduler is not None:
            log_rotation_logger.warning("[日志滚动] 调度器已启动，忽略重复启动请求")
            return

        hour, minute = self.compress_time.split(":")

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            self._get_compress_job(),
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="log_compress",
            name="日志压缩任务",
            replace_existing=True
        )
        self._scheduler.start()

        log_rotation_logger.info(
            "[日志滚动] 调度器已启动, compress_time={}, retention_days={}",
            self.compress_time, self.retention_days
        )

    def stop(self):
        """停止调度器"""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            log_rotation_logger.info("[日志滚动] 调度器已停止")

    def is_running(self) -> bool:
        """
        检查调度器是否运行中

        @returns 调度器是否运行
        """
        return self._scheduler is not None and self._scheduler.running


_scheduler_instance: Optional[LogRotationScheduler] = None


def start_log_rotation_scheduler(
    log_dir: str = DEFAULT_LOG_DIR,
    app_name: str = DEFAULT_APP_NAME,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    compress_time: str = DEFAULT_COMPRESS_TIME
) -> LogRotationScheduler:
    """启动日志滚动调度器"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = LogRotationScheduler(
            log_dir=log_dir,
            app_name=app_name,
            retention_days=retention_days,
            compress_time=compress_time
        )
        _scheduler_instance.start()
    return _scheduler_instance


def stop_log_rotation_scheduler():
    """停止日志滚动调度器"""
    global _scheduler_instance
    if _scheduler_instance is not None:
        _scheduler_instance.stop()
        _scheduler_instance = None
