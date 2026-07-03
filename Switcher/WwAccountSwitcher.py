import pyautogui
import time
import os
import pydirectinput
import ctypes
from ctypes import wintypes
import sys

def is_admin():
    """检查当前是否具备管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class WwAccountSwitcher:
    def __init__(self, img_folder_name="imgs", confidence=0.85):
        """初始化切号器"""
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        self.img_dir = os.path.join(current_script_dir, img_folder_name)
        self.confidence = confidence

        if not os.path.exists(self.img_dir):
            print(f"⚠️ 警告: 找不到图片文件夹 {self.img_dir}")

    def _get_img_path(self, img_name):
        return os.path.join(self.img_dir, img_name)

    def activate_game_window(self, title_keywords=["鸣潮", "wuthering"]):
        print(f"🔍 正在寻找游戏窗口...")
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        target_hwnd = None
        def foreach_window(hwnd, lParam):
            nonlocal target_hwnd
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    if any(kw.lower() in title for kw in title_keywords):
                        target_hwnd = hwnd
            return True
        EnumWindows(EnumWindowsProc(foreach_window), 0)
        if target_hwnd:
            ctypes.windll.user32.ShowWindow(target_hwnd, 9)
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ctypes.windll.user32.SetForegroundWindow(target_hwnd)
            print(f"✅ 已激活游戏窗口")
            time.sleep(0.5)
            return True
        print("❌ 未找到游戏窗口，请确认游戏是否已启动。")
        return False

    def wait_and_click(self, img_name, timeout=30, wait_after=1.0):
        img_path = self._get_img_path(img_name)
        if not os.path.exists(img_path):
            print(f"❌ 错误: 找不到截图文件 {img_path}")
            return False
        print(f"  └─ 寻找: {img_name} ...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                location = pyautogui.locateCenterOnScreen(img_path, confidence=self.confidence)
                if location:
                    pydirectinput.click(int(location.x), int(location.y))
                    print(f"  └─ ✅ 点击成功")
                    time.sleep(wait_after)
                    return True
            except pyautogui.ImageNotFoundException:
                pass
            time.sleep(0.5)
        print(f"  └─ ⚠️ 超时未找到 ({timeout}s)")
        return False

    def wait_for_image(self, img_name, timeout=30):
        img_path = self._get_img_path(img_name)
        if not os.path.exists(img_path):
            print(f"❌ 错误: 找不到截图文件 {img_path}")
            return False
        print(f"  └─ 视觉锚点等待: {img_name} ...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if pyautogui.locateOnScreen(img_path, confidence=self.confidence):
                    return True
            except pyautogui.ImageNotFoundException:
                pass
            time.sleep(0.5)
        return False

    def identify_account_on_login_screen(self, account_list):
        print("👁️ 正在扫描登录界面的当前账号...")
        time.sleep(1)
        for acc in account_list:
            current_img = f"acc_{acc}.png"
            img_path = self._get_img_path(current_img)
            if not os.path.exists(img_path):
                print(f"  └─ ⚠️ 警告: 缺少特征截图 {current_img}")
                continue
            try:
                if pyautogui.locateOnScreen(img_path, confidence=0.85):
                    print(f"  └─ ✅ 识别成功！当前框内账号是: [{acc}]")
                    return acc
            except pyautogui.ImageNotFoundException:
                pass
        print("  └─ ❓ 未能识别出框内的账号特征")
        return None

    def is_on_esc_menu(self):
        try:
            img_path = self._get_img_path("power_btn.png")
            return pyautogui.locateOnScreen(img_path, confidence=0.85) is not None
        except:
            return False

    def logout_from_esc_menu(self, known_accounts=["7267", "8071", "8701"]):
        print("🚪 从 ESC 菜单开始登出流程...")
        if not self.wait_and_click("power_btn.png", timeout=5):
            return None
        if not self.wait_and_click("return_login_btn.png", timeout=5):
            return None
        print("⏳ 正在静默等待返回登录界面...")
        if not self.wait_for_image("login_btn.png", timeout=45):
            return None
        return self.identify_account_on_login_screen(known_accounts)

    def login_from_screen(self, target_account_suffix, current_acc_on_screen):
        print(f"\n🚀 开始执行登录指令，目标: [{target_account_suffix}]")
        if current_acc_on_screen == target_account_suffix:
            print(f"🎯 识别到屏幕上已经是目标 [{target_account_suffix}]，直接点击登录！")
        else:
            print(f"🔄 展开列表，准备切换至 [{target_account_suffix}]")
            if not self.wait_and_click("dropdown_arrow.png", timeout=5, wait_after=1.0):
                return False
            if not self.wait_and_click(f"acc_{target_account_suffix}.png", timeout=5):
                return False
        if not self.wait_and_click("login_btn.png", timeout=5):
            return False
        print(f"🎉 成功发送登录指令！等待游戏大世界加载...")
        return True
