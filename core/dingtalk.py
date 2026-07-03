"""钉钉消息推送模块"""
import requests
from datetime import datetime


def send_dingtalk_message(content: str, config: dict, title: str = "游戏日常自动化报告",
                          is_urgent: bool = False) -> bool:
    if not config.get("dingtalk_webhook"):
        return False
    try:
        data = {"msgtype": "markdown", "markdown": {"title": title, "text": content}}
        if is_urgent and config.get("dingtalk_at_mobiles"):
            at_text = " ".join([f"@{mobile}" for mobile in config["dingtalk_at_mobiles"]])
            data["markdown"]["text"] = f"{at_text}\n\n" + data["markdown"]["text"]
            data["at"] = {"atMobiles": config["dingtalk_at_mobiles"], "isAtAll": False}
        max_len = config.get("dingtalk_max_message_length", 18000)
        if len(data["markdown"]["text"]) > max_len:
            truncated = data["markdown"]["text"][:max_len - 50] + "\n\n...(内容过长已截断)"
            data["markdown"]["text"] = truncated
        requests.post(config["dingtalk_webhook"], json=data, timeout=10)
        return True
    except Exception as e:
        return False


def send_detailed_dingtalk_report(alarms, config: dict, state, logger=None):
    if not config.get("send_detailed_dingtalk") or not config.get("dingtalk_webhook"):
        return

    if logger:
        logger.log("📱 正在生成结构化钉钉战报...")

    ww_res = state.ww_analyzer._build_result()
    ef_res = state.ef_analyzer._build_result()
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    markdown_content = f"# 🎮 游戏自动化执行报告\n"
    markdown_content += f"**执行时间**: {today_str}\n\n"

    is_urgent = False
    if alarms:
        is_urgent = True
        markdown_content += "## 🚨 **监控系统强力告警**\n"
        for alarm in alarms:
            markdown_content += f"> {alarm}\n\n"
        markdown_content += "---\n\n"

    ww_status_icon = "🟢 **成功**" if state.ww_success else "🔴 **失败**"
    markdown_content += f"### 1. 鸣潮 (ok-ww) - {ww_status_icon}\n"
    markdown_content += f"**多账号进度**: {ww_res.progress}/{ww_res.total}\n\n"
    markdown_content += f"{ww_res.get_timeline_report()}\n"
    if ww_res.error_message:
        markdown_content += f"\n> **❌ 错误原因**: {ww_res.error_message}\n"
    if ww_res.warnings:
        unique_ww_warns = list(dict.fromkeys(ww_res.warnings))
        markdown_content += f"\n> **⚠️ 战斗/截图警告**: 拦截到 {len(ww_res.warnings)} 次偶发报错，最近一次: {unique_ww_warns[-1] if unique_ww_warns else ''}\n"
    markdown_content += "\n---\n\n"

    ef_status_icon = "🟢 **成功**" if state.ef_success else "🔴 **失败**"
    markdown_content += f"### 2. 终末地 (MaaEnd) - {ef_status_icon}\n"
    markdown_content += f"**节点进度**: {ef_res.progress}/{ef_res.total}\n\n"
    markdown_content += f"{ef_res.get_timeline_report()}\n"
    if ef_res.error_message:
        markdown_content += f"\n> **❌ 错误原因**: {ef_res.error_message}\n"
    if ef_res.warnings:
        unique_ef_warns = list(dict.fromkeys(ef_res.warnings))
        markdown_content += f"\n> **⚠️ 监控提示**: 拦截到 {len(ef_res.warnings)} 条网络波动等次要报错\n"

    markdown_content += "\n---\n\n"
    if config.get("enable_oknte", True):
        nte_status_icon = "🟢 **成功**" if state.nte_success else "🔴 **失败**"
        nte_res = state.nte_analyzer._build_result()
        markdown_content += f"### 3. 异环 (ok-nte) - {nte_status_icon}\n"
        markdown_content += f"**节点进度**: {nte_res.progress}/{nte_res.total}\n\n"
        markdown_content += f"{nte_res.get_timeline_report()}\n"
        if nte_res.warnings:
            unique_warns = list(dict.fromkeys(nte_res.warnings))
            markdown_content += f"> ⚠️ **运行警告**: 拦截到 {len(nte_res.warnings)} 次偶发报错，最近一次: {unique_warns[-1]}\n"
    else:
        markdown_content += f"### 3. 异环 (ok-nte) - ⏸️ **未启用**\n"
        markdown_content += "该功能已在配置中关闭。\n"

    title_prefix = "【🚨告警】" if is_urgent else "【日常】"
    send_dingtalk_message(markdown_content, config, title=f"{title_prefix} 自动化分析报告", is_urgent=is_urgent)