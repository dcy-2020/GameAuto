"""GameAuto Daily - 游戏日常自动化工具 入口文件

启动时自动申请管理员权限，初始化配置，然后启动 GUI。
支持 --auto 参数（计划任务触发时自动执行，无需人工操作）。
"""
import sys
import os
import ctypes

# 必须在任何 GUI / 截图操作前调用
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# 强制初始化 numpy+opencv，确保 pyautogui 后续能正常使用 confidence 参数
try:
    import numpy
    import cv2
except Exception:
    pass


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin(extra_args: str = ""):
    """以管理员权限重新启动当前脚本，可附加命令行参数"""
    if is_admin():
        return
    try:
        script = os.path.abspath(sys.argv[0])
        if getattr(sys, 'frozen', False):
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", script, extra_args, None, 1
            )
        else:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {extra_args}'.strip(), None, 1
            )
        sys.exit(0)
    except Exception:
        sys.exit(1)


def _is_auto_mode() -> bool:
    """检查是否以 --auto 模式启动"""
    return "--auto" in sys.argv


def run_headless(config: dict):
    """无 GUI 模式：直接执行全部已启用的任务，完成后退出。

    用于计划任务自动触发，流程与 GUI 点击「开始执行」一致。
    """
    import time
    from datetime import datetime

    # 日志直接输出到控制台 + 文件
    from core.logger import ReportLogger
    logger = ReportLogger(config["report_log_path"], config)
    logger.print("=" * 50)
    logger.print(f"  🤖 GameAuto Daily (自动模式) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.print("=" * 50)

    # 环境检查
    if not config.get("enable_okww") and not config.get("enable_maaend") and not config.get("enable_oknte"):
        logger.log("❌ 所有游戏模块均未启用，无需执行", level="ERROR")
        return

    from core.task_runner import TaskRunner

    runner = TaskRunner(config=config)
    runner.start()

    # 等待任务完成
    try:
        while runner.is_running():
            time.sleep(2)
    except KeyboardInterrupt:
        logger.log("⚠️ 用户中断", level="WARN")
        runner.stop()

    logger.log("🏁 自动模式执行完毕")
    # 自动关机会在 TaskRunner 内部处理


def main():
    """主入口：管理员提权 → 根据 --auto 参数分支"""
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(script_dir)

    auto_mode = _is_auto_mode()

    # 管理员提权（传递 --auto 参数）
    if not is_admin():
        run_as_admin("--auto" if auto_mode else "")
        return

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # 加载配置
    from config_manager import load_config
    config = load_config()

    # 确保日志目录存在
    report_log_path = config.get("report_log_path", "")
    if report_log_path:
        try:
            os.makedirs(report_log_path, exist_ok=True)
        except Exception:
            pass

    # 根据模式分支
    if auto_mode:
        run_headless(config)
    else:
        from gui import launch_gui
        launch_gui(config)


if __name__ == "__main__":
    main()
