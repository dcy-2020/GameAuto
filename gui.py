"""GameAuto GUI - CustomTkinter 图形界面"""
import os
import sys
import json
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ===== 主题系统 =====
THEMES = {
    "暗夜绿": {
        "appearance": "dark",
        "ctk_theme":  "green",
        "bg":        "#0d1117",
        "fg":        "#161b22",
        "accent":    "#21262d",
        "highlight": "#3fb950",
        "success":   "#3fb950",
        "warning":   "#d2991d",
        "error":     "#f85149",
        "info":      "#58a6ff",
        "text":      "#c9d1d9",
        "text_dim":  "#8b949e",
        "border":    "#30363d",
    },
    "深海蓝": {
        "appearance": "dark",
        "ctk_theme":  "blue",
        "bg":        "#0a0e27",
        "fg":        "#111640",
        "accent":    "#1a2048",
        "highlight": "#4a9eff",
        "success":   "#4a9eff",
        "warning":   "#e2b03d",
        "error":     "#f85149",
        "info":      "#4a9eff",
        "text":      "#c9d1d9",
        "text_dim":  "#8b949e",
        "border":    "#2a3560",
    },
    "碳素灰": {
        "appearance": "dark",
        "ctk_theme":  "dark-blue",
        "bg":        "#1a1a1a",
        "fg":        "#242424",
        "accent":    "#2e2e2e",
        "highlight": "#888888",
        "success":   "#6aaa64",
        "warning":   "#c9a43b",
        "error":     "#d94a4a",
        "info":      "#8b8b8b",
        "text":      "#cccccc",
        "text_dim":  "#888888",
        "border":    "#3a3a3a",
    },
    "日落橙": {
        "appearance": "dark",
        "ctk_theme":  "green",
        "bg":        "#1c1410",
        "fg":        "#261d16",
        "accent":    "#2f241c",
        "highlight": "#f0883e",
        "success":   "#f0883e",
        "warning":   "#e2b03d",
        "error":     "#f85149",
        "info":      "#e2b03d",
        "text":      "#d4c5b9",
        "text_dim":  "#9e8e7e",
        "border":    "#3d3028",
    },
    "极光白": {
        "appearance": "light",
        "ctk_theme":  "green",
        "bg":        "#e8ecef",
        "fg":        "#f6f8fa",
        "accent":    "#e0e4e8",
        "highlight": "#2da44e",
        "success":   "#2da44e",
        "warning":   "#bf8700",
        "error":     "#cf222e",
        "info":      "#0969da",
        "text":      "#1f2328",
        "text_dim":  "#656d76",
        "border":    "#d0d7de",
    },
}

# 当前激活的主题配色（运行时动态切换）
_current_theme_name = "暗夜绿"
COLORS = dict(THEMES[_current_theme_name])

LOG_LEVEL_COLORS = {
    "INFO":    COLORS["text"],
    "WARN":    COLORS["warning"],
    "ERROR":   COLORS["error"],
    "SUCCESS": COLORS["success"],
}


class LogViewer(ctk.CTkFrame):
    """实时日志查看器 - 彩色分级显示"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.textbox = ctk.CTkTextbox(
            self,
            fg_color=COLORS["bg"],
            text_color=COLORS["text"],
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, padx=2, pady=2)

        self.textbox.tag_config("INFO", foreground=LOG_LEVEL_COLORS["INFO"])
        self.textbox.tag_config("WARN", foreground=LOG_LEVEL_COLORS["WARN"])
        self.textbox.tag_config("ERROR", foreground=LOG_LEVEL_COLORS["ERROR"])
        self.textbox.tag_config("SUCCESS", foreground=LOG_LEVEL_COLORS["SUCCESS"])

        self._line_count = 0

    def append(self, message: str, level: str = "INFO"):
        self.textbox.configure(state="normal")
        tag = level if level in LOG_LEVEL_COLORS else "INFO"
        self.textbox.insert("end", message + "\n", tag)
        self._line_count += 1
        if self._line_count > 5000:
            self.textbox.delete("1.0", "2.0")
            self._line_count -= 1
        self.textbox.configure(state="disabled")
        self.textbox.see("end")

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self._line_count = 0
        self.textbox.configure(state="disabled")


class StringListEditor(ctk.CTkFrame):
    """字符串列表编辑器 - 可增删"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._items = []
        self._item_frames = []

        self.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))

        ctk.CTkButton(
            btn_row, text="+ 添加", width=70, height=28,
            command=self._add_item,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_row, text="清空", width=60, height=28,
            fg_color=COLORS["accent"],
            command=self.clear,
        ).pack(side="left", padx=2)

        self._scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=100)
        self._scroll_frame.grid(row=1, column=0, sticky="nsew", padx=2)
        self._scroll_frame.grid_columnconfigure(0, weight=1)

    def set_items(self, items: list):
        self.clear()
        for item in items:
            self._add_item(item)

    def get_items(self) -> list:
        return [item for item in self._items if item.strip()]

    def _add_item(self, value: str = ""):
        row = len(self._item_frames)
        frame = ctk.CTkFrame(self._scroll_frame, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", pady=1)
        frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(frame, placeholder_text="请输入...")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        if value:
            entry.insert(0, value)

        btn = ctk.CTkButton(
            frame, text="✕", width=30, height=28,
            fg_color=COLORS["error"],
            command=lambda f=frame, e=entry: self._remove_item(f, e),
        )
        btn.grid(row=0, column=1)

        self._item_frames.append(frame)
        self._items.append(value)

        def on_change(_, e=entry, idx=row):
            if idx < len(self._items):
                self._items[idx] = e.get()
        entry.bind("<KeyRelease>", on_change)

    def _remove_item(self, frame, entry):
        if frame in self._item_frames:
            idx = self._item_frames.index(frame)
            if idx < len(self._items):
                self._items.pop(idx)
            self._item_frames.pop(idx)
            frame.destroy()

    def clear(self):
        for frame in self._item_frames:
            frame.destroy()
        self._item_frames.clear()
        self._items.clear()


class GameAutoGUI(ctk.CTk):
    """主窗口"""

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self._runner = None
        self._TaskRunner = None
        self._import_error = None
        self._theme = config.get("_theme", "暗夜绿")

        # 应用主题外观
        global COLORS, LOG_LEVEL_COLORS, _current_theme_name
        _current_theme_name = self._theme
        COLORS.update(THEMES[self._theme])
        LOG_LEVEL_COLORS.update({
            "INFO": COLORS["text"], "WARN": COLORS["warning"],
            "ERROR": COLORS["error"], "SUCCESS": COLORS["success"],
        })
        ctk.set_appearance_mode(THEMES[self._theme]["appearance"])
        ctk.set_default_color_theme(THEMES[self._theme]["ctk_theme"])

        # 延迟导入 TaskRunner
        try:
            from core.task_runner import TaskRunner
            self._TaskRunner = TaskRunner
        except ImportError as e:
            self._import_error = str(e)

        self.title("🎮 GameAuto Daily v2.0")
        self.geometry("1600x900")
        self.minsize(1000, 650)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ---- 顶部标题栏 ----
        title_bar = ctk.CTkFrame(self, height=44, fg_color=COLORS["fg"],
                                 corner_radius=0)
        title_bar.pack(fill="x", padx=0, pady=0)

        ctk.CTkLabel(
            title_bar, text="🎮  GameAuto Daily",
            text_color=COLORS["highlight"],
        ).pack(side="left", padx=20, pady=10)

        # 主题切换按钮组
        theme_group = ctk.CTkFrame(title_bar, fg_color="transparent")
        theme_group.pack(side="right", padx=(0, 8), pady=8)

        self._theme_btns = {}
        theme_names = list(THEMES.keys())
        for i, name in enumerate(theme_names):
            is_active = (name == self._theme)
            btn = ctk.CTkButton(
                theme_group, text=name, width=52, height=22,
                fg_color=COLORS["highlight"] if is_active else COLORS["accent"],
                hover_color=COLORS["highlight"],
                command=lambda n=name: self._switch_theme(n),
            )
            btn.pack(side="left", padx=1)
            self._theme_btns[name] = btn

        self._status_label = ctk.CTkLabel(
            title_bar, text="● 就绪",
            text_color=COLORS["success"],
        )
        self._status_label.pack(side="right", padx=(0, 15), pady=10)

        # ---- 主内容区：左右分栏 ----
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        main_area.grid_columnconfigure(0, weight=1)  # 左侧伸展
        main_area.grid_columnconfigure(1, weight=0)  # 拖拽手柄(固定)
        main_area.grid_columnconfigure(2, weight=0)  # 右侧(可拖拽调整)
        main_area.grid_rowconfigure(0, weight=1)

        # ===== 左侧：配置 Tab =====
        left_panel = ctk.CTkFrame(main_area, fg_color=COLORS["fg"],
                                  corner_radius=10)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        left_panel.grid_rowconfigure(0, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # ===== 拖拽手柄 =====
        self._handle = ctk.CTkFrame(main_area, width=5, fg_color="transparent",
                                     cursor="sb_h_double_arrow")
        self._handle.grid(row=0, column=1, sticky="ns", padx=0)
        self._handle.bind("<ButtonPress-1>", self._on_handle_press)
        self._handle.bind("<B1-Motion>", self._on_handle_drag)
        # 手柄中间画一条竖线
        handle_line = ctk.CTkFrame(self._handle, width=1, fg_color=COLORS["border"])
        handle_line.place(relx=0.5, rely=0, relheight=1, anchor="n")
        # 手柄悬停高亮
        def on_enter(e): handle_line.configure(fg_color=COLORS["highlight"])
        def on_leave(e): handle_line.configure(fg_color=COLORS["border"])
        self._handle.bind("<Enter>", on_enter)
        self._handle.bind("<Leave>", on_leave)

        # 右侧面板初始宽度（优先从配置恢复，否则默认 420）
        self._right_width = self.config.get("_splitter_pos", 420)
        main_area.grid_columnconfigure(2, minsize=self._right_width)

        self._tabview = ctk.CTkTabview(
            left_panel,
            fg_color=COLORS["fg"],
            segmented_button_fg_color=COLORS["accent"],
            segmented_button_selected_color=COLORS["highlight"],
            segmented_button_unselected_color=COLORS["accent"],
            segmented_button_unselected_hover_color="#2d3748",
            corner_radius=8,
        )
        self._tabview.pack(fill="both", expand=True, padx=4, pady=4)

        from config_manager import CONFIG_GROUPS
        self._config_widgets = {}

        for group_key, group_info in CONFIG_GROUPS.items():
            tab_name = group_info["label"]
            self._tabview.add(tab_name)
            tab = self._tabview.tab(tab_name)
            self._build_config_form(tab, group_info["keys"])

        # ===== 右侧：日志 + 控制面板 =====
        right_panel = ctk.CTkFrame(main_area, fg_color=COLORS["fg"],
                                   corner_radius=10)
        right_panel.grid(row=0, column=2, sticky="nsew", padx=(1, 0))
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=0)
        right_panel.grid_rowconfigure(2, weight=0)
        right_panel.grid_columnconfigure(0, weight=1)

        # 日志
        log_header = ctk.CTkFrame(right_panel, fg_color="transparent", height=28)
        log_header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))

        ctk.CTkLabel(log_header, text="📋 运行日志").pack(side="left")
        ctk.CTkButton(
            log_header, text="清空", width=50, height=24,
            fg_color=COLORS["accent"],
            command=self._clear_log,
        ).pack(side="right", padx=2)

        self._log_viewer = LogViewer(right_panel)
        self._log_viewer.grid(row=0, column=0, sticky="nsew", padx=4, pady=(30, 4))

        # 计划任务状态
        sched_bar = ctk.CTkFrame(right_panel, fg_color=COLORS["accent"],
                                 corner_radius=6, height=36)
        sched_bar.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        sched_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sched_bar, text="⏰ 计划任务").pack(side="left", padx=8, pady=6)
        self._schedule_status_label = ctk.CTkLabel(
            sched_bar, text="检查中...", text_color=COLORS["text_dim"],
        )
        self._schedule_status_label.pack(side="left", padx=4, pady=6)

        ctk.CTkButton(
            sched_bar, text="创建", width=55, height=24,
            fg_color=COLORS["success"], hover_color="#2ea043",
            command=self._schedule_create,
        ).pack(side="right", padx=2, pady=6)
        ctk.CTkButton(
            sched_bar, text="删除", width=55, height=24,
            fg_color=COLORS["error"], hover_color="#da3633",
            command=self._schedule_delete,
        ).pack(side="right", padx=2, pady=6)

        # 控制按钮
        ctrl_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        ctrl_bar.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 6))

        ctk.CTkButton(
            ctrl_bar, text="💾 保存配置", width=85, height=30,
            fg_color=COLORS["accent"], hover_color="#2d3748",
            command=self._save_config,
        ).pack(side="left", padx=2, pady=4)

        ctk.CTkButton(
            ctrl_bar, text="🔄 恢复默认", width=85, height=30,
            fg_color=COLORS["accent"], hover_color="#2d3748",
            command=self._reset_config,
        ).pack(side="left", padx=2, pady=4)

        self._start_btn = ctk.CTkButton(
            ctrl_bar, text="▶ 开始", width=80, height=30,
            fg_color=COLORS["success"], hover_color="#2ea043",
            command=self._start_task,
        )
        self._start_btn.pack(side="right", padx=2, pady=4)

        self._stop_btn = ctk.CTkButton(
            ctrl_bar, text="⏹ 停止", width=80, height=30,
            fg_color=COLORS["error"], hover_color="#da3633",
            command=self._stop_task,
            state="disabled",
        )
        self._stop_btn.pack(side="right", padx=2, pady=4)

        self.after(500, self._refresh_schedule_status)

    def _build_config_form(self, parent_tab, keys: list):
        from config_manager import CONFIG_HELP

        scroll_frame = ctk.CTkScrollableFrame(parent_tab, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(1, weight=1)

        row = 0
        for key in keys:
            help_info = CONFIG_HELP.get(key, (key, ""))
            label_text = help_info[0] if isinstance(help_info, tuple) else key

            ctk.CTkLabel(
                scroll_frame, text=label_text, anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(5, 10), pady=3)

            value = self.config.get(key, "")

            if isinstance(value, bool):
                var = ctk.BooleanVar(value=value)
                ctk.CTkCheckBox(scroll_frame, text="", variable=var, width=30).grid(
                    row=row, column=1, sticky="w", padx=2, pady=3)
                self._config_widgets[key] = ("bool", var)

            elif isinstance(value, list):
                editor = StringListEditor(scroll_frame, height=80)
                editor.grid(row=row, column=1, sticky="ew", padx=2, pady=3)
                editor.set_items(value)
                self._config_widgets[key] = ("list", editor)

            elif isinstance(value, int) and key in ("okww_run_mode",):
                var = ctk.StringVar(value=str(value))
                ctk.CTkOptionMenu(scroll_frame, values=["1", "2"], variable=var, width=100).grid(
                    row=row, column=1, sticky="w", padx=2, pady=3)
                self._config_widgets[key] = ("option", var)

            elif isinstance(value, (int, float)):
                var = ctk.StringVar(value=str(value))
                ctk.CTkEntry(scroll_frame, textvariable=var, width=120).grid(
                    row=row, column=1, sticky="w", padx=2, pady=3)
                self._config_widgets[key] = ("number", var, type(value))

            else:
                var = ctk.StringVar(value=str(value) if value else "")
                ctk.CTkEntry(scroll_frame, textvariable=var).grid(
                    row=row, column=1, sticky="ew", padx=2, pady=3)

                if "path" in key or "dir" in key or "exe" in key or "log" in key:
                    is_dir = "path" in key or "dir" in key
                    self._config_widgets[key] = ("path_str", var, is_dir)
                    ctk.CTkButton(
                        scroll_frame, text="📂", width=35, height=28,
                        fg_color=COLORS["accent"],
                        command=lambda k=key, v=var, d=is_dir: self._browse_path(k, v, d),
                    ).grid(row=row, column=2, padx=2, pady=3)
                else:
                    self._config_widgets[key] = ("str", var)

            if isinstance(help_info, tuple) and help_info[1]:
                ctk.CTkLabel(
                    scroll_frame, text=f"💡 {help_info[1]}",
                    text_color=COLORS["text_dim"], anchor="w",
                ).grid(row=row + 1, column=1, sticky="w", padx=2, pady=(0, 5))

            row += (3 if (isinstance(help_info, tuple) and help_info[1]) else 2)

    # ===== 主题切换 =====

    def _switch_theme(self, name: str):
        """切换主题皮肤 — 重建 UI 以完全生效"""
        if name not in THEMES or name == self._theme:
            return
        self._theme = name
        self.config["_theme"] = name

        global COLORS, LOG_LEVEL_COLORS, _current_theme_name
        _current_theme_name = name
        t = THEMES[name]
        COLORS.update(t)
        LOG_LEVEL_COLORS.update({
            "INFO": COLORS["text"], "WARN": COLORS["warning"],
            "ERROR": COLORS["error"], "SUCCESS": COLORS["success"],
        })
        ctk.set_appearance_mode(t["appearance"])
        ctk.set_default_color_theme(t["ctk_theme"])

        # 保存当前配置值（重建 UI 后会丢失 UI 中的未保存修改）
        saved_config = dict(self.config)

        # 销毁并重建整个 UI
        for child in self.winfo_children():
            child.destroy()

        self.config = saved_config
        self._build_ui()

        from config_manager import save_config
        save_config(self.config)

    # ===== 拖拽分栏 =====

    def _on_handle_press(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_w = self._right_width

    def _on_handle_drag(self, event):
        delta = self._drag_start_x - event.x_root
        win_w = self.winfo_width()
        min_w, max_w = 280, int(win_w * 0.7)
        new_w = max(min_w, min(max_w, self._drag_start_w + delta))
        self._right_width = new_w
        self._handle.master.grid_columnconfigure(2, minsize=new_w)

    def _save_splitter_pos(self):
        """保存分栏位置到 config"""
        self.config["_splitter_pos"] = self._right_width
        from config_manager import save_config
        save_config(self.config)

    def _browse_path(self, key, var, is_dir):
        if is_dir:
            path = filedialog.askdirectory(title="选择目录")
        else:
            path = filedialog.askopenfilename(
                title="选择文件",
                filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
            )
        if path:
            var.set(path)

    def _read_config_from_ui(self):
        config = {}
        for key, info in self._config_widgets.items():
            wtype = info[0]
            if wtype == "bool":
                config[key] = info[1].get()
            elif wtype == "list":
                config[key] = info[1].get_items()
            elif wtype == "option":
                val = info[1].get()
                config[key] = int(val) if val.isdigit() else val
            elif wtype == "number":
                raw = info[1].get()
                try:
                    config[key] = info[2](raw)
                except (ValueError, TypeError):
                    config[key] = raw
            elif wtype in ("str", "path_str"):
                config[key] = info[1].get()
        return config

    def _refresh_schedule_status(self):
        """刷新计划任务状态显示"""
        try:
            from core.scheduler import task_exists, get_task_info
            task_name = self.config.get("schedule_task_name", "GameAutoDaily")
            if task_exists(task_name):
                info = get_task_info(task_name)
                next_run = info.get("next_run", "未知") if info else "未知"
                self._schedule_status_label.configure(
                    text=f"✅ 已创建 | 下次运行: {next_run}",
                    text_color=COLORS["success"],
                )
            else:
                self._schedule_status_label.configure(
                    text="❌ 未创建", text_color=COLORS["text_dim"],
                )
        except Exception:
            self._schedule_status_label.configure(
                text="⚠️ 无法查询", text_color=COLORS["warning"],
            )

    def _schedule_create(self):
        """立即创建计划任务 - 读取表单配置并写入 Windows 任务计划程序"""
        new_config = self._read_config_from_ui()
        self.config.update(new_config)

        # 确保已启用
        if not self.config.get("schedule_enabled", False):
            if not messagebox.askyesno(
                "确认启用",
                "计划任务当前未启用。\n\n"
                "点击「是」将自动启用并创建每日定时任务。"
            ):
                return
            self.config["schedule_enabled"] = True
            # 同步勾选 UI 中的复选框
            if "schedule_enabled" in self._config_widgets:
                wtype, var = self._config_widgets["schedule_enabled"][:2]
                if wtype == "bool":
                    var.set(True)

        time_str = self.config.get("schedule_time", "09:40")
        task_name = self.config.get("schedule_task_name", "GameAutoDaily")

        from core.scheduler import create_daily_task
        from config_manager import save_config
        save_config(self.config)

        if create_daily_task(self.config):
            self._log_viewer.append(
                f"✅ 计划任务已创建: 每日 {time_str} 执行 [{task_name}]",
                "SUCCESS",
            )
            messagebox.showinfo(
                "创建成功",
                f"Windows 计划任务已创建。\n\n"
                f"任务名称: {task_name}\n"
                f"执行时间: 每日 {time_str}\n"
                f"权限级别: 最高权限\n\n"
                f"可在 Windows「任务计划程序」中查看。"
            )
        else:
            self._log_viewer.append("❌ 创建计划任务失败，请确认已以管理员身份运行", "ERROR")
            messagebox.showerror(
                "创建失败",
                "无法创建 Windows 计划任务。\n\n"
                "可能原因:\n"
                "1. 未以管理员身份运行程序\n"
                "2. 时间格式不正确（应为 HH:MM）\n"
                "3. 系统安全策略阻止"
            )
        self._refresh_schedule_status()

    def _schedule_delete(self):
        task_name = self.config.get("schedule_task_name", "GameAutoDaily")
        from core.scheduler import delete_task
        if delete_task(task_name):
            self._log_viewer.append(f"🗑️ 已删除计划任务 [{task_name}]", "INFO")
        self._refresh_schedule_status()

    def _save_config(self):
        self.config.update(self._read_config_from_ui())
        from config_manager import save_config
        if save_config(self.config):
            self._log_viewer.append("💾 配置已保存到 config.json", "SUCCESS")
            self._save_splitter_pos()
            # 同步计划任务
            from core.scheduler import create_daily_task, task_exists, delete_task
            if self.config.get("schedule_enabled", False):
                create_daily_task(self.config)
            else:
                tn = self.config.get("schedule_task_name", "GameAutoDaily")
                if task_exists(tn):
                    delete_task(tn)
            self._refresh_schedule_status()
        else:
            self._log_viewer.append("❌ 配置保存失败", "ERROR")

    def _reset_config(self):
        if messagebox.askyesno("确认", "确定要恢复默认配置吗？当前配置将被覆盖。"):
            from config_manager import DEFAULT_CONFIG
            import copy
            self.config = copy.deepcopy(DEFAULT_CONFIG)
            self._log_viewer.append("🔄 已恢复默认配置（请点击保存以持久化）", "WARN")

    def _start_task(self):
        if self._TaskRunner is None:
            messagebox.showerror(
                "启动失败",
                f"核心模块加载失败。\n错误: {self._import_error}\n请确认项目文件完整。"
            )
            return

        self.config.update(self._read_config_from_ui())
        from config_manager import save_config, validate_config
        save_config(self.config)

        errors = validate_config(self.config)
        if errors:
            messagebox.showwarning("配置问题", f"请先修正以下问题：\n\n" + "\n".join(errors))
            return

        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._status_label.configure(text="● 运行中", text_color=COLORS["warning"])
        self._log_viewer.clear()

        self._runner = self._TaskRunner(
            config=self.config,
            log_callback=self._on_log,
            status_callback=self._on_status_change,
        )
        self._runner.start()

    def _stop_task(self):
        """停止任务（非阻塞：发信号后轮询等待线程结束）"""
        if self._runner:
            self._log_viewer.append("⏹️ 正在停止任务...", "WARN")
            self._runner.stop()
            self._stop_btn.configure(state="disabled")
            self._status_label.configure(text="● 停止中...", text_color=COLORS["warning"])
            self._poll_stop()

    def _poll_stop(self):
        """轮询检查任务线程是否已退出"""
        if self._runner and self._runner.is_running():
            self.after(300, self._poll_stop)
        else:
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._status_label.configure(text="● 已停止", text_color=COLORS["text_dim"])
            self._log_viewer.append("⏹️ 任务已停止", "INFO")

    def _on_log(self, message, level="INFO"):
        self.after(0, lambda: self._log_viewer.append(message, level))

    def _on_status_change(self, status):
        if status == "finished":
            self.after(0, lambda: self._start_btn.configure(state="normal"))
            self.after(0, lambda: self._stop_btn.configure(state="disabled"))
            self.after(0, lambda: self._status_label.configure(
                text="● 完成", text_color=COLORS["success"]))

    def _clear_log(self):
        self._log_viewer.clear()

    def _on_close(self):
        if self._runner and self._runner.is_running():
            if messagebox.askyesno("确认", "任务正在运行中，确定退出吗？"):
                self._runner.stop()
            else:
                return
        self._save_splitter_pos()
        self.destroy()


def launch_gui(config: dict = None):
    if config is None:
        from config_manager import load_config
        config = load_config()
    app = GameAutoGUI(config)
    app.mainloop()
