"""日志分析器模块 - 解析各游戏自动化框架的运行日志"""
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Set


class TaskStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class TimelineEvent:
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    detail: str = ""


@dataclass
class TaskResult:
    status: TaskStatus
    progress: int
    total: int
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)

    def get_timeline_report(self) -> str:
        report = []
        for event in self.timeline:
            if event.end_time and event.start_time:
                cost = f"{(event.end_time - event.start_time):.1f}s"
                finish_time_str = datetime.fromtimestamp(event.end_time).strftime("%H:%M:%S")
            else:
                cost = "进行中"
                finish_time_str = "---"
            status_icon = "✅" if event.status == "success" else "❌" if event.status == "failed" else "⏳"
            report.append(f"- {status_icon} `[{finish_time_str}]` **{event.name}** (耗时 {cost}) {event.detail}")
        return "\n".join(report) if report else "- 暂无详细流程数据"


class BaseLogAnalyzer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.status = TaskStatus.UNKNOWN
        self.progress = 0
        self.total = 0
        self.error_message = ""
        self.warnings = []
        self.timeline: List[TimelineEvent] = []
        self._current_event: Optional[TimelineEvent] = None
        self.file_states: Dict[str, dict] = {}
        self.last_log_time = time.time()
        self._ai_attempt_count = 0

    def seek_to_end(self, log_path: str):
        if not log_path or not os.path.exists(log_path):
            return
        state = self.file_states.setdefault(log_path, {"pos": 0})
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                state["pos"] = f.tell()
            self.last_log_time = time.time()
        except Exception:
            pass

    def start_event(self, name: str, timestamp: float):
        if self._current_event and self._current_event.name == name and self._current_event.status == "running":
            return
        if self._current_event and self._current_event.status == "running":
            self.finish_event("success", "", timestamp)
        self._current_event = TimelineEvent(name=name, start_time=timestamp)
        self.timeline.append(self._current_event)

    def finish_event(self, status: str, detail: str, timestamp: float):
        if self._current_event and self._current_event.status == "running":
            self._current_event.status = status
            self._current_event.end_time = timestamp
            if detail:
                self._current_event.detail = detail

    def set_event_detail(self, detail: str):
        if self._current_event and self._current_event.status == "running":
            self._current_event.detail = detail

    def parse_time(self, line: str) -> Optional[float]:
        match = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            except:
                pass
        return None

    def is_ai_trigger_timeout(self, config: dict) -> bool:
        return (time.time() - self.last_log_time) >= config.get("ai_trigger_timeout", 30)

    def is_log_timeout(self, config: dict) -> bool:
        return (time.time() - self.last_log_time) >= config["log_timeout"]

    def _read_new_lines(self, log_path: str) -> List[str]:
        if not log_path or not os.path.exists(log_path):
            return []
        state = self.file_states.setdefault(log_path, {"pos": 0})
        try:
            current_size = os.path.getsize(log_path)
            if current_size < state["pos"]:
                state["pos"] = 0
            if current_size > state["pos"]:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(state["pos"])
                    lines = f.readlines()
                    state["pos"] = f.tell()
                if lines:
                    self.last_log_time = time.time()
                    return [line.strip() for line in lines if line.strip()]
        except Exception:
            pass
        return []


# ==================== MaaEnd 分析器 ====================
def get_latest_maaend_log(log_dir: str) -> Optional[str]:
    if not os.path.exists(log_dir):
        return None
    today_str = datetime.now().strftime("%Y-%m-%d")
    candidates = []
    fallback_candidates = []
    for fname in os.listdir(log_dir):
        if fname.endswith(".log") and fname != "maafw.log":
            full_path = os.path.join(log_dir, fname)
            try:
                mtime = os.path.getmtime(full_path)
                if today_str in fname:
                    candidates.append((mtime, full_path))
                else:
                    fallback_candidates.append((mtime, full_path))
            except Exception:
                pass
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    if fallback_candidates:
        fallback_candidates.sort(reverse=True)
        return fallback_candidates[0][1]
    return None


class MaaEndLogAnalyzer(BaseLogAnalyzer):
    ENTRY_MAPPING = {
        "VisitFriendsMain": "拜访好友",
        "DijiangRewards": "基建任务",
        "DeliveryJobsMain": "转交委托",
        "AutoStockpileMain": "自动囤货",
        "SellProductMain": "售卖产品",
        "AutoStockStapleMain": "购买稳定物资",
        "CreditShoppingMain": "信用点购物",
        "DailyRewardStart": "领取邮件及日常奖励",
        "ProtocolSpaceEntry": "协议空间",
        "MXU_KILLPROC": "执行结束与游戏清理"
    }

    def reset(self):
        super().reset()
        self.task_dict: Dict[int, str] = {}
        self.ordered_tasks: List[str] = []
        self.is_started = False

    def analyze(self, process_running: bool, log_dir: str) -> TaskResult:
        app_log_path = get_latest_maaend_log(log_dir)
        if not app_log_path and not process_running:
            self.status = TaskStatus.FAILED
            self.error_message = "未找到运行日志"
            return self._build_result()

        # 如果日志文件变了（MaaEnd 每次运行新文件），重置 seek 位置
        if app_log_path and app_log_path not in self.file_states:
            old_states = list(self.file_states.keys())
            for old in old_states:
                self.file_states.pop(old)
            self.seek_to_end(app_log_path)
            self.last_log_time = time.time()

        app_lines = self._read_new_lines(app_log_path)
        if app_lines:
            self._process_lines(app_lines)
        # MaaEnd 完成后进程自动退出，此时如果 status 被 tasks-completed 置为 SUCCESS 则没问题
        if not process_running and self.status == TaskStatus.RUNNING:
            # 再查一下是不是有更早的成功标记被漏掉了
            if app_log_path:
                try:
                    with open(app_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        full = f.read()
                    if any(kw in full for kw in ["kind: tasks-completed", "成功", "自动执行任务完成"]):
                        self.status = TaskStatus.SUCCESS
                        return self._build_result()
                except Exception:
                    pass
            self.status = TaskStatus.FAILED
            self.finish_event("failed", "进程意外终止", time.time())
            if not self.error_message:
                self.error_message = "MaaEnd 进程中途崩溃"
        return self._build_result()

    def _process_lines(self, lines: List[str]):
        for line in lines:
            line_time = self.parse_time(line) or time.time()
            if any(err in line.lower() for err in ["connection error", "timeout", "网络异常"]):
                self.warnings.append(f"网络报错(已忽略): {line[-50:]}")
                continue
            task_match = re.search(r"任务\[(\d+)\]:\s*entry=([a-zA-Z0-9_]+)", line)
            if task_match:
                idx = int(task_match.group(1))
                raw_entry = task_match.group(2)
                self.task_dict[idx] = self.ENTRY_MAPPING.get(raw_entry, raw_entry)
                continue
            if "开始执行任务, 数量:" in line:
                self.is_started = False
                self.total = int(re.search(r"数量: (\d+)", line).group(1))
                self.progress = 0
                self.status = TaskStatus.RUNNING
                self.error_message = ""
                continue
            if "kind: task-started" in line:
                if not self.is_started:
                    self.is_started = True
                    self.ordered_tasks = [self.task_dict[k] for k in sorted(self.task_dict.keys())]
                    if self.progress < len(self.ordered_tasks):
                        self.start_event(f"执行: {self.ordered_tasks[self.progress]}", line_time)
                continue
            if "kind: task-progress" in line:
                if not self.is_started:
                    continue
                self.finish_event("success", "", line_time)
                self.progress += 1
                if self.progress < len(self.ordered_tasks):
                    self.start_event(f"执行: {self.ordered_tasks[self.progress]}", line_time)
                continue
            if "kind: tasks-completed" in line or "自动执行任务完成" in line or "Successfully" in line:
                self.finish_event("success", "", line_time)
                self.status = TaskStatus.SUCCESS
                self.progress = self.total
                continue
            if "ERROR" in line or "任务启动异常" in line:
                if self.status != TaskStatus.SUCCESS:
                    self.status = TaskStatus.FAILED
                    err_msg = line.split("ERROR")[-1].strip() if "ERROR" in line else line.strip()
                    self.error_message = err_msg
                    self.finish_event("failed", "异常中断", line_time)

    def _build_result(self):
        return TaskResult(status=self.status, progress=self.progress,
                          total=self.total if self.total > 0 else 10,
                          error_message=self.error_message, warnings=self.warnings,
                          timeline=self.timeline)


# ==================== Ok-WW 分析器 ====================
def get_latest_okww_log(log_dir: str) -> Optional[str]:
    log_file = os.path.join(log_dir, "ok-script.log")
    return log_file if os.path.exists(log_file) else None


class OkWwLogAnalyzer(BaseLogAnalyzer):
    def __init__(self, expected_accounts: List[str] = None, run_mode: int = 1, config: dict = None, logger=None):
        self.expected_accounts = expected_accounts or []
        self.run_mode = run_mode
        self.config = config or {}
        self.logger = logger
        super().__init__()

    def reset(self):
        super().reset()
        self.total = len(self.expected_accounts) if self.expected_accounts else 3
        self.completed_accounts: Set[str] = set()
        self.attempted_accounts: Set[str] = set()
        self.current_account = "首发账号"
        self.account_order: List[str] = []

    def reset_for_new_run(self):
        self.status = TaskStatus.RUNNING
        self.error_message = ""

    def extract_acc_4_digits(self, text: str) -> str:
        match = re.search(r'(\d{4})$', text.strip())
        return match.group(1) if match else text.strip()

    def retroactively_update_account(self, real_account: str):
        if self.current_account in ["首发账号", "单账号"]:
            self.current_account = real_account
        for event in self.timeline:
            if "[首发账号]" in event.name:
                event.name = event.name.replace("[首发账号]", f"[{real_account}]")
            elif "[单账号]" in event.name:
                event.name = event.name.replace("[单账号]", f"[{real_account}]")
        if real_account not in self.account_order:
            self.account_order.insert(0, real_account)

    def analyze(self, process_running: bool, log_dir: str) -> TaskResult:
        log_path = get_latest_okww_log(log_dir)
        if not log_path and not process_running:
            self.status = TaskStatus.FAILED
            self.error_message = "未找到 ok-ww 运行日志"
            return self._build_result()
        lines = self._read_new_lines(log_path)
        if lines:
            self._process_lines(lines)
        return self._build_result()

    def _process_lines(self, lines: List[str]):
        for line in lines:
            line_time = self.parse_time(line) or time.time()

            if "ERROR" in line and "TaskExecutor" in line:
                ignore_keywords = [
                    "combat check not in combat", "target_enemy failed", "ocr translations error",
                    "got no frame!", "PostMessage error", "clicked liberation but no effect"
                ]
                if any(kw in line for kw in ignore_keywords):
                    continue
                if "capture_by_bitblt exception" in line:
                    self.warnings.append("截图模块闪退(框架已尝试自愈)")
                    if self.logger:
                        self.logger.log("⚠️ 截图模块闪退，框架正尝试自愈恢复...", level="WARN")
                else:
                    err_text = line.split("ERROR")[-1].strip()
                    self.warnings.append(f"未知异常(监控中): {err_text[:40]}")
                    if self.logger:
                        self.logger.log(f"⚠️ 捕获报错: {err_text}", level="WARN")

            if "TaskExecutor:start execute" in line:
                self.status = TaskStatus.RUNNING
                self.start_event(f"[{self.current_account}] 启动引擎与环境初始化", line_time)
                if self.logger:
                    self.logger.log(f"🔍 [WW] 引擎已启动，开始处理{self.current_account}")
            elif "检测到已完成账号：" in line:
                acc_4 = self.extract_acc_4_digits(line.split("检测到已完成账号：")[-1])
                self.retroactively_update_account(acc_4)
                self.completed_accounts.add(acc_4)
            elif "正在选择账号：" in line:
                acc_4 = self.extract_acc_4_digits(line.split("正在选择账号：")[-1])
                self.current_account = acc_4
                self.attempted_accounts.add(acc_4)
                if acc_4 not in self.account_order:
                    self.account_order.append(acc_4)
                self.start_event(f"[{self.current_account}] 切换账号并尝试登录", line_time)
                if self.logger:
                    self.logger.log(f"▶️ [WW] 切换账号: {self.current_account}")
            elif "跳过" in line and "（已完成）" in line:
                match = re.search(r"跳过 (.*?)（已完成）", line)
                if match:
                    acc_4 = self.extract_acc_4_digits(match.group(1))
                    if self.logger:
                        self.logger.log(f"⏩ [WW] 跳过已完成账号: {acc_4}")
                if self.progress < self.total:
                    self.progress += 1
            elif "登录成功" in line:
                if "登录成功：" in line:
                    acc_4 = self.extract_acc_4_digits(line.split("登录成功：")[-1])
                    self.retroactively_update_account(acc_4)
                self.start_event(f"[{self.current_account}] 登录成功，执行大世界检测", line_time)
            elif "Teleport to Tacet Suppression" in line:
                self.start_event(f"[{self.current_account}] 传送并清理体力 (无音区)", line_time)
            elif "used all stamina" in line:
                if self.logger:
                    self.logger.log(f"✅ [WW] {self.current_account} 体力已耗尽")
            elif "current task claim daily" in line:
                self.start_event(f"[{self.current_account}] 领取日常活跃度奖励", line_time)
            elif "battle pass" in line:
                self.start_event(f"[{self.current_account}] 领取电台/纪行奖励", line_time)
            elif "DailyTask:Task completed" in line:
                self.finish_event("success", "", line_time)
                if self.current_account not in ["首发账号", "单账号"]:
                    self.completed_accounts.add(self.current_account)
                if self.progress < self.total:
                    self.progress += 1
                if self.logger:
                    self.logger.log(f"🎉 [WW] 账号 {self.current_account} 日常已完成 ({self.progress}/{self.total})")
            elif "正在返回登录界面" in line:
                self.start_event(f"[{self.current_account}] 结算并返回登录界面", line_time)

            elif "all tasks completed" in line or "所有账号任务完成" in line or "Exit event set" in line or "Successfully Executed Task" in line:
                self.finish_event("success", "", line_time)
                self.status = TaskStatus.SUCCESS

    def _build_result(self):
        if self.run_mode == 2:
            if any("[首发账号]" in e.name for e in self.timeline):
                known_used = self.completed_accounts.union(self.attempted_accounts)
                remaining = set(self.expected_accounts) - known_used
                if len(remaining) == 1:
                    deduced_acc = list(remaining)[0]
                    self.retroactively_update_account(deduced_acc)
                    if self.progress > 0:
                        self.completed_accounts.add(deduced_acc)

            stamina_cleared_accs = set()
            for event in self.timeline:
                if "清理体力" in event.name:
                    match = re.search(r'\[(.*?)\]', event.name)
                    if match:
                        stamina_cleared_accs.add(match.group(1))

            fake_accs = self.completed_accounts - stamina_cleared_accs
            if self.account_order and self.account_order[0] in fake_accs:
                fake_accs.remove(self.account_order[0])

            if fake_accs and self.status == TaskStatus.SUCCESS:
                self.warnings.append(f"智能防卡死: 账号 {', '.join(fake_accs)} 未执行体力清理即结束，判定为切号失败。")
                self.status = TaskStatus.FAILED
                self.error_message = f"疑似切号失败 ({', '.join(fake_accs)})"

            missing = set(self.expected_accounts) - self.completed_accounts
            if missing:
                self.warnings.append(f"智能诊断: 账号 {', '.join(missing)} 未检测到完成标志，可能漏打或切号崩溃。")

        return TaskResult(status=self.status, progress=self.progress, total=self.total,
                          error_message=self.error_message, warnings=self.warnings,
                          timeline=self.timeline)


# ==================== Ok-NTE (异环) 分析器 ====================
def get_latest_oknte_log(log_dir: str) -> Optional[str]:
    log_file = os.path.join(log_dir, "ok-script.log")
    return log_file if os.path.exists(log_file) else None


class OkNteLogAnalyzer(BaseLogAnalyzer):
    def reset(self):
        super().reset()
        self.progress = 0
        self.total = 1

    def analyze(self, log_dir: str) -> TaskResult:
        log_path = get_latest_oknte_log(log_dir)
        if not log_path:
            return self._build_result()
        lines = self._read_new_lines(log_path)
        if lines:
            self._process_lines(lines)
        return self._build_result()

    def _process_lines(self, lines: List[str]):
        for line in lines:
            line_time = self.parse_time(line) or time.time()

            if "TaskExecutor:start execute" in line:
                self.status = TaskStatus.RUNNING
                self.start_event("启动异环引擎与等待加载", line_time)
            elif "开始任务: " in line:
                task_name = line.split("开始任务: ")[-1].split(",")[0].strip()
                self.start_event(f"日常: {task_name}", line_time)
            elif "任务完成: " in line:
                self.finish_event("success", "", line_time)
            elif "正在执行一咖舍自动化" in line:
                self.start_event("一咖舍自动化", line_time)
            elif "一咖舍执行完成" in line:
                self.finish_event("success", "", line_time)
            elif "Successfully Executed Task, Exiting Game and App!" in line:
                self.finish_event("success", "日志判定自然结束", line_time)
                self.status = TaskStatus.SUCCESS
                self.progress = 1
            elif "ERROR TaskExecutor" in line:
                if "target_enemy failed" in line or "combat check not in combat" in line:
                    continue
                err_msg = line.split("ERROR")[-1].strip()
                self.warnings.append(f"运行警告: {err_msg[:30]}")

    def _build_result(self):
        return TaskResult(status=self.status, progress=self.progress, total=self.total,
                          error_message=self.error_message, warnings=self.warnings,
                          timeline=self.timeline)