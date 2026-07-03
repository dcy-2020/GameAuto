"""历史记录与告警管理模块"""
import json
import os
from typing import List


class HistoryManager:
    def __init__(self, config: dict, logger=None):
        self.config = config
        self.logger = logger
        self.history_file = os.path.join(config.get("report_log_path", ""), "auto_history.json")
        self.history = self._load_history()

    def _load_history(self) -> dict:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "ww_failures": 0,
            "ef_failures": 0,
            "ww_avg_time": 0.0,
            "ef_avg_time": 0.0,
            "run_count": 0
        }

    def _save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            if self.logger:
                self.logger.log(f"⚠️ 保存历史记录失败: {e}", level="WARN")

    def update_and_check(self, ww_success: bool, ef_success: bool, ww_cost: float, ef_cost: float,
                         ww_enabled: bool = True, ef_enabled: bool = True) -> List[str]:
        alarms = []
        FAILURE_THRESHOLD = 2

        if ww_enabled and not ww_success:
            self.history["ww_failures"] += 1
            if self.history["ww_failures"] >= FAILURE_THRESHOLD:
                alarms.append(f"🚨 **[紧急] 鸣潮已连续 {self.history['ww_failures']} 次运行失败！请立即人工介入检查。**")
        elif ww_enabled and ww_success:
            self.history["ww_failures"] = 0

        if ef_enabled and not ef_success:
            self.history["ef_failures"] += 1
            if self.history["ef_failures"] >= FAILURE_THRESHOLD:
                alarms.append(f"🚨 **[紧急] 终末地已连续 {self.history['ef_failures']} 次运行失败！请立即人工介入检查。**")
        elif ef_enabled and ef_success:
            self.history["ef_failures"] = 0

        TIME_SPIKE_RATIO = 3.0
        if ww_enabled and ww_success and self.history["run_count"] > 0:
            avg_ww = self.history["ww_avg_time"]
            if avg_ww > 0 and ww_cost > (avg_ww * TIME_SPIKE_RATIO):
                alarms.append(f"⚠️ **[警告] 鸣潮本次耗时 ({ww_cost/60:.1f}分钟) 异常，远超历史平均 ({avg_ww/60:.1f}分钟)！**")
        if ef_enabled and ef_success and self.history["run_count"] > 0:
            avg_ef = self.history["ef_avg_time"]
            if avg_ef > 0 and ef_cost > (avg_ef * TIME_SPIKE_RATIO):
                alarms.append(f"⚠️ **[警告] 终末地本次耗时 ({ef_cost/60:.1f}分钟) 异常，远超历史平均 ({avg_ef/60:.1f}分钟)！**")

        if (ww_enabled and ww_success) and (ef_enabled and ef_success):
            count = self.history["run_count"]
            self.history["ww_avg_time"] = (self.history["ww_avg_time"] * count + ww_cost) / (count + 1)
            self.history["ef_avg_time"] = (self.history["ef_avg_time"] * count + ef_cost) / (count + 1)
            self.history["run_count"] += 1

        self._save_history()
        return alarms