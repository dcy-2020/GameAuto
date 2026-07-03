"""窗口与进程工具模块"""
import ctypes
import os
import time
from ctypes import wintypes
from typing import List, Optional


def iter_windows_by_title(keywords: List[str]):
    """共享的窗口枚举生成器，yield (hwnd, title, pid) 元组"""
    try:
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
        results = []
        def foreach_window(hwnd, lParam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    if any(kw.lower() in title for kw in keywords):
                        pid = wintypes.DWORD()
                        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        results.append((hwnd, title, pid.value))
            return True
        EnumWindows(EnumWindowsProc(foreach_window), 0)
        return results
    except Exception:
        return []


def set_window_foreground(hwnd, config: dict):
    if not hwnd:
        return False
    try:
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SetFocus(hwnd)
        time.sleep(config.get("window_activate_wait", 2))
        return True
    except:
        return False


def activate_target_window(title_keywords: List[str], config: dict) -> bool:
    windows = iter_windows_by_title(title_keywords)
    if windows:
        set_window_foreground(windows[0][0], config)
        return True
    return False


def ensure_esc_menu(config: dict, logger, switcher=None, ai_client=None, max_ai_attempts=10):
    """使用 AI 确保游戏处于大世界的 ESC 菜单界面"""
    if ai_client is None:
        if switcher is None:
            logger.log("⚠️ 无 AI 也无 switcher，无法确认 ESC 菜单")
            return True
        for _ in range(max_ai_attempts):
            activate_target_window(["鸣潮", "wuthering"], config)
            import pydirectinput
            pydirectinput.keyDown('esc')
            time.sleep(0.1)
            pydirectinput.keyUp('esc')
            time.sleep(2)
            if switcher.is_on_esc_menu():
                return True
        logger.log("❌ 无 AI 时多次尝试未能进入 ESC 菜单")
        return False

    for i in range(max_ai_attempts):
        activate_target_window(["鸣潮", "wuthering"], config)
        time.sleep(0.5)
        import pydirectinput
        pydirectinput.keyDown('esc')
        time.sleep(0.1)
        pydirectinput.keyUp('esc')
        time.sleep(2)

        screenshot_b64 = ai_client.capture_screen()
        if not screenshot_b64:
            continue

        context = (
            '游戏鸣潮，当前屏幕是否显示了ESC菜单？该菜单通常包含'
            '"退出登录"、"返回登录"、"设置"等按钮。'
            '如果是，请返回 {"action": "skip"}。'
            '如果不是（例如在弹窗、加载画面、其他界面），请判断需要如何操作才能回到ESC菜单，'
            '例如点击关闭按钮、按ESC键、或点击空白区域关闭弹窗，并返回对应的点击坐标或按键。'
        )
        action = ai_client.ask_for_action(screenshot_b64, context)

        if action:
            if action.get("action") == "skip":
                if switcher and not switcher.is_on_esc_menu():
                    logger.log("🧠 AI 判断为 ESC 但未检测到退出按钮，可能是误判，继续尝试...")
                    continue
                logger.log("✅ AI 确认已处于 ESC 菜单界面")
                return True
            else:
                ai_client.execute_action(action)
                time.sleep(2)
        else:
            logger.log("⚠️ AI 无有效返回，重新尝试")

    logger.log("❌ AI 多次尝试未能进入 ESC 菜单")
    return False


import psutil


def smart_cleanup(config: dict, logger, exe_names: List[str], title_keywords: List[str]):
    logger.log("🧹 智能清场：正在执行全量进程与窗口清理")
    killed_pids = set()

    try:
        for hwnd, title, pid in iter_windows_by_title(title_keywords):
            if pid > 0 and pid not in killed_pids:
                killed_pids.add(pid)
                try:
                    p = psutil.Process(pid)
                    for child in p.children(recursive=True):
                        child.kill()
                        killed_pids.add(child.pid)
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception as e:
        logger.log(f"⚠️ 窗口清理异常: {e}", level="WARN")

    def kill_by_exe(name: str):
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == name.lower():
                    if proc.info['pid'] not in killed_pids:
                        for child in proc.children(recursive=True):
                            child.kill()
                        proc.kill()
                        killed_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    for exe_name in exe_names:
        kill_by_exe(exe_name)

    time.sleep(config.get("cleanup_wait_first", 5))
    stubborn = []
    for exe_name in exe_names:
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == exe_name.lower():
                    stubborn.append(exe_name)
                    proc.kill()
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if stubborn:
        logger.log(f"⚠️ 发现顽固进程 {', '.join(set(stubborn))}，已二次强杀")

    time.sleep(config.get("cleanup_wait_check", 3))
    logger.log("✅ 智能清场完成")


def clear_logs(log_dir: str):
    if not os.path.exists(log_dir):
        return
    for filename in os.listdir(log_dir):
        if filename.startswith("mxu-web-") or filename == "maafw.log":
            file_path = os.path.join(log_dir, filename)
            try:
                os.remove(file_path)
            except:
                pass
    time.sleep(1)


def is_process_running_by_name(exe_name: str) -> bool:
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == exe_name.lower():
                return True
        except:
            pass
    return False


def safe_kill_process(proc) -> bool:
    """安全地终止一个 subprocess.Popen 进程"""
    if proc is None:
        return False
    try:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except __import__('subprocess').TimeoutExpired:
            pass
        return True
    except (ProcessLookupError, OSError, AttributeError):
        return False