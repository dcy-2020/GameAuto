"""Windows 计划任务管理模块 - 通过 schtasks 命令创建/删除/查询"""
import subprocess
import sys
import os
import re


def _get_exe_path():
    """获取要计划执行的目标（优先 exe，否则 main.py）"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


def _get_python_exe():
    """获取 Python 解释器路径（源码模式需要）"""
    return sys.executable


def task_exists(task_name: str = "GameAutoDaily") -> bool:
    """检查计划任务是否存在"""
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name],
            capture_output=True, text=True, encoding='gbk', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_task_info(task_name: str = "GameAutoDaily") -> dict | None:
    """获取计划任务详情，返回 None 表示不存在"""
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "LIST", "/v"],
            capture_output=True, text=True, encoding='gbk', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return None

        info = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                info[key.strip()] = val.strip()

        # 提取下次运行时间
        next_run = info.get("Next Run Time", info.get("下次运行时间", ""))
        status = info.get("Status", info.get("状态", ""))
        return {
            "next_run": next_run if next_run != "N/A" else "暂无",
            "status": status if status != "N/A" else "未知",
            "raw": info,
        }
    except Exception:
        return None


def create_daily_task(config: dict, logger=None) -> bool:
    """
    创建/更新每日计划任务
    返回 True 表示成功
    """
    task_name = config.get("schedule_task_name", "GameAutoDaily")
    time_str = config.get("schedule_time", "09:40")
    enabled = config.get("schedule_enabled", False)

    # 先删除旧任务（如果存在）
    if task_exists(task_name):
        delete_task(task_name, logger)

    if not enabled:
        if logger:
            logger.log("⏰ 计划任务未启用，跳过创建", level="WARN")
        return False  # 未启用视为未创建

    # 解析时间
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        if logger:
            logger.log(f"❌ 时间格式错误: {time_str}，应为 HH:MM", level="ERROR")
        return False
    hour, minute = parts[0].strip(), parts[1].strip()

    # 构建命令行（带 --auto 参数，自动开始执行）
    if getattr(sys, 'frozen', False):
        program = _get_exe_path()
        arguments = "--auto"
    else:
        program = _get_python_exe()
        arguments = f'"{_get_exe_path()}" --auto'

    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{program}" {arguments}'.strip(),
        "/sc", "daily",
        "/st", f"{hour.zfill(2)}:{minute.zfill(2)}",
        "/f",                          # 强制覆盖
        "/rl", "highest",              # 以最高权限运行
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding='gbk', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            if logger:
                logger.log(f"✅ 计划任务已创建: 每日 {hour.zfill(2)}:{minute.zfill(2)} 自动执行")
            return True
        else:
            if logger:
                logger.log(f"❌ 创建计划任务失败: {result.stderr.strip()}", level="ERROR")
            return False
    except Exception as e:
        if logger:
            logger.log(f"❌ 创建计划任务异常: {e}", level="ERROR")
        return False


def delete_task(task_name: str = "GameAutoDaily", logger=None) -> bool:
    """删除计划任务"""
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True, text=True, encoding='gbk', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            if logger:
                logger.log(f"🗑️ 已删除旧的计划任务 [{task_name}]")
            return True
        return False
    except Exception as e:
        if logger:
            logger.log(f"⚠️ 删除计划任务异常: {e}", level="WARN")
        return False
