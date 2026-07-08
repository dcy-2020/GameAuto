"""AI 多模态异常处理模块"""
import base64
import io
import json
import re
import time

import pydirectinput
import requests
from PIL import ImageGrab
from typing import Optional


class AIAssistant:
    """AI 辅助助手 - 通过多模态模型分析截图并执行操作"""

    # 服务商预设
    _PROVIDERS = {
        "aliyun": {
            "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            "default_model": "qwen3-vl-flash",
            "protocol": "dashscope",
        },
    }

    def __init__(self, api_key: str, model: str = "qwen3.6-flash", logger=None,
                 provider: str = "aliyun", base_url: str = ""):
        self.api_key = api_key
        self.provider = (provider or "aliyun").lower()
        preset = self._PROVIDERS.get(self.provider, self._PROVIDERS["aliyun"])
        self.model = model or preset["default_model"]
        self.protocol = preset["protocol"]
        self.api_url = (base_url or preset["base_url"]).rstrip("/")
        if logger is None:
            class _DummyLogger:
                def log(self, *args, **kwargs): pass
            self.logger = _DummyLogger()
        else:
            self.logger = logger
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.screenshot_region = None

    def _extract_text_from_response(self, data: dict) -> Optional[str]:
        try:
            output = data.get("output", {})
            choices = output.get("choices", [])
            if not choices:
                self._log(f"API 响应无 choices: {data}", "WARN")
                return None
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        return item.get("text", "")
                    if isinstance(item, dict) and "text" in item:
                        return item["text"]
                return content[0] if content else None
            self._log(f"未知 content 类型: {type(content)} value: {content}", "WARN")
            return None
        except Exception as e:
            self._log(f"解析 API 响应异常: {e}", "WARN")
            return None

    def capture_screen(self):
        try:
            img = ImageGrab.grab(self.screenshot_region) if self.screenshot_region else ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=50)
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as e:
            self._log(f"截图失败: {e}", "WARN")
            return None

    def ask_for_action(self, screenshot_b64: str, context: str, timeout: int = 120) -> Optional[dict]:
        if not screenshot_b64:
            return None

        prompt = f"""你是一个游戏辅助AI。当前脚本在执行游戏日常任务时遇到了未知状况，或需要你进行智能决策。
请根据截图分析当前屏幕内容，判断应该进行什么操作来继续流程。
可能的情况包括：
- 弹出活动公告/领取奖励/签到弹窗 → 点击"关闭"或"确认"或"领取"按钮
- 网络重连提示 → 点击"重试"或"确认"
- 游戏更新公告 → 点击"确定"
- 角色死亡/任务失败 → 点击"复活"或"重新挑战"
- 正常游戏画面且没有需要干预的 → 返回 {{"action": "skip"}}

【附加上下文】: {context}

重要：截图是2560*1440的全屏幕截图，返回的点击坐标必须精准对应屏幕上要点击的点位。
你必须返回一个合法的JSON对象，格式如下（只返回JSON，不要有其他文字）：
{{"action": "click", "x": 整数像素坐标, "y": 整数像素坐标}}
或
{{"action": "skip"}}
或
{{"action": "key", "key": "按键名"}}   (按键名例如 "enter", "esc", "space")
"""
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": f"data:image/jpeg;base64,{screenshot_b64}"},
                            {"text": prompt}
                        ]
                    }
                ]
            },
            "parameters": {
                "result_format": "message"
            }
        }
        # 强制直连，避免系统代理劫持内网端点导致超时
        no_proxy = {"http": None, "https": None}
        try:
            resp = requests.post(self.api_url, headers=self.headers, json=payload, timeout=timeout, proxies=no_proxy)
            if resp.status_code == 200:
                data = resp.json()
                text = self._extract_text_from_response(data)
                if not text:
                    self._log("API 响应中未提取到有效文本", "WARN")
                    return None
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    raw_json = json_match.group()
                    raw_json = re.sub(r'"x"\s*:\s*(\d+)\s*,\s*(\d+)', r'"x": \1, "y": \2', raw_json)
                    raw_json = re.sub(r'([{,])\s*([a-zA-Z_]+)\s*:', r'\1"\2":', raw_json)
                    try:
                        action = json.loads(raw_json)
                        self._log(f"AI返回动作: {action}", "INFO")
                        return action
                    except json.JSONDecodeError:
                        act_match = re.search(r'"action"\s*:\s*"(click|skip|key)"', raw_json)
                        if act_match:
                            act_type = act_match.group(1)
                            if act_type == "click":
                                coords = re.findall(r'\b(\d+)\b', raw_json)
                                if len(coords) >= 2:
                                    action = {"action": "click", "x": int(coords[0]), "y": int(coords[1])}
                                    self._log(f"AI返回动作(降级): {action}", "WARN")
                                    return action
                            elif act_type == "skip":
                                self._log("AI返回动作(降级): skip", "WARN")
                                return {"action": "skip"}
                            elif act_type == "key":
                                key_match = re.search(r'"key"\s*:\s*"([^"]+)"', raw_json)
                                if key_match:
                                    action = {"action": "key", "key": key_match.group(1)}
                                    self._log(f"AI返回动作(降级): {action}", "WARN")
                                    return action
                    self._log(f"AI返回JSON无法解析: {raw_json[:200]}", "WARN")
                else:
                    self._log(f"AI返回非JSON: {text[:200]}", "WARN")
            else:
                self._log(f"API请求失败: {resp.status_code} {resp.text[:200]}", "WARN")
            return None
        except Exception as e:
            self._log(f"AI API调用异常: {e}", "WARN")
            return None

    def execute_action(self, action: dict) -> bool:
        if not action:
            return False
        act_type = action.get("action")
        if act_type == "click":
            x, y = action.get("x"), action.get("y")
            if x is not None and y is not None:
                self._log(f"🤖 AI执行点击 ({x}, {y})")
                try:
                    pydirectinput.moveTo(x, y, duration=0.1)
                    pydirectinput.click()
                    return True
                except Exception as e:
                    self._log(f"点击失败: {e}", "WARN")
                    return False
        elif act_type == "key":
            key = action.get("key")
            if key:
                self._log(f"🤖 AI执行按键 [{key}]")
                try:
                    pydirectinput.keyDown(key)
                    time.sleep(0.1)
                    pydirectinput.keyUp(key)
                    time.sleep(2)
                    return True
                except Exception as e:
                    self._log(f"按键失败: {e}", "WARN")
                    return False
        elif act_type == "skip":
            self._log("🤖 AI判定无需操作")
            return True
        else:
            self._log(f"未知动作类型: {act_type}", "WARN")
        return False

    def _log(self, msg, level="INFO"):
        if self.logger:
            self.logger.log(msg, level=level)
        else:
            print(f"[AI] {msg}")