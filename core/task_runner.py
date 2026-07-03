"""TaskRunner - 后台线程编排游戏日常自动化主流程"""
import os
import sys
import time
import subprocess
import threading

# 导入手柄：兼容源码运行和 PyInstaller 打包后的环境
# 打包后 Python 模块在 PKG 归档中，必须用包名导入；源码运行两种方式都支持
try:
    from Switcher.WwAccountSwitcher import WwAccountSwitcher
except ImportError:
    # 源码运行时如果 Switcher 不是包，通过 sys.path 降级导入
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(_current_dir)
    _switcher_dir = os.path.join(_project_dir, "Switcher")
    if _switcher_dir not in sys.path:
        sys.path.insert(0, _switcher_dir)
    from WwAccountSwitcher import WwAccountSwitcher

# 解析项目根目录（用于定位 Switcher/imgs 等资源）
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后，资源在 _MEIPASS 临时解压目录
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
                return  # 立即退出
            chunk = min(tick, seconds - elapsed)
            time.sleep(chunk)
            elapsed += chunk

    def _log(self, msg: str, level: str = "INFO"):
        if self._log_callback:
            try:
                self._log_callback(msg, level)
            except Exception:
                pass

    def _notify_status(self, status: str):
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception:
                pass

    def _check_stop(self) -> bool:
        return self._should_stop

    def _init_ai_client(self, logger):
        """初始化 AI 辅助模块"""
        if self.config.get("enable_ai_assist", False) and self.config.get("dashscope_api_key"):
            client = AIAssistant(
                api_key=self.config["dashscope_api_key"],
                model=self.config.get("ai_model", "qwen3.6-flash"),
                logger=logger,
            )
            logger.log("🧠 AI辅助模块已初始化")
            return client
        if self.config.get("enable_ai_assist", False):
            logger.log("⚠️ AI未启用：缺少API Key", level="WARN")
        return None

    def _run_ww_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 ok-ww 任务 — 严格按照原 AutoGameDaily.py 逻辑"""
        state.ww_analyzer.reset_for_new_run()
        cfg = self.config

        logger.log("----------------------------------------")
        logger.log(f"⚙️ [WW] 开始第 {retry_count}/{cfg['ww_max_retries']} 次自动化流程")

        ww_keywords = ["ok-ww"]
        smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
        clear_logs(cfg["okww_log_dir"])

        current_okww_log = get_latest_okww_log(cfg["okww_log_dir"])
        if current_okww_log:
            state.ww_analyzer.seek_to_end(current_okww_log)
            logger.log("🔍 [WW] 已屏蔽历史日志，准备捕捉本次运行")
        else:
            logger.log("⚠️ 未找到 ok-ww 日志文件，将从头开始读取", level="WARN")

        run_mode = cfg.get("okww_run_mode", 1)
        logger.log(f"🚀 启动 ok-ww.exe (模式 -t {run_mode})")
        os.chdir(cfg["okww_path"])
        state.current_process = subprocess.Popen(
            [cfg["okww_exe"], "-t", str(run_mode), "-e"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        self._sleep(cfg.get("process_start_wait", 8))
        activate_target_window(["鸣潮", "wuthering", "ok-ww.exe"], cfg)
        logger.log("🐶 看门狗已启动...")

        start_time = time.time()
        state.ww_analyzer._ai_attempt_count = 0

        while True:
            if self._check_stop():
                logger.log("⏹️ [WW] 用户中断")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return False
            self._sleep(cfg["watchdog_interval"])

            # 全局超时
            if time.time() > program_deadline:
                logger.log("⏰ 程序总时长超限，强制结束本任务", level="ERROR")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return False

            if time.time() - start_time > cfg["global_task_timeout"]:
                logger.log("⏰ 全局超时，强制终止", level="ERROR")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return False

            process_running = state.current_process.poll() is None
            result = state.ww_analyzer.analyze(process_running, cfg["okww_log_dir"])

            if result.status == TaskStatus.SUCCESS:
                logger.log("✅ 单次鸣潮清理任务完成")
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return True
            elif result.status == TaskStatus.FAILED:
                if "疑似切号失败" in result.error_message and retry_count == cfg["ww_max_retries"]:
                    logger.log("⚠️ 已达最大重试次数，该账号可能真实无体力，妥协视为成功")
                    state.ww_analyzer.status = TaskStatus.SUCCESS
                    state.ww_analyzer.error_message = ""
                    state.ww_analyzer.finish_event("success", "", time.time())
                    smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                    return True
                logger.log(f"❌ 鸣潮任务失败: {result.error_message}")
                state.ww_analyzer.finish_event("failed", "任务异常失败", time.time())
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return False

            # AI 异常处理 — 使用 is_log_timeout 触发（与原版一致）
            if cfg.get("enable_ai_assist", False) and ai_client is not None:
                if state.ww_analyzer.is_log_timeout(cfg):
                    logger.log("⏳ 日志超时，疑似卡在未知弹窗，尝试AI自救...")
                    if state.ww_analyzer._ai_attempt_count >= cfg.get("ai_max_attempts", 10):
                        logger.log("❌ AI尝试次数已达上限，放弃并执行清理")
                        smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                        return False
                    state.ww_analyzer._ai_attempt_count += 1

                    activate_target_window(["鸣潮", "wuthering"], cfg)
                    self._sleep(0.3)
                    screenshot_b64 = ai_client.capture_screen()

                    if screenshot_b64:
                        context = f"鸣潮日常，账号 {state.ww_analyzer.current_account}，进度 {state.ww_analyzer.progress}/{state.ww_analyzer.total}"
                        action = ai_client.ask_for_action(screenshot_b64, context)
                        if action and ai_client.execute_action(action):
                            state.ww_analyzer.last_log_time = time.time()
                            continue
                        else:
                            logger.log("⚠️ AI无有效动作，继续等待")
                    else:
                        logger.log("⚠️ 截图失败，跳过AI")

            if state.ww_analyzer.is_log_timeout(cfg):
                logger.log("⚠️ 日志超时，且AI未能恢复，执行清理", level="WARN")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["ok-ww.exe"], ww_keywords)
                return False

    def _run_ef_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 MaaEnd 任务 — 严格按照原 AutoGameDaily.py 逻辑"""
        state.ef_analyzer.reset()
        cfg = self.config

        logger.log("----------------------------------------")
        logger.log(f"⚙️ [EF] 开始第 {retry_count}/{cfg['ef_max_retries']} 次自动化流程")

        ef_keywords = ["MaaEnd", "终末地", "endfield"]
        smart_cleanup(cfg, logger, ["MaaEnd.exe", "Endfield.exe", "Endfield-Win64-Shipping.exe"], ef_keywords)
        clear_logs(cfg["maaend_log_dir"])

        logger.log("🚀 启动 MaaEnd.exe")
        os.chdir(cfg["maaend_path"])
        state.current_process = subprocess.Popen(
            [cfg["maaend_exe"], "--autostart", "--instance", "全套日常", "--quit-after-run"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._sleep(cfg.get("process_start_wait", 8))
        logger.log("🐶 看门狗已启动...")

        start_time = time.time()
        while True:
            if self._check_stop():
                logger.log("⏹️ [EF] 用户中断")
                if state.current_process:
                    state.current_process.kill()
                return False
            self._sleep(cfg["watchdog_interval"])

            if time.time() > program_deadline:
                logger.log("⏰ 程序总时长超限，强制结束本任务", level="ERROR")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                return False

            if time.time() - start_time > cfg["global_task_timeout"]:
                logger.log("⏰ 全局超时，强制终止", level="ERROR")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                return False

            process_running = state.current_process.poll() is None
            result = state.ef_analyzer.analyze(process_running, cfg["maaend_log_dir"])

            if result.status == TaskStatus.SUCCESS:
                logger.log("✅ 终末地任务完成")
                state.ef_analyzer.finish_event("success", "", time.time())
                smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                return True
            elif result.status == TaskStatus.FAILED:
                logger.log("❌ 终末地任务失败")
                smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                return False

            # AI 异常处理 — 使用 is_log_timeout 触发（与原版一致）
            if cfg.get("enable_ai_assist", False) and ai_client is not None:
                if state.ef_analyzer.is_log_timeout(cfg):
                    logger.log("⏳ [EF] 日志超时，疑似卡在未知弹窗，尝试AI自救...")
                    if state.ef_analyzer._ai_attempt_count >= cfg.get("ai_max_attempts", 10):
                        logger.log("❌ [EF] AI尝试次数已达上限，放弃并执行清理")
                        if state.current_process:
                            state.current_process.kill()
                        smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                        return False
                    state.ef_analyzer._ai_attempt_count += 1

                    activate_target_window(["终末地", "endfield"], cfg)
                    self._sleep(0.3)
                    screenshot_b64 = ai_client.capture_screen()

                    if screenshot_b64:
                        context = f"终末地日常，当前进度 {state.ef_analyzer.progress}/{state.ef_analyzer.total}"
                        action = ai_client.ask_for_action(screenshot_b64, context)
                        if action and ai_client.execute_action(action):
                            state.ef_analyzer.last_log_time = time.time()
                            continue
                        else:
                            logger.log("⚠️ [EF] AI无有效动作，继续等待")
                    else:
                        logger.log("⚠️ [EF] 截图失败，跳过AI")

            if state.ef_analyzer.is_log_timeout(cfg):
                logger.log("⚠️ [EF] 日志超时，且AI未能恢复，执行清理", level="WARN")
                if state.current_process:
                    state.current_process.kill()
                smart_cleanup(cfg, logger, ["MaaEnd.exe"], ef_keywords)
                return False

    def _run_nte_task(self, logger, state, ai_client, retry_count: int, program_deadline: float) -> bool:
        """单次运行 ok-nte 任务 — 严格按照原 AutoGameDaily.py 逻辑"""
        state.nte_analyzer.reset()
        cfg = self.config

        logger.log("----------------------------------------")
        logger.log(f"⚙️ [NTE] 开始第 {retry_count}/{cfg.get('nte_max_retries', 2)} 次自动化流程")

        nte_keywords = ["ok-nte", "异环", "NTE.exe", "HTGame.exe"]
        smart_cleanup(cfg, logger, ["ok-nte.exe", "NTE.exe"], nte_keywords)
        clear_logs(cfg.get("oknte_log_dir", ""))

        logger.log("🚀 启动 ok-nte.exe (模式 -t 2)")
        os.chdir(cfg["oknte_path"])
        subprocess.Popen(
            [cfg["oknte_exe"], "-t", "2", "-e"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        logger.log("🐶 日志监控看门狗已上线...")
        start_time = time.time()

        while True:
            if self._check_stop():
                logger.log("⏹️ [NTE] 用户中断")
                return False
            self._sleep(cfg["watchdog_interval"])

            result = state.nte_analyzer.analyze(cfg.get("oknte_log_dir", ""))

            if result.status == TaskStatus.SUCCESS:
                logger.log("✅ 在日志中捕捉到退出锚点，异环任务顺利完成！")
                return True
            elif result.status == TaskStatus.FAILED:
                logger.log(f"❌ 异环任务失败: {result.error_message}")
                smart_cleanup(cfg, logger, ["ok-nte.exe", "NTE.exe", "HTGame.exe"], nte_keywords)
                return False

            # AI 异常处理 — 使用 is_log_timeout 触发（与原版一致）
            if cfg.get("enable_ai_assist", False) and ai_client is not None:
                if state.nte_analyzer.is_log_timeout(cfg):
                    logger.log("⏳ [NTE] 日志超时，疑似卡在未知弹窗，尝试AI自救...")
                    if state.nte_analyzer._ai_attempt_count >= cfg.get("ai_max_attempts", 10):
                        logger.log("❌ [NTE] AI尝试次数已达上限，放弃并执行清理")
                        smart_cleanup(cfg, logger, ["ok-nte.exe", "NTE.exe", "HTGame.exe"], nte_keywords)
                        return False
                    state.nte_analyzer._ai_attempt_count += 1

                    activate_target_window(["异环", "NTE.exe"], cfg)
                    self._sleep(0.3)
                    screenshot_b64 = ai_client.capture_screen()

                    if screenshot_b64:
                        context = "异环日常"
                        action = ai_client.ask_for_action(screenshot_b64, context)
                        if action and ai_client.execute_action(action):
                            state.nte_analyzer.last_log_time = time.time()
                            continue
                        else:
                            logger.log("⚠️ [NTE] AI无有效动作，继续等待")
                    else:
                        logger.log("⚠️ [NTE] 截图失败，跳过AI")

            if state.nte_analyzer.is_log_timeout(cfg):
                logger.log(f"⚠️ [NTE] 日志已超过 {cfg.get('log_timeout', 300)} 秒未更新，且AI未能恢复，判定框架卡死", level="WARN")
                smart_cleanup(cfg, logger, ["ok-nte.exe", "NTE.exe", "HTGame.exe"], nte_keywords)
                return False

            if time.time() - start_time > cfg["global_task_timeout"]:
                logger.log("⏰ [NTE] 任务总时长超限，强制终止", level="ERROR")
                smart_cleanup(cfg, logger, ["ok-nte.exe", "NTE.exe", "HTGame.exe"], nte_keywords)
                return False

    def _run_loop(self):
        """主执行循环 - 重构自 AutoGameDaily.main()"""
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
        logger.print(f"  🤖 游戏日常自动化中枢 - {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}")
        logger.print("=" * 40)

        if self._check_stop():
            return

        if not check_boot_environment_ready(cfg, logger):
            logger.log("❌ 环境初始化彻底失败，取消今日自动化任务。")
            send_dingtalk_message("# 🤖 报告:自动化中断报警\n网络自愈失败，无法连接网络，任务已取消。", cfg)
            auto_shutdown(cfg, logger)
            return

        program_start = time.time()
        MAX_PROGRAM_RUNTIME = 10800  # 3小时
        program_deadline = program_start + MAX_PROGRAM_RUNTIME

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
            if cfg.get("enable_okww", True):
                ww_start = time.time()
                state.ww_analyzer.reset()

                # 使用 Switcher 图片目录（相对于 Switcher 模块）
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

                # 清理
                if all_ww_success:
                    state.ww_analyzer.status = TaskStatus.SUCCESS
                    state.ww_analyzer.start_event("执行游戏清理与结束", time.time())
                    logger.log("🧹 [总控] 鸣潮全账号流水线执行完毕，正在关闭游戏客户端释放资源...")
                    smart_cleanup(
                        cfg, logger,
                        ["ok-ww.exe", "Wuthering Waves.exe", "Client-Win64-Shipping.exe"],
                        ["鸣潮", "wuthering", "ok-ww"],
                    )
                    self._sleep(8)
                    state.ww_analyzer.finish_event("success", "", time.time())
                else:
                    state.ww_analyzer.status = TaskStatus.FAILED
                    logger.log("🧹 [总控] 鸣潮全账号流水线执行完毕，正在关闭游戏客户端释放资源...")
                    smart_cleanup(
                        cfg, logger,
                        ["ok-ww.exe", "Wuthering Waves.exe", "Client-Win64-Shipping.exe"],
                        ["鸣潮", "wuthering", "ok-ww"],
                    )
                    self._sleep(8)

                state.ww_success = all_ww_success
                ww_cost = time.time() - ww_start
            else:
                logger.log("⏸️ [总控] 鸣潮功能未启用，跳过执行")
                ww_cost = 0
                state.ww_success = False
                state.ww_analyzer.reset()

            # 检查停止信号
            if self._check_stop():
                break

            # ==================== 终末地模块 ====================
            if cfg.get("enable_maaend", True):
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
                ef_cost = time.time() - ef_start
            else:
                logger.log("⏸️ [总控] 终末地功能未启用，跳过执行")
                ef_cost = 0
                state.ef_success = False
                state.ef_analyzer.reset()

            # 检查停止信号
            if self._check_stop():
                break

            # ==================== 异环模块 ====================
            if cfg.get("enable_oknte", True):
                nte_start = time.time()
                for retry in range(1, cfg.get("nte_max_retries", 2) + 1):
                    if self._check_stop():
                        break
                    state.nte_success = self._run_nte_task(logger, state, ai_client, retry, program_deadline)
                    if state.nte_success:
                        break
                    if time.time() > program_deadline:
                        force_shutdown(cfg, logger, "全局超时")
                    if retry < cfg.get("nte_max_retries", 2):
                        logger.log(f"[WARN] 🔄 休息{cfg['retry_wait']}秒后重试...")
                        self._sleep(cfg["retry_wait"])
                nte_cost = time.time() - nte_start
            else:
                logger.log("⏸️ [总控] 异环功能未启用，跳过执行")
                state.nte_success = False
                nte_cost = 0
                state.nte_analyzer.reset()

            last_ww_success = state.ww_success
            last_ef_success = state.ef_success
            last_ww_cost = ww_cost
            last_ef_cost = ef_cost

            if self._check_stop():
                break

            logger.log(f"📊 第 {round_num} 轮结果: 鸣潮{'✅' if state.ww_success else '❌'} | 终末地{'✅' if state.ef_success else '❌'} | 异环{'✅' if state.nte_success else '❌'}")
            logger.log(f"   耗时: 鸣潮{ww_cost / 60:.1f}分钟, 终末地{ef_cost / 60:.1f}分钟, 异环{nte_cost / 60:.1f}分钟")

            # 钉钉战报（检查停止信号，避免用户中断后还发报告）
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

        # 汇总告警（检查停止信号）
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
