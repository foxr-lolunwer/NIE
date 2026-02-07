import logging
import os
import sys
import shutil
from datetime import datetime


class LoggerManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            # 这里不设置 _initialized，由 __init__ 处理或手动 init_logger
        return cls._instance

    def __init__(self):
        # 初始默认状态
        if not hasattr(self, 'logger'):
            self.logger = logging.getLogger("NIE_LawParser")
            self._initialized = False
            self.log_folder = "log"
            self.latest_log_path = ""

    def init_logger(self, level=logging.INFO, log_folder="log"):
        """
        初始化日志配置
        :param level: 日志等级
        :param log_folder: 日志存放根目录
        """
        if self._initialized:
            self.set_level(level)
            return self.logger

        self.log_folder = log_folder
        if not os.path.exists(self.log_folder):
            os.makedirs(self.log_folder)

        self.latest_log_path = os.path.join(self.log_folder, "latest.log")
        self.logger.setLevel(level)

        # 格式化器
        formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s", datefmt='%H:%M:%S')

        # 1. 控制台处理器
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setFormatter(formatter)
        self.logger.addHandler(c_handler)

        # 2. 文件处理器 (latest.log)
        # 使用 mode='w' 确保每次启动覆盖旧的 latest，或者 'a' 追加
        f_handler = logging.FileHandler(self.latest_log_path, mode='w', encoding="utf-8-sig")
        f_handler.setFormatter(formatter)
        self.logger.addHandler(f_handler)

        # 注册崩溃处理和退出处理
        sys.excepthook = self._handle_crash

        self._initialized = True
        return self.logger

    def set_level(self, level):
        """动态更改等级"""
        self.logger.setLevel(level)
        self.logger.info(f"Log Level changed to: {logging.getLevelName(level)}")

    def get_logger(self):
        return self.logger

    def _handle_crash(self, exc_type, exc_value, exc_traceback):
        """当程序崩溃时触发的钩子"""
        # 首先记录错误到日志
        self.logger.critical("程序崩溃! 正在生成备份日志...", exc_info=(exc_type, exc_value, exc_traceback))

        # 执行备份
        self._archive_log(is_crash=True)

        # 调用默认的 excepthook 来打印错误到控制台
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _archive_log(self, is_crash=False):
        """将 latest.log 复制到时间戳文件夹"""
        if not os.path.exists(self.latest_log_path):
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        status = "CRASH" if is_crash else "EXIT"
        archive_dir = os.path.join(self.log_folder, f"{timestamp}_{status}")

        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)

        dest_path = os.path.join(archive_dir, "crash_report.log" if is_crash else "session.log")

        # 关闭所有 handler 释放文件句柄，确保复制成功
        for handler in self.logger.handlers:
            handler.close()

        shutil.copy2(self.latest_log_path, dest_path)
        # 崩溃时无法 print，但可以在此处执行其他清理逻辑


# 实例化
log_manager = LoggerManager()
