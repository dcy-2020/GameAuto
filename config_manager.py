"""配置管理器 - JSON 配置文件的加载、保存和验证"""
import json
import os
import copy

# 默认配置模板
DEFAULT_CONFIG = {
    # ===== 路径配置 =====
    "okww_path": "",
    "okww_exe": "",
    "okww_log_dir": "",
    "maaend_path": "",
    "maaend_exe": "",
    "maaend_log_dir": "",
    "ww_game_exe": "",
    "ef_game_exe": "",

    # ===== 异环配置 =====
    "oknte_path": "",
    "oknte_exe": "",
    "oknte_log_dir": "",
    "nte_max_retries": 2,
    "enable_oknte": True,

    # ===== 启用开关 =====
    "enable_okww": True,
    "enable_maaend": True,

    # ===== 账号配置 =====
    "okww_total_accounts": 1,
    "okww_expected_accounts": [],
    "okww_run_mode": 1,

    # ===== 重试配置 =====
    "ww_max_retries": 2,
    "ef_max_retries": 2,

    # ===== 时间配置 =====
    "watchdog_interval": 5,
    "log_timeout": 600,
    "retry_wait": 20,
    "global_task_timeout": 3600,
    "max_program_runtime": 10800,
    "boot_max_wait": 600,
    "cleanup_wait_first": 5,
    "cleanup_wait_check": 3,
    "window_activate_wait": 2,
    "process_start_wait": 8,

    # ===== 自动关机配置 =====
    "auto_shutdown": False,
    "shutdown_timeout_seconds": 30,

    # ===== 计划任务配置 =====
    "schedule_enabled": False,
    "schedule_time": "09:40",
    "schedule_task_name": "GameAutoDaily",

    # ===== 日志保存路径 =====
    "report_log_path": "",

    # ===== WiFi 配置 =====
    "wifi_primary": "",
    "wifi_backup": "",

    # ===== 钉钉配置 =====
    "dingtalk_webhook": "",
    "dingtalk_secret": "",
    "dingtalk_at_mobiles": [],
    "send_detailed_dingtalk": False,
    "dingtalk_max_message_length": 18000,

    # ===== 轮次配置 =====
    "round_interval": 600,
    "total_rounds": 1,

    # ===== AI 配置 =====
    "enable_ai_assist": False,
    "dashscope_api_key": "",
    "ai_model": "qwen3-vl-flash",
    "ai_trigger_timeout": 30,
    "ai_max_attempts": 10,
    "ai_click_confidence": 0.7,
}

# 配置描述（供 GUI 显示提示和分组）
CONFIG_HELP = {
    "okww_path": ("鸣潮 - 脚本目录", "ok-ww 的安装目录路径"),
    "okww_exe": ("鸣潮 - 可执行文件", "ok-ww.exe 的完整路径"),
    "okww_log_dir": ("鸣潮 - 日志目录", "ok-ww 日志输出目录"),
    "maaend_path": ("终末地 - 脚本目录", "MaaEnd 的安装目录路径"),
    "maaend_exe": ("终末地 - 可执行文件", "MaaEnd.exe 的完整路径"),
    "maaend_log_dir": ("终末地 - 日志目录", "MaaEnd 日志输出目录"),
    "ww_game_exe": ("鸣潮 - 游戏本体", "Wuthering Waves.exe 的完整路径"),
    "ef_game_exe": ("终末地 - 游戏本体", "Endfield.exe 的完整路径"),
    "oknte_path": ("异环 - 脚本目录", "ok-nte 的安装目录路径"),
    "oknte_exe": ("异环 - 可执行文件", "ok-nte.exe 的完整路径"),
    "oknte_log_dir": ("异环 - 日志目录", "ok-nte 日志输出目录"),
    "nte_max_retries": ("异环 - 最大重试", "异环任务失败后最大重试次数"),
    "enable_oknte": ("异环 - 启用", "是否执行异环日常任务"),
    "enable_okww": ("鸣潮 - 启用", "是否执行鸣潮日常任务"),
    "enable_maaend": ("终末地 - 启用", "是否执行终末地日常任务"),
    "okww_total_accounts": ("鸣潮 - 账号总数", "预期处理的账号数量"),
    "okww_expected_accounts": ("鸣潮 - 账号列表", "账号尾号列表，如 [\"7267\", \"8071\"]"),
    "okww_run_mode": ("鸣潮 - 运行模式", "1=单账号, 2=多账号"),
    "ww_max_retries": ("鸣潮 - 最大重试", "单个任务最大重试次数"),
    "ef_max_retries": ("终末地 - 最大重试", "单个任务最大重试次数"),
    "watchdog_interval": ("看门狗 - 检查间隔(秒)", "看门狗轮询日志间隔"),
    "log_timeout": ("超时 - 日志超时(秒)", "日志无更新时的超时判断"),
    "retry_wait": ("重试 - 等待时间(秒)", "重试之间的等待时间"),
    "global_task_timeout": ("超时 - 单个任务超时(秒)", "单个任务最大允许运行时间"),
    "max_program_runtime": ("超时 - 程序总运行时间(秒)", "程序从启动到强制结束的最大总时间，默认10800秒(3小时)"),
    "boot_max_wait": ("开机 - 最大等待(秒)", "等待系统就绪的最长时间"),
    "cleanup_wait_first": ("清理 - 首轮等待(秒)", "进程清理后首轮等待时间"),
    "cleanup_wait_check": ("清理 - 复查等待(秒)", "进程清理复查等待时间"),
    "window_activate_wait": ("窗口 - 激活缓冲(秒)", "窗口激活后的缓冲时间"),
    "process_start_wait": ("进程 - 启动等待(秒)", "进程启动后的缓冲时间"),
    "auto_shutdown": ("关机 - 自动关机", "任务完成后是否自动关机"),
    "shutdown_timeout_seconds": ("关机 - 确认超时(秒)", "关机确认弹窗超时秒数"),
    "schedule_enabled": ("计划任务 - 启用", "是否创建 Windows 每日定时任务"),
    "schedule_time": ("计划任务 - 执行时间", "每日自动运行的时间，格式 HH:MM"),
    "schedule_task_name": ("计划任务 - 任务名", "Windows 任务计划程序中的任务名称"),
    "report_log_path": ("日志 - 报告保存路径", "运行报告日志保存目录"),
    "wifi_primary": ("网络 - 主WiFi", "首选WiFi SSID"),
    "wifi_backup": ("网络 - 备用WiFi", "备用WiFi SSID"),
    "dingtalk_webhook": ("钉钉 - Webhook URL", "钉钉机器人 Webhook 地址"),
    "dingtalk_secret": ("钉钉 - Secret", "钉钉机器人加签密钥"),
    "dingtalk_at_mobiles": ("钉钉 - @手机号", "紧急告警时 @ 的手机号列表"),
    "send_detailed_dingtalk": ("钉钉 - 详细报告", "是否发送结构化执行报告"),
    "dingtalk_max_message_length": ("钉钉 - 消息长度上限", "钉钉消息最大字符数"),
    "round_interval": ("轮次 - 间隔(秒)", "多轮执行时的间隔时间"),
    "total_rounds": ("轮次 - 总轮数", "总共执行的轮数"),
    "enable_ai_assist": ("AI - 启用", "是否启用 AI 辅助异常处理"),
    "dashscope_api_key": ("AI - API Key", "阿里云 DashScope API Key"),
    "ai_model": ("AI - 模型", "多模态模型名称"),
    "ai_trigger_timeout": ("AI - 触发超时(秒)", "日志静默多久触发AI检查"),
    "ai_max_attempts": ("AI - 最大尝试", "每轮任务最多AI干预次数"),
    "ai_click_confidence": ("AI - 点击置信度", "保留参数，暂未使用"),
}

# 配置分组（对应 GUI Tab）
CONFIG_GROUPS = {
    "general": {
        "label": "总设置",
        "keys": [
            "report_log_path", "auto_shutdown", "shutdown_timeout_seconds",
            "schedule_enabled", "schedule_time", "schedule_task_name",
            "total_rounds", "round_interval", "watchdog_interval",
            "log_timeout", "global_task_timeout", "max_program_runtime",
            "retry_wait", "boot_max_wait", "cleanup_wait_first",
            "cleanup_wait_check", "window_activate_wait", "process_start_wait",
        ],
    },
    "okww": {
        "label": "鸣潮",
        "keys": [
            "enable_okww", "okww_path", "okww_exe", "okww_log_dir",
            "ww_game_exe", "okww_run_mode", "okww_total_accounts",
            "okww_expected_accounts", "ww_max_retries",
        ],
    },
    "maaend": {
        "label": "终末地",
        "keys": [
            "enable_maaend", "maaend_path", "maaend_exe", "maaend_log_dir",
            "ef_game_exe", "ef_max_retries",
        ],
    },
    "oknte": {
        "label": "异环",
        "keys": [
            "enable_oknte", "oknte_path", "oknte_exe", "oknte_log_dir",
            "nte_max_retries",
        ],
    },
    "dingtalk": {
        "label": "钉钉",
        "keys": [
            "dingtalk_webhook", "dingtalk_secret", "send_detailed_dingtalk",
            "dingtalk_at_mobiles", "dingtalk_max_message_length",
        ],
    },
    "ai": {
        "label": "AI",
        "keys": [
            "enable_ai_assist", "dashscope_api_key", "ai_model",
            "ai_trigger_timeout", "ai_max_attempts", "ai_click_confidence",
        ],
    },
    "network": {
        "label": "网络",
        "keys": [
            "wifi_primary", "wifi_backup",
        ],
    },
}


def get_config_path():
    """获取 config.json 的路径（可写位置：exe 旁边或脚本目录）"""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：config.json 放在 exe 同级目录（可写）
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    else:
        # 源码运行：放在项目根目录
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _get_default_config_path():
    """获取 default_config.json 模板路径（兼容源码和打包后）"""
    import sys
    if getattr(sys, 'frozen', False):
        # 打包后从 _MEIPASS 读取
        return os.path.join(sys._MEIPASS, "resources", "default_config.json")
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "resources", "default_config.json")


def load_config() -> dict:
    """加载配置：优先 config.json，不存在时从 default_config.json 复制。
    始终与 DEFAULT_CONFIG 合并，确保新增的 key 不会缺失。"""
    config_path = get_config_path()

    # 1) 首选用户 config.json
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            # 合并缺失的默认值（新增 key 自动补上）
            config = copy.deepcopy(DEFAULT_CONFIG)
            config.update(user_config)
            return config
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ 配置文件损坏 ({e})，使用默认配置")

    # 2) 从出厂模板复制
    default_config_path = _get_default_config_path()
    if os.path.exists(default_config_path):
        try:
            with open(default_config_path, 'r', encoding='utf-8') as f:
                template = json.load(f)
            # 始终合并 DEFAULT_CONFIG，保证新增 key 不丢
            config = copy.deepcopy(DEFAULT_CONFIG)
            config.update(template)
            save_config(config)
            return config
        except (json.JSONDecodeError, IOError):
            pass

    # 3) 最终兜底
    config = copy.deepcopy(DEFAULT_CONFIG)
    save_config(config)
    return config


def save_config(config: dict) -> bool:
    """保存配置到 config.json"""
    config_path = get_config_path()
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"❌ 保存配置失败: {e}")
        return False


def validate_config(config: dict) -> list:
    """验证配置，返回错误列表（空列表表示无错误）"""
    errors = []
    cfg = config

    # 检查启用模块的路径
    if cfg.get("enable_okww", True):
        if not cfg.get("okww_exe"):
            errors.append("鸣潮已启用但未设置 okww_exe 路径")
        if not cfg.get("okww_path"):
            errors.append("鸣潮已启用但未设置 okww_path 路径")

    if cfg.get("enable_maaend", True):
        if not cfg.get("maaend_exe"):
            errors.append("终末地已启用但未设置 maaend_exe 路径")
        if not cfg.get("maaend_path"):
            errors.append("终末地已启用但未设置 maaend_path 路径")

    if cfg.get("enable_oknte", True):
        if not cfg.get("oknte_exe"):
            errors.append("异环已启用但未设置 oknte_exe 路径")
        if not cfg.get("oknte_path"):
            errors.append("异环已启用但未设置 oknte_path 路径")

    # 检查账号配置
    if cfg.get("enable_okww", True) and not cfg.get("okww_expected_accounts"):
        errors.append("鸣潮已启用但未配置 okww_expected_accounts 账号列表")

    return errors
