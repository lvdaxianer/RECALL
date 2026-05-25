"""
Pytest 配置文件

@author lvdaxianerplus
@date 2026-04-14
"""

import pytest
import sys
import os

# 将 app 目录添加到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 配置 pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def mock_logger():
    """Mock 日志器"""
    from unittest.mock import MagicMock
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    return logger
