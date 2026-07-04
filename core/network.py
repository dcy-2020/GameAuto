"""网络检查与 WiFi 自愈模块"""
import socket
import subprocess
import time


def check_internet_connection(host="8.8.8.8", port=53, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except socket.error:
        try:
            sock.close()
        except Exception:
            pass
        return False


def connect_to_wifi(ssid_name: str, logger) -> bool:
    logger.log(f"🔄 正在尝试连接至 WiFi: [{ssid_name}]...")
    try:
        result = subprocess.run(
            f'netsh wlan connect name="{ssid_name}"',
            capture_output=True, text=True, encoding='gbk', errors='ignore', shell=True
        )
        if result.returncode == 0 or "successfully" in result.stdout.lower():
            time.sleep(8)
            return True
        else:
            logger.log(f"⚠️ 连接命令执行失败: {result.stdout.strip()}", level="WARN")
            return False
    except Exception as e:
        logger.log(f"⚠️ WiFi 切换抛出异常: {e}", level="WARN")
        return False


def ensure_network_ready(config: dict, logger):
    logger.log("🌐 正在执行网络连通性检查...")
    if check_internet_connection():
        logger.log("✅ 当前网络畅通，无需切换。")
        return True
    logger.log("❌ 检测到当前无外网访问权限，启动网络自愈协议！", level="WARN")

    wifi_primary = config.get("wifi_primary", "")
    wifi_backup = config.get("wifi_backup", "")

    if wifi_primary:
        logger.log(f"👉 优先级 1: 尝试恢复主网络 [{wifi_primary}]")
        connect_to_wifi(wifi_primary, logger)
        if check_internet_connection():
            logger.log(f"✅ 已成功恢复主网络 [{wifi_primary}]！")
            return True

    if wifi_backup:
        logger.log(f"❌ 主网络失效，启动备份方案！", level="WARN")
        logger.log(f"👉 优先级 2: 尝试连接备用热点 [{wifi_backup}]")
        connect_to_wifi(wifi_backup, logger)
        if check_internet_connection():
            logger.log(f"✅ 警告：已切换至备用热点 [{wifi_backup}]，请注意流量消耗！", level="WARN")
            return True

    logger.log("💥 致命错误：所有已配置的网络均无法提供外网访问！", level="ERROR")
    return False


import psutil


def check_boot_environment_ready(config: dict, logger):
    logger.log("⏳ 正在检测系统与网络环境是否就绪...")
    if not ensure_network_ready(config, logger):
        logger.log("❌ 网络自愈失败，彻底无法连接外网", level="ERROR")
        return False
    start_time = time.time()
    last_log_time = 0
    boot_max_wait = config.get("boot_max_wait", 600)
    while time.time() - start_time < boot_max_wait:
        if time.time() - last_log_time > 30:
            logger.log(f"⏰ 仍在等待系统资源释放... 已等待 {int(time.time()-start_time)} 秒")
            last_log_time = time.time()
        cpu_high = False
        try:
            cpu_load = psutil.cpu_percent(interval=1)
            if cpu_load > 30:
                cpu_high = True
                logger.log(f"⚠️ CPU负载过高({cpu_load}%)，等待中...", level="WARN")
        except Exception:
            pass
        if cpu_high:
            time.sleep(5)
            continue
        logger.log("✅ 开机环境(网络+性能)检测通过，准许起飞！")
        return True
    logger.log("❌ 系统性能等待超时，强行继续执行（可能出现卡顿异常）", level="ERROR")
    return True