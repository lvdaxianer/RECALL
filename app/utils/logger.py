"""
日志工具模块

支持业务标识格式：[业务标识] 消息内容

@author lvdaxianerplus
@date 2026-04-14
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


class BusinessLogger:
    """业务日志类

    支持带业务标识的日志格式

    示例：
        logger = BusinessLogger("RAG检索")
        logger.info("查询开始, queryId={}", query_id)
        # 输出：[RAG检索] 查询开始, queryId=123
    """

    def __init__(self, business_tag: str):
        """
        初始化业务日志器

        @param business_tag - 业务标识，如 "RAG检索"、"Milvus" 等
        """
        self.business_tag = business_tag
        self.logger = logging.getLogger(business_tag)
        self._setup_logger()

    def _setup_logger(self):
        """配置日志格式"""
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                fmt=f"%(asctime)s [%(name)s] %(levelname)s - [{self.business_tag}] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)

    def _format_message(self, message: str, *args) -> str:
        """
        格式化日志消息

        @param message - 消息模板，使用 {} 占位符
        @param args - 替换参数
        @returns 格式化后的消息
        """
        if args:
            try:
                return message.format(*args)
            except (IndexError, KeyError):
                return message
        return message

    def debug(self, message: str, *args):
        """
        DEBUG 级别日志

        @param message - 消息模板
        @param args - 参数
        """
        self.logger.debug(self._format_message(message, *args))

    def info(self, message: str, *args):
        """
        INFO 级别日志

        @param message - 消息模板
        @param args - 参数
        """
        self.logger.info(self._format_message(message, *args))

    def warning(self, message: str, *args):
        """
        WARNING 级别日志

        @param message - 消息模板
        @param args - 参数
        """
        self.logger.warning(self._format_message(message, *args))

    def error(self, message: str, *args):
        """
        ERROR 级别日志

        @param message - 消息模板
        @param args - 参数
        """
        self.logger.error(self._format_message(message, *args))


def setup_logging():
    """
    初始化日志系统

    配置控制台输出和文件输出（按天滚动）

    @author lvdaxianerplus
    @date 2026-04-15
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if root_logger.handlers:
        return

    _add_console_handler(root_logger)
    _add_file_handler(root_logger)


def _add_console_handler(root_logger):
    """
    配置控制台输出

    @param root_logger - 根日志器
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)


def _add_file_handler(root_logger):
    """
    配置文件输出（按天滚动）

    @param root_logger - 根日志器
    """
    log_dir = os.getenv("LOG_DIR", "./logs")
    app_name = os.getenv("APP_NAME", "app")

    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 使用 TimedRotatingFileHandler，每天午夜滚动
    log_file = os.path.join(log_dir, f"{app_name}.log")
    file_handler = TimedRotatingFileHandler(
        when="midnight",
        interval=1,
        backupCount=0,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)


# 预定义的业务日志器
def get_logger(business_tag: str) -> BusinessLogger:
    """
    获取业务日志器

    @param business_tag - 业务标识
    @returns BusinessLogger 实例
    """
    return BusinessLogger(business_tag)


# 常用日志器实例
config_logger = get_logger("配置加载")
milvus_logger = get_logger("Milvus")
embedding_logger = get_logger("Embedding")
rerank_logger = get_logger("Rerank")
rag_insert_logger = get_logger("RAG插入")
rag_search_logger = get_logger("RAG检索")
rag_delete_logger = get_logger("RAG删除")
