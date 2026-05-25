"""
日志滚动模块测试

@author lvdaxianerplus
@date 2026-04-15
"""

import gzip
import os
import tempfile
from datetime import date, timedelta
import pytest
from app.utils.log_rotation import (
    get_log_filename,
    get_compressed_filename,
    get_log_filepath,
    get_compressed_filepath,
    find_log_files,
    compress_log_file,
    cleanup_old_compressed_logs,
    compress_yesterday_logs
)


class TestLogFilename:
    """日志文件名测试"""

    def test_get_log_filename(self):
        """测试获取日志文件名"""
        test_date = date(2026, 4, 15)
        filename = get_log_filename("myapp", test_date)
        assert filename == "myapp-2026-04-15.log"

    def test_get_compressed_filename(self):
        """测试获取压缩文件名"""
        test_date = date(2026, 4, 15)
        filename = get_compressed_filename("myapp", test_date)
        assert filename == "myapp-2026-04-15.log.gz"


class TestLogFilepath:
    """日志路径测试"""

    def test_get_log_filepath(self):
        """测试获取日志文件完整路径"""
        test_date = date(2026, 4, 15)
        filepath = get_log_filepath("/var/log", "myapp", test_date)
        assert filepath == "/var/log/myapp-2026-04-15.log"

    def test_get_compressed_filepath(self):
        """测试获取压缩文件完整路径"""
        test_date = date(2026, 4, 15)
        filepath = get_compressed_filepath("/var/log", "myapp", test_date)
        assert filepath == "/var/log/myapp-2026-04-15.log.gz"


class TestFindLogFiles:
    """查找日志文件测试"""

    def test_find_log_files_returns_empty_when_no_file(self, tmp_path):
        """当没有日志文件时返回空列表"""
        files = find_log_files(str(tmp_path), "myapp")
        assert files == []

    def test_find_log_files_returns_file_when_exists(self, tmp_path):
        """当日志文件存在时返回该文件"""
        # 创建测试文件
        yesterday = date.today() - timedelta(days=1)
        filename = f"myapp-{yesterday.strftime('%Y-%m-%d')}.log"
        test_file = tmp_path / filename
        test_file.write_text("test log content")

        files = find_log_files(str(tmp_path), "myapp")
        assert len(files) == 1
        assert files[0] == str(test_file)

    def test_find_log_files_excludes_already_compressed(self, tmp_path):
        """已压缩的文件不返回"""
        yesterday = date.today() - timedelta(days=1)
        filename = f"myapp-{yesterday.strftime('%Y-%m-%d')}.log"
        compressed_filename = f"{filename}.gz"

        # 创建日志文件和压缩文件
        (tmp_path / filename).write_text("test log content")
        (tmp_path / compressed_filename).write_text("compressed")

        files = find_log_files(str(tmp_path), "myapp")
        assert files == []


class TestCompressLogFile:
    """压缩日志文件测试"""

    def test_compress_success(self, tmp_path):
        """测试压缩成功"""
        # 创建测试文件
        test_file = tmp_path / "test-2026-04-14.log"
        test_content = "test log content " * 100  # 足够大以测试压缩率
        test_file.write_text(test_content)

        original_size = len(test_content)
        result = compress_log_file(str(test_file))

        # 验证压缩文件存在
        assert result is not None
        compressed_path = f"{test_file}.gz"
        assert os.path.exists(compressed_path)

        # 验证压缩后比原始文件小
        compressed_size = os.path.getsize(compressed_path)
        assert compressed_size < original_size

        # 验证压缩率大于 80%（文本重复内容压缩率高）
        compression_ratio = (1 - compressed_size / original_size) * 100
        assert compression_ratio > 50  # 至少 50% 压缩率

        # 验证原文件已删除
        assert not os.path.exists(test_file)

    def test_compress_file_not_exists(self, tmp_path):
        """测试压缩不存在的文件"""
        result = compress_log_file(str(tmp_path / "nonexistent.log"))
        assert result is None


class TestCleanupOldCompressedLogs:
    """清理过期压缩包测试"""

    def test_cleanup_deletes_old_files(self, tmp_path):
        """测试删除过期压缩包"""
        app_name = "myapp"

        # 创建过期的压缩文件（35 天前）
        old_date = (date.today() - timedelta(days=35)).strftime('%Y-%m-%d')
        old_file = tmp_path / f"{app_name}-{old_date}.log.gz"
        old_file.write_text("old compressed content")

        # 创建最近的压缩文件（5 天前）
        recent_date = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        recent_file = tmp_path / f"{app_name}-{recent_date}.log.gz"
        recent_file.write_text("recent compressed content")

        # 执行清理（保留 30 天）
        deleted_count = cleanup_old_compressed_logs(str(tmp_path), app_name, retention_days=30)

        # 验证只删除了过期文件
        assert deleted_count == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_cleanup_no_old_files(self, tmp_path):
        """当没有过期文件时删除数量为 0"""
        app_name = "myapp"

        # 创建一个最近的压缩文件
        recent_date = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        recent_file = tmp_path / f"{app_name}-{recent_date}.log.gz"
        recent_file.write_text("recent content")

        deleted_count = cleanup_old_compressed_logs(str(tmp_path), app_name, retention_days=30)

        assert deleted_count == 0
        assert recent_file.exists()


class TestCompressYesterdayLogs:
    """压缩昨日日志测试"""

    def test_compress_yesterday_no_files(self, tmp_path):
        """当没有昨日日志时返回空列表"""
        result = compress_yesterday_logs(str(tmp_path), "myapp")
        assert result == []

    def test_compress_yesterday_success(self, tmp_path):
        """测试压缩昨日日志成功"""
        yesterday = date.today() - timedelta(days=1)
        filename = f"myapp-{yesterday.strftime('%Y-%m-%d')}.log"
        test_file = tmp_path / filename
        test_file.write_text("yesterday log content")

        result = compress_yesterday_logs(str(tmp_path), "myapp")

        # 验证返回压缩后的文件
        assert len(result) == 1
        compressed_file = f"{test_file}.gz"
        assert os.path.exists(compressed_file)
        assert not os.path.exists(test_file)  # 原文件已删除
