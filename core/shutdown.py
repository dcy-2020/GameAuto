"""自动关机模块"""
import subprocess
import sys
import ctypes
from ctypes import wintypes


def ask_shutdown_confirmation(config: dict, logger) -> bool:
    MessageBoxTimeoutW = ctypes.windll.user32.MessageBoxTimeoutW
    MessageBoxTimeoutW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   ctypes.c_uint, wintypes.WORD, ctypes.c_int)
    MessageBoxTimeoutW.restype = ctypes.c_int
    result = MessageBoxTimeoutW(
        None,
        f"所有游戏日常任务已完成。是否立即关机？\n\n若不操作，{config.get('shutdown_timeout_seconds', 30)}秒后将自动关机。",
        "自动关机确认",
        0x24,
        0,
        int(config.get("shutdown_timeout_seconds", 30) * 1000)
    )
    if result == 7:
        logger.log("用户点击【否】，取消关机")
        return False
    else:
        if result == 6:
            logger.log("用户点击【是】，准备关机")
        elif result == 32000:
            logger.log("超时无操作，自动关机")
        else:
            logger.log(f"返回值异常({result})，强制关机")
        return True


def auto_shutdown(config: dict, logger):
    if not config.get("auto_shutdown", False):
        return
    logger.log("🔔 所有任务已完成，准备触发关机确认...")
    if ask_shutdown_confirmation(config, logger):
        logger.log("🔌 执行自动关机...")
        subprocess.run(["shutdown", "/s", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        logger.log("🚫 用户取消关机，继续运行")


def cancel_shutdown():
    subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)


def force_shutdown(config: dict, logger, reason: str = ""):
    if reason:
        logger.log(f"⏰ {reason}，正在强制关机...")
    else:
        logger.log("🔌 强制关机...")
    cancel_shutdown()
    subprocess.run(["shutdown", "/s", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)