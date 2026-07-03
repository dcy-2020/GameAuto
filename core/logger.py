"""日志记录器模块"""
import os
import sys
import shutil
from datetime import datetime


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ReportLogger:
    """日志记录器 - 同时输出到控制台和文件"""

    def __init__(self, base_log_dir: str, config: dict = None):
        self.base_log_dir = base_log_dir
        self.config = config or {}
        self.log_buffer = []
        self.full_log_history = []
        self._log_callback = None
        try:
            sys.stdout.fileno()
            self.console_output = True
        except (OSError, AttributeError):
            self.console_output = False
        self.today_str = datetime.now().strftime("%Y-%m-%d")
        self.today_log_dir = os.path.join(base_log_dir, self.today_str)
        os.makedirs(self.today_log_dir, exist_ok=True)
        self.report_file = os.path.join(self.today_log_dir, f"report_{self.today_str}.log")

    def set_log_callback(self, callback):
        """设置日志回调，供 GUI 实时接收日志"""
        self._log_callback = callback

    def log(self, message: str, timestamp: bool = True, level: str = "INFO"):
        if timestamp:
            level_tag = f"[{level}]" if level != "INFO" else ""
            full_message = f"[{get_timestamp()}]{level_tag} {message}"
        else:
            full_message = message
        self.log_buffer.append(full_message)
        self.full_log_history.append(full_message)
        if self.console_output:
            try:
                print(full_message)
            except:
                pass
        # 通知 GUI
        if self._log_callback:
            try:
                self._log_callback(full_message, level)
            except:
                pass
        self._flush()

    def print(self, message: str):
        self.log(message, timestamp=False)

    def _flush(self):
        if not self.log_buffer:
            return
        try:
            with open(self.report_file, 'a', encoding='utf-8') as f:
                for line in self.log_buffer:
                    f.write(line + '\n')
            self.log_buffer = []
        except:
            pass

    def get_full_log(self) -> str:
        return '\n'.join(self.full_log_history)

    def get_report_file_path(self) -> str:
        return self.report_file

    def archive_original_logs(self):
        self.log("📦 正在归档原始日志文件...")
        today_str = self.today_str
        archived_count = 0

        try:
            okww_log = os.path.join(self.config.get("okww_log_dir", ""), "ok-script.log")
            if os.path.exists(okww_log):
                dest = os.path.join(self.today_log_dir, f"okww_{today_str}.log")
                shutil.copy2(okww_log, dest)
                archived_count += 1
                self.log(f"  ✅ ok-ww 日志已归档")
        except Exception as e:
            self.log(f"  ❌ 归档 ok-ww 日志失败: {e}", level="WARN")

        try:
            maaend_dir = self.config.get("maaend_log_dir", "")
            if maaend_dir and os.path.exists(maaend_dir):
                for fname in os.listdir(maaend_dir):
                    if fname.startswith(today_str) and fname.endswith(".log") and fname != "maafw.log":
                        src = os.path.join(maaend_dir, fname)
                        dest = os.path.join(self.today_log_dir, f"maaend_{fname}")
                        shutil.copy2(src, dest)
                        archived_count += 1
                if archived_count == 0:
                    self.log(f"  ⚠️ 未找到 MaaEnd 当天的运行日志")
        except Exception as e:
            self.log(f"  ❌ 归档 MaaEnd 日志失败: {e}", level="WARN")
        self.log(f"📦 日志归档完成，共归档 {archived_count} 个文件")

        try:
            oknte_log = os.path.join(self.config.get("oknte_log_dir", ""), "ok-script.log")
            if os.path.exists(oknte_log):
                dest = os.path.join(self.today_log_dir, f"oknte_{today_str}.log")
                shutil.copy2(oknte_log, dest)
                self.log(f"  ✅ ok-nte 日志已归档")
        except:
            pass