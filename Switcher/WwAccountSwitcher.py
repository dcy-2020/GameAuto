import os, sys, time, zipfile
import ctypes
from ctypes import wintypes

# pyautogui import 时会尝试加载 cv2，cv2 找不到 numpy 会打印错误到 stderr
# 先吞掉 stderr，import 完再恢复
_stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')
try:
    import pyautogui
    import pyscreeze
    pyscreeze.USE_OPENCV = False  # 强制纯 Python 匹配，不依赖 opencv/numpy
finally:
    sys.stderr.close()
    sys.stderr = _stderr

import pydirectinput

def is_admin():
    """检查当前是否具备管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def _get_resolution_key() -> str:
    """检测屏幕分辨率，返回 '1080P' 或 '2K'"""
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        w, h = pyautogui.size()
    if h <= 1080:
        return "1080P"
    else:
        return "2K"


class WwAccountSwitcher:
    def __init__(self, img_folder_name="imgs", confidence=0.85):
        """初始化切号器 — 自动检测分辨率并加载对应图包"""
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        base_img_dir = os.path.join(current_script_dir, img_folder_name)
        self.confidence = confidence

        # 直接使用基础目录的 PNG（与原版脚本一致，已验证可正常识别）
        self.img_dir = base_img_dir

    def _get_img_path(self, img_name):
        return os.path.join(self.img_dir, img_name)

    def activate_game_window(self, title_keywords=["鸣潮", "wuthering"]):
        """
        利用 Windows 原生 API 寻找并激活游戏窗口
        """
        print(f"🔍 正在寻找游戏窗口...")
        
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        
        target_hwnd = None
        
        # 遍历所有窗口，根据标题关键字寻找
        def foreach_window(hwnd, lParam):
            nonlocal target_hwnd
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    if any(kw.lower() in title for kw in [k.lower() for k in title_keywords]):
                        target_hwnd = hwnd
                        return False # 找到就停止遍历
            return True
            
        EnumWindows(EnumWindowsProc(foreach_window), 0)
        
        if target_hwnd:
            try:
                # 恢复窗口（如果被最小化了）
                ctypes.windll.user32.ShowWindow(target_hwnd, 9)
                
                # Windows防强占焦点机制破解：模拟按下 Alt 键
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                
                # 强制前置并设置焦点
                ctypes.windll.user32.SetForegroundWindow(target_hwnd)
                ctypes.windll.user32.SetFocus(target_hwnd)
                print("✅ 已成功将游戏窗口置于最前台！")
                time.sleep(1.5) # 给窗口渲染和获取焦点一点缓冲时间
                return True
            except Exception as e:
                print(f"❌ 激活窗口失败: {e}")
                return False
        else:
            print("❌ 未找到游戏窗口，请确认游戏是否已启动。")
            return False

    def wait_and_click(self, img_name, timeout=30, wait_after=1.0):
        """核心方法：带超时的动态等待并点击目标图片"""
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
        """
        核心方法补充：仅等待图片出现，不执行点击。
        用于判断场景是否加载完毕，避免过早触发动作。
        """
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
        """
        在登录界面（未展开下拉框时）识别当前默认展示的账号
        """
        print("👁️ 正在扫描登录界面的当前账号...")
        time.sleep(1) # 给UI一点渲染时间
        
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
        """纯 PIL 模板匹配，带容差（不依赖 opencv/numpy，打包前后一致）"""
        img_path = self._get_img_path("power_btn.png")
        try:
            from PIL import Image, ImageGrab
            template = Image.open(img_path).convert('RGB')
            screen = ImageGrab.grab().convert('RGB')
            tw, th = template.size
            sw, sh = screen.size
            if tw > sw or th > sh:
                return False

            tpix = list(template.getdata())
            tcount = len(tpix)

            # 步进扫描屏幕，每步计算匹配率
            for y in range(0, sh - th, 5):
                for x in range(0, sw - tw, 5):
                    region = screen.crop((x, y, x + tw, y + th))
                    rpix = list(region.getdata())
                    match = 0
                    for i in range(0, tcount, 3):  # 每 3 个像素抽 1 个
                        tr, tg, tb = tpix[i]
                        rr, rg, rb = rpix[i]
                        if abs(tr - rr) < 20 and abs(tg - rg) < 20 and abs(tb - rb) < 20:
                            match += 1
                    if match / (tcount / 3) > 0.85:
                        return True
            return False
        except Exception as e:
            print(f"⚠️ is_on_esc_menu 异常: {type(e).__name__}: {e}")
            try:
                return pyautogui.locateOnScreen(img_path) is not None
            except Exception:
                return False

    # def switch_account(self, target_account_suffix, known_accounts=["7267", "8071", "8701"]):
    #     """
    #     执行完整的切号流水线
    #     """
    #     print(f"\n🚀 === 开始切换账号至尾号: {target_account_suffix} ===")
        
    #     if not self.activate_game_window():
    #         return False
        
    #     # 1. 退出到登录界面
    #     print("⌨️ 按下 ESC 打开终端菜单...")
    #     pydirectinput.keyDown('esc')
    #     time.sleep(0.1) 
    #     pydirectinput.keyUp('esc')
    #     time.sleep(2)

    #     if not self.wait_and_click("power_btn.png", timeout=5):
    #         print("❌ 未在当前界面找到退出按钮，可能不在大世界状态？")
    #         return False

    #     if not self.wait_and_click("return_login_btn.png", timeout=5):
    #         return False

    #     # 2. 关键修正：只“看”不“点”，等待登录按钮出现，证明黑屏加载已结束
    #     print("⏳ 正在静默等待返回登录界面...")
    #     if not self.wait_for_image("login_btn.png", timeout=45):
    #         print("❌ 迟迟未检测到登录界面，可能掉线或游戏卡死")
    #         return False

    #     # 3. 此时下拉列表是闭合的，安全进行屏幕特征扫描
    #     current_acc = self.identify_account_on_login_screen(known_accounts)
        
    #     if current_acc == target_account_suffix:
    #         print(f"🎯 识别到当前已是目标账号 [{target_account_suffix}]，完美跳过下拉切换步骤！")
    #     else:
    #         print(f"🔄 当前是 [{current_acc}]，需要展开列表切换至 [{target_account_suffix}]")
            
    #         # 确认需要切号后，再去点击下拉箭头
    #         if not self.wait_and_click("dropdown_arrow.png", timeout=5, wait_after=1.0):
    #             print("❌ 无法展开下拉列表")
    #             return False

    #         # 点击列表中的目标账号
    #         account_img = f"acc_{target_account_suffix}.png"
    #         if not self.wait_and_click(account_img, timeout=5):
    #             print(f"❌ 在下拉列表中未找到账号 {target_account_suffix}")
    #             return False

    #     # 4. 无论是否切号，最后统一点击登录
    #     if not self.wait_and_click("login_btn.png", timeout=5):
    #         return False

    #     print(f"🎉 成功发送登录指令！等待游戏大世界加载...")
    #     return True

    def logout_and_identify(self, known_accounts=["7267", "8071", "8701"]):
        """
        原子动作 1：登出大世界，退回登录界面，并识别当前框内的账号
        """
        print("\n🚪 开始执行登出流程...")
        if not self.activate_game_window(): 
            return None

        print("⌨️ 按下 ESC 打开终端菜单...")
        pydirectinput.keyDown('esc')
        time.sleep(0.1) 
        pydirectinput.keyUp('esc')
        time.sleep(2)

        if not self.wait_and_click("power_btn.png", timeout=5): 
            return None
        if not self.wait_and_click("return_login_btn.png", timeout=5): 
            return None

        print("⏳ 正在静默等待返回登录界面...")
        if not self.wait_for_image("login_btn.png", timeout=45): 
            return None

        return self.identify_account_on_login_screen(known_accounts)
    
    def logout_from_esc_menu(self, known_accounts=["7267", "8071", "8701"]):
        """
        前提：游戏已经处于大世界的 ESC 菜单界面。
        不再按 ESC，直接点击退出按钮 → 返回登录 → 等待登录界面 → 识别当前账号
        """
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
        """
        原子动作 2：在登录界面上，执行下拉切换并进入游戏
        """
        print(f"\n🚀 开始执行登录指令，目标: [{target_account_suffix}]")
        
        # 如果不知道当前是谁（容错），或者需要切号，统统点开下拉列表
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
            
        print(f"🎉 成功发送登录指令！")
        return True

if __name__ == "__main__":
    # ==================== 管理员提权校验 ====================
    if not is_admin():
        print("🛡️ 当前非管理员权限，正在请求提权...")
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1
            )
        except Exception as e:
            print(f"❌ 提权失败: {e}")
        sys.exit()

    print("✅ 已获取管理员权限，脚本启动就绪！\n")
    # ========================================================

    switcher = WwAccountSwitcher()

    target = "8071"                            # 要切到的目标账号尾号
    known_accounts = ["7267", "8071", "8701"]  # 所有已知账号尾号

    # 第一步：登出大世界，回到登录界面，并识别当前框里的账号
    current_acc = switcher.logout_and_identify(known_accounts)
    if current_acc is None:
        print("❌ 登出或识别失败，脚本终止。")
        sys.exit(1)

    print(f"当前登录界面的账号是: {current_acc}")

    # 第二步：在登录界面执行切换（如果需要）并点击登录
    success = switcher.login_from_screen(target, current_acc)
    if success:
        print(f"\n🎉 切号流程执行完毕，正在进入目标账号 {target} 的大世界！")
    else:
        print(f"\n❌ 登录流程中断，未能进入账号 {target}。")