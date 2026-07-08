"""TaskRunner - 后台线程编排游戏日常自动化主流程"""
import os
import sys
import time
import subprocess
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

# 导入手柄：兼容源码运行和 PyInstaller 打包后的环境
try:
    from Switcher.WwAccountSwitcher import WwAccountSwitcher
except ImportError:
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_dir_init = os.path.dirname(_current_dir)
    _switcher_dir = os.path.join(_project_dir_init, "Switcher")
    if _switcher_dir not in sys.path:
        sys.path.insert(0, _switcher_dir)
    from WwAccountSwitcher import WwAccountSwitcher

# 解析项目根目录（用于定位 Switcher/imgs 等资源）
if getattr(sys, 'frozen', False):
    _project_dir = sys._MEIPASS
else:
    _project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from .logger import ReportLogger
from .ai_assistant import AIAssistant
from .log_analyzer import (
    TaskStatus, TimelineEvent, TaskResult,
    OkWwLogAnalyzer, MaaEndLogAnalyzer, OkNteLogAnalyzer,
    get_latest_okww_log, get_latest_maaend_log, get_latest_oknte_log,
)
from .process_tools import (
    activate_target_window, ensure_esc_menu, smart_cleanup, clear_logs,
    is_process_running_by_name, safe_kill_process, set_window_foreground,
    iter_windows_by_title,
)
from .network import check_boot_environment_ready, ensure_network_ready
from .dingtalk import send_dingtalk_message, send_detailed_dingtalk_report
from .history import HistoryManager
from .shutdown import auto_shutdown, force_shutdown, cancel_shutdown


@dataclass
class WatchdogConfig:
    """通用看门狗的运行时参数，集中描述一个任务的启动与监控方式"""
    task_label: str           # 任务标签，如 "鸣潮"
    log_prefix: str           # 日志前缀，如 "[WW]"
    analyzer: object          # 日志分析器实例
    cwd: str                  # 进程工作目录
    cmd: List[str]            # 子进程启动命令
    exe_names: List[str]      # 清理时匹配的 exe 名列表
    keywords: List[str]       # 清理时匹配的窗口关键词
    log_dir: str              # 日志目录
    find_latest_log: callable # 返回最新日志文件路径
    ai_keywords: List[str]    # AI 激活窗口关键词
    ai_context_fn: callable   # 返回 AI 上下文字符串
    post_start_activate_keywords: Optional[List[str]] = None  # 启动后激活窗口的关键词（None=不激活，WW 特有）
    special_failure_fn: Optional[callable] = None  # 自定义失败处理 (result, analyzer) -> bool


class GlobalState:
    """持有分析器和运行时状态"""

    def __init__(self):
        self.ww_analyzer: OkWwLogAnalyzer = None
        self.ef_analyzer: MaaEndLogAnalyzer = None
        self.nte_analyzer: OkNteLogAnalyzer = None
        self.current_process = None
        self.ww_success = False
        self.ef_success = False
        self.nte_success = False


class TaskRunner:
    """后台线程编排器 - 在 daemon thread 中运行主流程，通过日志回调通知 GUI"""

    def __init__(self, config: dict, log_callback=None, progress_callback=None,
                 status_callback=None):
        self.config = config
        self._log_callback = log_callback
        self._progress_callback = progress_callback
        self._status_callback = status_callback
        self._thread: threading.Thread = None
        self._should_stop = False
        self._is_running = False
        self._lock = threading.Lock()
        # 运行时辅助字段
        self._ai_client = None
        self._program_deadline = None

    # ---------- 公共 API ----------

    def start(self):
        """启动后台任务线程"""
        with self._lock:
            if self._is_running:
                return False
            self._should_stop = False
            self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """发送停止信号（非阻塞，由调用方轮询 is_running 确认完成）"""
        self._should_stop = True

    def is_running(self) -> bool:
        return self._is_running

    # ---------- 内部方法 ----------

    def _sleep(self, seconds: float, tick: float = 0.3):
        """可中断睡眠：每 tick 秒检查一次 _should_stop，实现即时响应"""
        elapsed = 0.0
        while elapsed < seconds:
            if self._should_stop:
                return
            chunk = min(tick, seconds - elapsed)
            time.sleep(chunk)
            elapsed += chunk

    def _log(self, msg: str, level: str = "INFO"):
        try:
            cb = self._log_callback
            if cb:
                cb(msg, level)
        except Exception as e:
            print(f"[WARN] log_callback 异常: {e}")

    def _notify_status(self, status: str):
        try:
            cb = self._status_callback
            if cb:
                cb(status)
        except Exception as e:
            print(f"[WARN] status_callback 异常: {e}")

    def _check_stop(self) -> bool:
        return self._should_stop

    def _init_ai_client(self, logger):
        """初始化 AI 辅助模块"""
        if self.config.get("enable_ai_assist", False) and self.config.get("dashscope_api_key"):
            client = AIAssistant(
                api_key=self.config["dashscope_api_key"],
                model=self.config.get("ai_model", ""),
                logger=logger,
                provider=self.config.get("ai_provider", "aliyun"),
                base_url=self.config.get("ai_base_url", ""),
            )
            logger.log(f"🧠 AI辅助模块已初始化（服务商={self.config.get('ai_provider', 'aliyun')}）")
            return client
        if self.config.get("enable_ai_assist", False):
            logger.log("⚠️ AI未启用：缺少API Key", level="WARN")
        return None

    # ---------- 通用看门狗 ----------

    def _run_with_watchdog(self, logger, wd: WatchdogConfig, retry_count: int, max_retries: int,
                           state=None) -> bool:
        """通用的看门狗循环：清理 → 启动进程 → 监控日志 → AI 自救 → 清理退出。

        将 _run_ww_task / _run_ef_task / _run_nte_task 的共同逻辑合并至此。
        返回 True 表示成功，False 表示失败。
        """
        cfg = self.config

        # 循环内频繁读取的配置缓存到局部变量（避免每次迭代查字典）
        watchdog_interval = cfg["watchdog_interval"]
        global_task_timeout = cfg["global_task_timeout"]
        ai_max_attempts = cfg.get("ai_max_attempts", 10)
        ai_assist_enabled = cfg.get("enable_ai_assist", False)

        logger.log("----------------------------------------")
        logger.log(f"⚙️ {wd.log_prefix} 开始第 {retry_count}/{max_retries} 次自动化流程")

        # 1. 清理旧进程与日志
        smart_cleanup(cfg, logger, wd.exe_names, wd.keywords)
        clear_logs(wd.log_dir)

        # 2. 定位最新日志
        latest_log = wd.find_latest_log()
        if latest_log:
            wd.analyzer.seek_to_end(latest_log)
            logger.log(f"🔍 {wd.log_prefix} 已屏蔽历史日志，准备捕捉本次运行")
        else:
            logger.log(f"⚠️ 未找到 {wd.log_prefix} 日志文件，将从头开始读取", level="WARN")

        # 3. 启动子进程
        os.chdir(wd.cwd)
        process = subprocess.Popen(
            wd.cmd,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if state is not None:
            state.current_process = process

        self._sleep(cfg.get("process_start_wait", 8))

        # 4. WW 特有：启动后将游戏窗口置前台，便于后续截图/模板匹配
        if wd.post_start_activate_keywords:
            activate_target_window(wd.post_start_activate_keywords, cfg)

        logger.log("🐶 看门狗已启动...")

        wd.analyzer._ai_attempt_count = 0
        start_time = time.time()

        def cleanup_and_exit(status: bool) -> bool:
            if process.poll() is None:
                process.kill()
            smart_cleanup(cfg, logger, wd.exe_names, wd.keywords)
            if state is not None and state.current_process is process:
                state.current_process = None
            return status

        while True:
            if self._check_stop():
                logger.log(f"⏹️ {wd.log_prefix} 用户中断")
                return cleanup_and_exit(False)

            # 轮询间隔（与原版一致：每次迭代先睡 watchdog_interval，避免忙等待烧 CPU）
            self._sleep(watchdog_interval)

            # 全局超时
            if self._program_deadline and time.time() > self._program_deadline:
                logger.log("⏰ 程序总时长超限，强制结束本任务", level="ERROR")
                return cleanup_and_exit(False)

            if time.time() - start_time > global_task_timeout:
                logger.log(f"⏰ {wd.log_prefix} 全局超时，强制终止", level="ERROR")
                return cleanup_and_exit(False)

            result = wd.analyze_fn(process)

            if result.status == TaskStatus.SUCCESS:
                return cleanup_and_exit(True)

            if result.status == TaskStatus.FAILED:
                # 允许调用方做特殊处理（如 WW 切号失败妥协）
                if wd.special_failure_fn is not None and wd.special_failure_fn(result, wd.analyzer):
                    smart_cleanup(cfg, logger, wd.exe_names, wd.keywords)
                    return True
                logger.log(f"❌ {wd.task_label}任务失败: {result.error_message}")
                smart_cleanup(cfg, logger, wd.exe_names, wd.keywords)
                return False

            # 运行中：AI 异常自救
            if ai_assist_enabled and self._ai_client is not None:
                if wd.analyzer.is_log_timeout(cfg):
                    if wd.analyzer._ai_attempt_count >= ai_max_attempts:
                        logger.log(f"❌ {wd.log_prefix} AI尝试次数已达上限，放弃并执行清理")
                        return cleanup_and_exit(False)

                    wd.analyzer._ai_attempt_count += 1
                    logger.log(f"⏳ {wd.log_prefix} 日志超时，疑似卡在未知弹窗，尝试AI自救...")

                    activate_target_window(wd.ai_keywords, cfg)
                    self._sleep(0.3)
                    screenshot_b64 = self._ai_client.capture_screen()

                    if screenshot_b64:
                        context = wd.ai_context_fn()
                        action = self._ai_client.ask_for_action(
                            screenshot_b64, context, timeout=cfg.get("ai_api_timeout", 300))
                        if action and self._ai_client.execute_action(action):
                            wd.analyzer.last_log_time = time.time()
                            continue
                        else:
                            logger.log(f"⚠️ {wd.log_prefix} AI无有效动作，继续等待")
                    else:
                        logger.log(f"⚠️ {wd.log_prefix} 截图失败，跳过AI")

            # 非 AI 路径的超时判定
            if wd.analyzer.is_log_timeout(cfg):
                logger.log(f"⚠️ {wd.log_prefix} 日志超时，且AI未能恢复，执行清理", level="WARN")
                return cleanup_and_exit(False)

    # ---------- 鸣潮任务 ----------

    def _run_ww_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 ok-ww 任务"""
        state.ww_analyzer.reset_for_new_run()
        cfg = self.config

        self._ai_client = ai_client
        self._program_deadline = program_deadline

        run_mode = cfg.get("okww_run_mode", 1)
        logger.log(f"🚀 启动 ok-ww.exe (模式 -t {run_mode})")

        # 切号失败妥协逻辑
        def special_failure(result, analyzer):
            if "疑似切号失败" in result.error_message and retry_count == cfg["ww_max_retries"]:
                logger.log("⚠️ 已达最大重试次数，该账号可能真实无体力，妥协视为成功")
                analyzer.status = TaskStatus.SUCCESS
                analyzer.error_message = ""
                analyzer.finish_event("success", "", time.time())
                return True
            return False

        wd = WatchdogConfig(
            task_label="鸣潮",
            log_prefix="[WW]",
            analyzer=state.ww_analyzer,
            cwd=cfg["okww_path"],
            cmd=[cfg["okww_exe"], "-t", str(run_mode), "-e"],
            exe_names=["ok-ww.exe"],
            keywords=["ok-ww"],
            log_dir=cfg["okww_log_dir"],
            find_latest_log=lambda: get_latest_okww_log(cfg["okww_log_dir"]),
            ai_keywords=["鸣潮", "wuthering"],
            ai_context_fn=lambda: f"鸣潮日常，账号 {state.ww_analyzer.current_account}，进度 {state.ww_analyzer.progress}/{state.ww_analyzer.total}",
            post_start_activate_keywords=["鸣潮", "wuthering", "ok-ww.exe"],
            special_failure_fn=special_failure,
        )
        # 将 analyze_fn 绑定为闭包
        wd.analyze_fn = lambda proc: state.ww_analyzer.analyze(proc.poll() is None, cfg["okww_log_dir"])

        return self._run_with_watchdog(logger, wd, retry_count, cfg["ww_max_retries"], state=state)

    # ---------- 终末地任务 ----------

    def _run_ef_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 MaaEnd 任务"""
        state.ef_analyzer.reset()
        cfg = self.config

        self._ai_client = ai_client
        self._program_deadline = program_deadline

        logger.log("🚀 启动 MaaEnd.exe")

        wd = WatchdogConfig(
            task_label="终末地",
            log_prefix="[EF]",
            analyzer=state.ef_analyzer,
            cwd=cfg["maaend_path"],
            cmd=[cfg["maaend_exe"], "--autostart", "--instance", "全套日常", "--quit-after-run"],
            exe_names=["MaaEnd.exe", "Endfield.exe", "Endfield-Win64-Shipping.exe"],
            keywords=["MaaEnd", "终末地", "endfield"],
            log_dir=cfg["maaend_log_dir"],
            find_latest_log=lambda: get_latest_maaend_log(cfg["maaend_log_dir"]),
            ai_keywords=["终末地", "endfield"],
            ai_context_fn=lambda: f"终末地日常，当前进度 {state.ef_analyzer.progress}/{state.ef_analyzer.total}",
        )
        wd.analyze_fn = lambda proc: state.ef_analyzer.analyze(proc.poll() is None, cfg["maaend_log_dir"])

        return self._run_with_watchdog(logger, wd, retry_count, cfg["ef_max_retries"], state=state)

    # ---------- 异环任务 ----------

    def _run_nte_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 ok-nte 任务"""
        state.nte_analyzer.reset()
        cfg = self.config

        self._ai_client = ai_client
        self._program_deadline = program_deadline

        logger.log("🚀 启动 ok-nte.exe (模式 -t 2)")

        oknte_log_dir = cfg.get("oknte_log_dir", "")
        nte_max_retries = cfg.get("nte_max_retries", 2)

        wd = WatchdogConfig(
            task_label="异环",
            log_prefix="[NTE]",
            analyzer=state.nte_analyzer,
            cwd=cfg["oknte_path"],
            cmd=[cfg["oknte_exe"], "-t", "2", "-e"],
            exe_names=["ok-nte.exe", "NTE.exe", "HTGame.exe"],
            keywords=["ok-nte", "异环", "NTE.exe", "HTGame.exe"],
            log_dir=oknte_log_dir,
            find_latest_log=lambda: get_latest_oknte_log(oknte_log_dir),
            ai_keywords=["异环", "NTE.exe"],
            ai_context_fn=lambda: "异环日常",
        )
        wd.analyze_fn = lambda proc: state.nte_analyzer.analyze(oknte_log_dir)

        return self._run_with_watchdog(logger, wd, retry_count, nte_max_retries, state=state)

    # ---------- 游戏模块级封装 ----------

    def _run_ww_module(self, logger, state, ai_client, cfg, program_deadline):
        """运行鸣潮完整流水线：首发盲跑 → 切号 → 清理，返回 (cost, success)"""
        ww_start = time.time()

        state.ww_analyzer.reset()
        switcher_img_dir = os.path.join(_project_dir, "Switcher", "imgs")
        switcher = WwAccountSwitcher(img_folder_name=switcher_img_dir)
        base_accounts = list(cfg["okww_expected_accounts"])

        logger.log("🎮 [总控] 启动首发盲跑模式...")

        first_success = False
        for retry in range(1, cfg["ww_max_retries"] + 1):
            if self._check_stop():
                break
            first_success = self._run_ww_task(logger, state, ai_client, retry, program_deadline)
            if first_success:
                break
            if time.time() > program_deadline:
                force_shutdown(cfg, logger, "全局超时")
            if retry < cfg["ww_max_retries"]:
                logger.log(f"[WARN] 🔄 ok-ww 引擎异常，休息{cfg['retry_wait']}秒后重启...")
                self._sleep(cfg["retry_wait"])

        all_ww_success = first_success

        if first_success and not self._check_stop():
            first_acc = state.ww_analyzer.current_account
            state.ww_analyzer.start_event(f"[{first_acc}] 结算并返回登录界面", time.time())

            logger.log("🔌 [总控] 首发完成，执行登出并顺路识别账号...")
            self._sleep(3)

            if not ensure_esc_menu(cfg, logger, switcher=switcher, ai_client=ai_client):
                logger.log("❌ 无法将游戏定位到 ESC 菜单，终止切号")
                all_ww_success = False
            else:
                current_on_screen = switcher.logout_from_esc_menu(base_accounts)
                state.ww_analyzer.finish_event("success", "", time.time())

                if current_on_screen and current_on_screen in base_accounts:
                    state.ww_analyzer.retroactively_update_account(current_on_screen)
                    idx = base_accounts.index(current_on_screen)
                    remaining_accounts = base_accounts[idx + 1:] + base_accounts[:idx]
                    logger.log(f"🧠 [总控] 看到刚才完成的是 [{current_on_screen}]！推导后续队列为: {' -> '.join(remaining_accounts) if remaining_accounts else '无'}")
                else:
                    logger.log("⚠️ [总控] 识别失败，降级为默认顺序盲切", level="WARN")
                    remaining_accounts = base_accounts[1:]
                    current_on_screen = None

                for i, next_acc in enumerate(remaining_accounts):
                    if self._check_stop():
                        break
                    logger.log(f"\n🔑 [总控] 准备登录至: [{next_acc}]...")

                    state.ww_analyzer.start_event(f"[{next_acc}] 切换账号并尝试登录", time.time())

                    if switcher.login_from_screen(next_acc, current_on_screen):
                        state.ww_analyzer.finish_event("success", "", time.time())

                        wait_time = 5
                        state.ww_analyzer.start_event(f"[{next_acc}] 登录成功，执行大世界检测", time.time())
                        logger.log(f"✅ [总控] 登录成功，静默等待大世界加载 {wait_time} 秒...")
                        self._sleep(wait_time)
                        state.ww_analyzer.finish_event("success", "", time.time())

                        state.ww_analyzer.current_account = next_acc

                        acc_success = False
                        for retry in range(1, cfg["ww_max_retries"] + 1):
                            if self._check_stop():
                                break
                            acc_success = self._run_ww_task(logger, state, ai_client, retry, program_deadline)
                            if acc_success:
                                break
                            if time.time() > program_deadline:
                                force_shutdown(cfg, logger, "全局超时")
                            if retry < cfg["ww_max_retries"]:
                                logger.log("[WARN] 🔄 ok-ww 重试中...")
                                self._sleep(cfg["retry_wait"])

                        if not acc_success:
                            logger.log(f"❌ [总控] 账号 [{next_acc}] 任务彻底失败，终止流水线。", level="ERROR")
                            all_ww_success = False
                            break

                        if i < len(remaining_accounts) - 1:
                            state.ww_analyzer.start_event(f"[{next_acc}] 结算并返回登录界面", time.time())
                            logger.log("🚪 [总控] 任务完成，登出准备下一个号...")
                            self._sleep(3)

                            if not ensure_esc_menu(cfg, logger, switcher=switcher, ai_client=ai_client):
                                logger.log("❌ 无法将游戏定位到 ESC 菜单，终止切号")
                                all_ww_success = False
                                break

                            current_on_screen = switcher.logout_from_esc_menu(base_accounts)
                            state.ww_analyzer.finish_event("success", "", time.time())
                            if current_on_screen is None:
                                logger.log("⚠️ 识别失败，将在下一轮登录时重新判断", level="WARN")
                    else:
                        logger.log(f"❌ [总控] 图形化切号至 {next_acc} 失败！终止流水线。", level="ERROR")
                        all_ww_success = False
                        break
        elif not first_success:
            logger.log("❌ [总控] 首发账号遭遇滑铁卢，直接放弃后续任务。", level="ERROR")

        # 统一清理（无论成功失败都做）
        logger.log("🧹 [总控] 鸣潮全账号流水线执行完毕，正在关闭游戏客户端释放资源...")
        smart_cleanup(
            cfg, logger,
            ["ok-ww.exe", "Wuthering Waves.exe", "Client-Win64-Shipping.exe"],
            ["鸣潮", "wuthering", "ok-ww"],
        )
        self._sleep(8)
        if all_ww_success:
            state.ww_analyzer.status = TaskStatus.SUCCESS
            state.ww_analyzer.start_event("执行游戏清理与结束", time.time())
            state.ww_analyzer.finish_event("success", "", time.time())
        else:
            state.ww_analyzer.status = TaskStatus.FAILED

        state.ww_success = all_ww_success
        return time.time() - ww_start, all_ww_success

    def _run_ef_module(self, logger, state, ai_client, cfg, program_deadline):
        """运行终末地模块，返回 (cost, success)"""
        ef_start = time.time()
        for retry in range(1, cfg["ef_max_retries"] + 1):
            if self._check_stop():
                break
            state.ef_success = self._run_ef_task(logger, state, ai_client, retry, program_deadline)
            if state.ef_success:
                break
            if time.time() > program_deadline:
                force_shutdown(cfg, logger, "全局超时")
            if retry < cfg["ef_max_retries"]:
                logger.log(f"[WARN] 🔄 休息{cfg['retry_wait']}秒后重试...")
                wait_remain = cfg["retry_wait"]
                while wait_remain > 0:
                    if self._check_stop() or time.time() > program_deadline:
                        break
                    self._sleep(min(5, wait_remain))
                    wait_remain -= 5
        return time.time() - ef_start, state.ef_success

    def _run_nte_module(self, logger, state, ai_client, cfg, program_deadline):
        """运行异环模块，返回 (cost, success)"""
        nte_start = time.time()
        nte_max_retries = cfg.get("nte_max_retries", 2)
        for retry in range(1, nte_max_retries + 1):
            if self._check_stop():
                break
            state.nte_success = self._run_nte_task(logger, state, ai_client, retry, program_deadline)
            if state.nte_success:
                break
            if time.time() > program_deadline:
                force_shutdown(cfg, logger, "全局超时")
            if retry < nte_max_retries:
                logger.log(f"[WARN] 🔄 休息{cfg['retry_wait']}秒后重试...")
                self._sleep(cfg["retry_wait"])
        return time.time() - nte_start, state.nte_success

    # ---------- 主循环 ----------

    def _run_loop(self):
        """主执行循环"""
        cfg = self.config
        logger = ReportLogger(cfg["report_log_path"], cfg)
        logger.set_log_callback(self._log_callback)
        history_manager = HistoryManager(cfg, logger)

        # 初始化 AI
        ai_client = self._init_ai_client(logger)

        # 创建运行时状态
        state = GlobalState()
        state.ww_analyzer = OkWwLogAnalyzer(
            expected_accounts=cfg.get("okww_expected_accounts", []),
            run_mode=cfg.get("okww_run_mode", 1),
            config=cfg,
            logger=logger,
        )
        state.ef_analyzer = MaaEndLogAnalyzer()
        state.nte_analyzer = OkNteLogAnalyzer()

        logger.print("=" * 40)
        logger.print(f"  🤖 游戏日常自动化中枢 - {datetime.now().strftime('%Y-%m-%d')}")
        logger.print("=" * 40)

        if self._check_stop():
            return

        if not check_boot_environment_ready(cfg, logger):
            logger.log("❌ 环境初始化彻底失败，取消今日自动化任务。")
            send_dingtalk_message("# 🤖 报告:自动化中断报警\n网络自愈失败，无法连接网络，任务已取消。", cfg)
            auto_shutdown(cfg, logger)
            return

        program_start = time.time()
        max_program_runtime = cfg.get("max_program_runtime", 10800)
        program_deadline = program_start + max_program_runtime

        total_rounds = cfg.get("total_rounds", 1)
        round_interval = cfg.get("round_interval", 600)

        last_ww_success = False
        last_ef_success = False
        last_ww_cost = 0
        last_ef_cost = 0

        for round_num in range(1, total_rounds + 1):
            if self._check_stop():
                break
            if time.time() > program_deadline:
                force_shutdown(cfg, logger, "全局超时")
                return

            logger.print("")
            logger.print("=" * 40)
            logger.log(f"🔄 开始第 {round_num} / {total_rounds} 轮执行")
            logger.print("=" * 40)

            state.ww_success = False
            state.ef_success = False
            state.nte_success = False

            # ==================== 鸣潮模块 ====================
            ww_cost = 0
            if cfg.get("enable_okww", True):
                ww_cost, state.ww_success = self._run_ww_module(logger, state, ai_client, cfg, program_deadline)
            else:
                logger.log("⏸️ [总控] 鸣潮功能未启用，跳过执行")
                state.ww_analyzer.reset()

            if self._check_stop():
                break

            # ==================== 终末地模块 ====================
            ef_cost = 0
            if cfg.get("enable_maaend", True):
                ef_cost, state.ef_success = self._run_ef_module(logger, state, ai_client, cfg, program_deadline)
            else:
                logger.log("⏸️ [总控] 终末地功能未启用，跳过执行")
                state.ef_analyzer.reset()

            if self._check_stop():
                break

            # ==================== 异环模块 ====================
            nte_cost = 0
            if cfg.get("enable_oknte", True):
                nte_cost, state.nte_success = self._run_nte_module(logger, state, ai_client, cfg, program_deadline)
            else:
                logger.log("⏸️ [总控] 异环功能未启用，跳过执行")
                state.nte_analyzer.reset()

            last_ww_success = state.ww_success
            last_ef_success = state.ef_success
            last_ww_cost = ww_cost
            last_ef_cost = ef_cost

            if self._check_stop():
                break

            logger.log(f"📊 第 {round_num} 轮结果: 鸣潮{'✅' if state.ww_success else '❌'} | 终末地{'✅' if state.ef_success else '❌'} | 异环{'✅' if state.nte_success else '❌'}")
            logger.log(f"   耗时: 鸣潮{ww_cost / 60:.1f}分钟, 终末地{ef_cost / 60:.1f}分钟, 异环{nte_cost / 60:.1f}分钟")

            # 钉钉战报
            if self._check_stop():
                break
            send_detailed_dingtalk_report([], cfg, state, logger)

            if round_num == total_rounds:
                break

            logger.log(f"⏳ 第 {round_num} 轮完成，等待 {round_interval // 60} 分钟后开始下一轮...")
            remain = round_interval
            while remain > 0:
                if self._check_stop():
                    break
                if time.time() > program_deadline:
                    force_shutdown(cfg, logger, "等待间隔期间全局超时")
                self._sleep(min(10, remain))
                remain -= 10

            logger.log("🧹 两轮之间执行深度清理...")
            smart_cleanup(
                cfg, logger,
                ["ok-ww.exe", "MaaEnd.exe", "Wuthering Waves.exe", "Endfield.exe"],
                ["鸣潮", "终末地", "ok-ww", "maaend"],
            )
            self._sleep(10)

        # 汇总告警
        if not self._check_stop():
            alarms = history_manager.update_and_check(
                last_ww_success, last_ef_success, last_ww_cost, last_ef_cost,
                ww_enabled=cfg.get("enable_okww", True),
                ef_enabled=cfg.get("enable_maaend", True),
            )
            if alarms:
                send_dingtalk_message("\n".join(alarms), cfg, title="自动化监控告警", is_urgent=True)

        if not self._check_stop():
            logger.archive_original_logs()

        self._notify_status("finished")

        if not self._check_stop():
            auto_shutdown(cfg, logger)

        with self._lock:
            self._is_running = False