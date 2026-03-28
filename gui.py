import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
import time
import json
import subprocess
import concurrent.futures
import queue
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta
from downloader import (
    download_by_date,
    _split_program_name,
    _sanitize_component_for_path,
    _render_filename_template,
    _build_output_file_path,
)
from converter import check_ffmpeg_path, build_ffmpeg_cmd

CONFIG_FILE = "config.json"

class StopDownloadException(Exception):
    # 统一用于下载/转换线程的可控中断，避免直接抛出通用异常导致日志不清晰。
    pass

class RedirectText:
    # 将 print / traceback 重定向到 Tk 文本框。
    # 通过 dash_start 标记，把新日志插在“仪表盘动态区”之前，避免覆盖实时面板。
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.text_widget.configure(state="normal")
        self.text_widget.mark_set("dash_start", tk.END)
        self.text_widget.mark_gravity("dash_start", tk.RIGHT)
        
    def write(self, string):
        self.text_widget.insert("dash_start", string)
        self.text_widget.see("dash_start")
        self.text_widget.update_idletasks()
        
    def flush(self):
        pass


class CpuSampler:
    # 轻量级 CPU 采样器：Windows 使用 GetSystemTimes，其他平台回退到 loadavg 估算。
    def __init__(self):
        self._is_windows = (os.name == "nt")
        self._prev = self._read_windows_times() if self._is_windows else None

    @staticmethod
    def _ft_to_int(ft):
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    def _read_windows_times(self):
        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        )
        if not ok:
            return None
        return (
            self._ft_to_int(idle),
            self._ft_to_int(kernel),
            self._ft_to_int(user),
        )

    def get_percent(self):
        if self._is_windows:
            curr = self._read_windows_times()
            if curr is None:
                return 0.0
            if self._prev is None:
                self._prev = curr
                return 0.0

            idle_prev, kernel_prev, user_prev = self._prev
            idle_curr, kernel_curr, user_curr = curr
            self._prev = curr

            idle_delta = idle_curr - idle_prev
            kernel_delta = kernel_curr - kernel_prev
            user_delta = user_curr - user_prev
            total = kernel_delta + user_delta
            if total <= 0:
                return 0.0

            busy = max(total - idle_delta, 0)
            return min(100.0, (busy * 100.0) / total)

        if hasattr(os, "getloadavg") and os.cpu_count():
            return min(100.0, max(0.0, os.getloadavg()[0] * 100.0 / os.cpu_count()))
        return 0.0

class YunTingDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("云听电台下载器")
        self.root.geometry("850x700")
        
        self.mode_var = tk.StringVar(value="single")
        self.start_date_var = tk.StringVar(value=datetime.now().strftime("%y-%m-%d"))
        self.end_date_var = tk.StringVar(value=datetime.now().strftime("%y-%m-%d"))
        self.broadcast_id_var = tk.StringVar(value="662")
        self.output_dir_var = tk.StringVar(value="downloads")
        self.delay_var = tk.StringVar(value="1.5")
        self.api_key_var = tk.StringVar(value="f0fc4c668392f9f9a447e48584c214ee")
        self.high_bitrate_var = tk.BooleanVar(value=True)
        self.download_images_var = tk.BooleanVar(value=True)
        self.name_filter_regex_var = tk.StringVar(value="")
        self.filename_template_var = tk.StringVar(value=r"{date}\{name}")
        self.filename_preview_var = tk.StringVar(value="")
        self.max_rate_kbps = 0
        
        self.ffmpeg_path_var = tk.StringVar(value="")
        self.convert_out_dir_var = tk.StringVar(value="")
        self.ffmpeg_status_var = tk.StringVar(value="检测中...")
        self.convert_format_var = tk.StringVar(value="opus")
        self.convert_bitrate_var = tk.StringVar(value="96")
        self.convert_sample_rate_var = tk.StringVar(value="0")
        self.convert_threads_var = tk.StringVar(value="0")
        self.overwrite_mode_var = tk.StringVar(value="跳过现有")
        self.embed_cover_var = tk.BooleanVar(value=True)
        self.auto_convert_var = tk.BooleanVar(value=False)
        self.delete_origin_var = tk.BooleanVar(value=False)
        
        self.manual_convert_mode = tk.StringVar(value="auto")
        self.manual_convert_path = tk.StringVar(value="")
        
        # 运行态状态机：
        # - is_downloading 表示当前是否存在下载或转换任务。
        # - pause_event 控制暂停/恢复。
        # - stop_level: 0运行中, 1软停止, 2强制停止。
        # - stop_convert_level: 手动转换独立的两级停止控制。
        self.is_downloading = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_level = 0
        self.stop_convert_level = 0
        self.ffmpeg_valid = False
        self.ffmpeg_exe = ""
        
        # tasks 同时用于自动转换队列和手动批量转换，用于驱动 FFmpeg 仪表盘。
        self.tasks = []
        self.is_monitoring = False
        self.ffmpeg_history_lines = []
        self.max_pending_preview = 2
        self.speed_var = tk.StringVar(value="下载速率 0.00MB/s")
        self.cpu_var = tk.StringVar(value="CPU使用率 0%")
        self.metrics_lock = threading.Lock()
        self.downloaded_bytes_total = 0
        self.last_speed_bytes = 0
        self.last_speed_ts = time.time()
        self.cpu_sampler = CpuSampler()
        self.metrics_running = True
        
        self.load_config()
        self.setup_ui()
        self.bind_preview_traces()
        self.update_filename_preview()
        self.after_init_check()
        self.schedule_metrics_refresh()
        
        self.initial_config = self.get_config_dict()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def get_config_dict(self):
        # 汉字转为数字（向后兼容配置）
        ow_map_inv = {"跳过现有": 0, "仅覆盖0kb": 1, "全部覆盖": 2}
        try:
            ow_mode = ow_map_inv[self.overwrite_mode_var.get().strip()]
        except KeyError:
            ow_mode = 0
            
        return {
            "broadcast_id": self.broadcast_id_var.get().strip(),
            "output_dir": self.output_dir_var.get().strip(),
            "delay": float(self.delay_var.get().strip() or 1.5),
            "max_rate_kbps": int(self.max_rate_kbps),
            "api_key": self.api_key_var.get().strip(),
            "high_bitrate": self.high_bitrate_var.get(),
            "download_images": self.download_images_var.get(),
            "name_filter_regex": self.name_filter_regex_var.get(),
            "filename_template": self.filename_template_var.get(),
            "ffmpeg_path": self.ffmpeg_path_var.get().strip(),
            "convert_out_dir": self.convert_out_dir_var.get().strip(),
            "convert_format": self.convert_format_var.get().strip(),
            "convert_bitrate": self.convert_bitrate_var.get().strip(),
            "convert_sample_rate": self.convert_sample_rate_var.get().strip(),
            "convert_threads": self.convert_threads_var.get().strip(),
            "overwrite_mode": ow_mode,
            "embed_cover": self.embed_cover_var.get(),
            "auto_convert": self.auto_convert_var.get(),
            "delete_origin": self.delete_origin_var.get()
        }

    def on_closing(self):
        # 停止指标定时器，避免窗口销毁后仍有 after 回调。
        self.metrics_running = False
        if self.is_downloading or (getattr(self, "auto_convert_queue", None) is not None and not self.auto_convert_queue.empty()):
            if not messagebox.askyesno("退出提示", "有任务正在后台运行，强制退出可能导致文件损坏。\n确定要退出吗？"):
                return
            self.stop_level = 2
            self.pause_event.set()
            
        current_config = self.get_config_dict()
        if current_config != self.initial_config:
            ans = messagebox.askyesnocancel("保存配置", "您的配置已被修改，是否在退出前保存？")
            if ans is True:
                self.save_config()
            elif ans is None:
                return  # 取消关闭
                
        self.root.destroy()
        
    def load_config(self):
        # 兼容旧配置加载
        ow_map = {0: "跳过现有", 1: "仅覆盖0kb", 2: "全部覆盖"}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.broadcast_id_var.set(config.get("broadcast_id", "662"))
                    
                    # 尝试保留相对路径
                    out_dir = config.get("output_dir", "downloads")
                    self.output_dir_var.set(out_dir)
                    
                    self.delay_var.set(str(config.get("delay", 1.5)))
                    try:
                        self.max_rate_kbps = int(config.get("max_rate_kbps", 0) or 0)
                    except Exception:
                        self.max_rate_kbps = 0
                    self.api_key_var.set(config.get("api_key", "f0fc4c668392f9f9a447e48584c214ee"))
                    self.high_bitrate_var.set(config.get("high_bitrate", True))
                    self.download_images_var.set(config.get("download_images", True))
                    self.name_filter_regex_var.set(config.get("name_filter_regex", ""))
                    self.filename_template_var.set(config.get("filename_template", r"{date}\{name}"))
                    self.ffmpeg_path_var.set(config.get("ffmpeg_path", ""))
                    
                    conv_dir = config.get("convert_out_dir", "")
                    self.convert_out_dir_var.set(conv_dir)
                    
                    self.convert_format_var.set(config.get("convert_format", "opus"))
                    self.convert_bitrate_var.set(config.get("convert_bitrate", "96"))
                    self.convert_sample_rate_var.set(config.get("convert_sample_rate", "0"))
                    self.convert_threads_var.set(config.get("convert_threads", "0"))
                    
                    ow_val = config.get("overwrite_mode", 0)
                    if isinstance(ow_val, str) and ow_val in ow_map.values():
                        self.overwrite_mode_var.set(ow_val)
                    else:
                        self.overwrite_mode_var.set(ow_map.get(ow_val, "跳过现有"))
                        
                    self.embed_cover_var.set(config.get("embed_cover", True))
                    self.auto_convert_var.set(config.get("auto_convert", False))
                    self.delete_origin_var.set(config.get("delete_origin", False))
            except Exception as e:
                print(f"读取配置文件失败: {e}")
        else:
            self.output_dir_var.set("downloads")
            self.max_rate_kbps = 0

    def save_config(self):
        config = self.get_config_dict()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.initial_config = config
        except Exception as e:
            print(f"保存配置文件失败: {e}")

    def after_init_check(self):
        self.verify_ffmpeg_path(quiet=True)

    def verify_ffmpeg_path(self, quiet=False):
        # 允许用户给目录或直接依赖 PATH，check_ffmpeg_path 负责兜底查找逻辑。
        valid, fp = check_ffmpeg_path(self.ffmpeg_path_var.get().strip())
        self.ffmpeg_valid = valid
        if valid:
            self.ffmpeg_exe = fp
            self.ffmpeg_status_var.set("状态: 已找到FFmpeg 👍")
            if hasattr(self, 'ffmpeg_status_label'):
                self.ffmpeg_status_label.config(foreground="green")
            if not quiet:
                messagebox.showinfo("检测成功", f"成功定位有效FFmpeg可执行文件：\n{fp}")
        else:
            self.ffmpeg_exe = ""
            self.ffmpeg_status_var.set("状态: 未找到FFmpeg ❌")
            if hasattr(self, 'ffmpeg_status_label'):
                self.ffmpeg_status_label.config(foreground="red")
            if not quiet:
                messagebox.showwarning("无效目录", "在该目录下或环境变量中未检测到FFmpeg!\n请确保选择包含了ffmpeg的目录，或者已正确配置系统环境变量。")

    def toggle_ffmpeg_test(self):
        self.verify_ffmpeg_path(quiet=False)

    def setup_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tab_download = ttk.Frame(notebook)
        tab_convert = ttk.Frame(notebook)
        
        notebook.add(tab_download, text="⬇ 下载控制")
        notebook.add(tab_convert, text="⚙ 格式转换设置")
        
        dl_params_frame = ttk.LabelFrame(tab_download, text="基本参数", padding="10")
        dl_params_frame.pack(fill=tk.X, padx=5, pady=5)
        
        mode_frame = ttk.Frame(dl_params_frame)
        mode_frame.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 5))
        ttk.Label(mode_frame, text="模式:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="单日", variable=self.mode_var, value="single", command=self.update_ui_state).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="日期范围", variable=self.mode_var, value="range", command=self.update_ui_state).pack(side=tk.LEFT, padx=10)
        
        self.date_label = ttk.Label(dl_params_frame, text="日期 (YY-MM-DD):")
        self.date_label.grid(row=1, column=0, sticky=tk.W, pady=2)
        self.start_date_entry = ttk.Entry(dl_params_frame, textvariable=self.start_date_var, width=15)
        self.start_date_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        self.end_date_label = ttk.Label(dl_params_frame, text="结束日期:")
        self.end_date_label.grid(row=1, column=2, sticky=tk.W, padx=(10,0), pady=2)
        self.end_date_entry = ttk.Entry(dl_params_frame, textvariable=self.end_date_var, width=15, state="disabled")
        self.end_date_entry.grid(row=1, column=3, sticky=tk.W, pady=2)
        
        ttk.Label(dl_params_frame, text="电台ID:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.broadcast_id_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=2)
        ttk.Label(dl_params_frame, text="下载延迟(秒):").grid(row=2, column=2, sticky=tk.W, padx=(10,0), pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.delay_var, width=15).grid(row=2, column=3, sticky=tk.W, pady=2)
        
        ttk.Label(dl_params_frame, text="API Key(不建议修改):").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.api_key_var, width=42).grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=2)
        
        ttk.Label(dl_params_frame, text="下载保存目录:").grid(row=4, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.output_dir_var, width=33).grid(row=4, column=1, columnspan=2, sticky=tk.W, pady=2)
        ttk.Button(dl_params_frame, text="浏览...", command=self.browse_output_dir).grid(row=4, column=3, sticky=tk.W, padx=5)

        ttk.Label(dl_params_frame, text="节目筛选正则:").grid(row=5, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.name_filter_regex_var, width=42).grid(row=5, column=1, columnspan=3, sticky=tk.W, pady=2)

        ttk.Label(dl_params_frame, text="文件名模板:").grid(row=6, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dl_params_frame, textvariable=self.filename_template_var, width=42).grid(row=6, column=1, columnspan=3, sticky=tk.W, pady=2)

        ttk.Label(dl_params_frame, text="预览示例:").grid(row=7, column=0, sticky=tk.W, pady=2)
        preview_entry = ttk.Entry(dl_params_frame, textvariable=self.filename_preview_var, width=42, state="readonly")
        preview_entry.grid(row=7, column=1, columnspan=3, sticky=tk.W, pady=2)

        options_frame = ttk.Frame(dl_params_frame)
        options_frame.grid(row=8, column=0, columnspan=4, sticky=tk.W, pady=(5,0))
        ttk.Checkbutton(options_frame, text="下载高码率", variable=self.high_bitrate_var).pack(side=tk.LEFT, padx=(0,15))
        ttk.Checkbutton(options_frame, text="下载封面图", variable=self.download_images_var).pack(side=tk.LEFT, padx=(0,15))
        ttk.Checkbutton(options_frame, text="下载后自动转换音频格式(需配置FFmpeg)", variable=self.auto_convert_var).pack(side=tk.LEFT)
        
        control_frame = ttk.Frame(tab_download)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="▶ 开始下载", command=self.start_download_thread)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.pause_btn = ttk.Button(control_frame, text="⏸ 暂停", command=self.toggle_pause, state="disabled")
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="⏹ 停止", command=self.stop_download, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.save_btn = ttk.Button(control_frame, text="💾 保存所有配置", command=self.save_config_manual)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        
        log_paned = ttk.PanedWindow(tab_download, orient=tk.VERTICAL)
        log_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Download logs
        self.dl_log_frame = ttk.LabelFrame(log_paned, text="⬇ 系统日志", padding="5")
        log_paned.add(self.dl_log_frame, weight=1)

        metrics_row = ttk.Frame(self.dl_log_frame)
        metrics_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(metrics_row, text="实时:").pack(side=tk.LEFT)
        # 分离速率/CPU两个标签，并固定速率标签宽度，避免非等宽字体下的位移抖动。
        ttk.Label(metrics_row, textvariable=self.speed_var, width=18, anchor=tk.W).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(metrics_row, textvariable=self.cpu_var).pack(side=tk.LEFT, padx=(10, 0))
        
        self.log_text = tk.Text(self.dl_log_frame, wrap="word", width=40, height=10)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(self.dl_log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # FFmpeg logs
        ff_log_frame = ttk.LabelFrame(log_paned, text="⚙ FFmpeg转换日志", padding="5")
        log_paned.add(ff_log_frame, weight=1)
        
        self.ffmpeg_text = tk.Text(ff_log_frame, wrap="word", width=40, height=10)
        self.ffmpeg_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ffmpeg_scrollbar = ttk.Scrollbar(ff_log_frame, command=self.ffmpeg_text.yview)
        ffmpeg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ffmpeg_text.configure(yscrollcommand=ffmpeg_scrollbar.set)
        
        # Add marks for dashboard view
        self.ffmpeg_text.mark_set("dash_start", "end-1c")
        self.ffmpeg_text.mark_gravity("dash_start", tk.LEFT)
        
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)

        cv_env_frame = ttk.LabelFrame(tab_convert, text="环境检测", padding="10")
        cv_env_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(cv_env_frame, text="自定义FFmpeg目录:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cv_env_frame, textvariable=self.ffmpeg_path_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Button(cv_env_frame, text="浏览", command=self.browse_ffmpeg_dir).grid(row=0, column=2, sticky=tk.W, padx=2)
        ttk.Button(cv_env_frame, text="测试", command=self.toggle_ffmpeg_test).grid(row=0, column=3, sticky=tk.W, padx=5)
        self.ffmpeg_status_label = ttk.Label(cv_env_frame, textvariable=self.ffmpeg_status_var, font=("", 10, "bold"))
        self.ffmpeg_status_label.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(5,0))
        
        cv_opt_frame = ttk.LabelFrame(tab_convert, text="转换参数", padding="10")
        cv_opt_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(cv_opt_frame, text="目标格式:").grid(row=0, column=0, sticky=tk.W, pady=2)
        format_cb = ttk.Combobox(cv_opt_frame, textvariable=self.convert_format_var, values=["opus", "mp3", "m4a", "aac"], width=8)
        format_cb.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        ttk.Label(cv_opt_frame, text="目标码率(k):").grid(row=0, column=2, sticky=tk.W, padx=(10,0), pady=2)
        bitrate_cb = ttk.Combobox(cv_opt_frame, textvariable=self.convert_bitrate_var, values=["32", "48", "64", "80", "96", "128", "192", "256", "320"], width=8)
        bitrate_cb.grid(row=0, column=3, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(cv_opt_frame, text="转换线程数(0=自动):").grid(row=1, column=0, sticky=tk.W, pady=2)
        threads_cb = ttk.Combobox(cv_opt_frame, textvariable=self.convert_threads_var, values=["0", "1", "2", "4", "8", "12", "16", "20"], width=8)
        threads_cb.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(cv_opt_frame, text="采样率(0=保持):").grid(row=1, column=2, sticky=tk.W, padx=(10,0), pady=2)
        sr_cb = ttk.Combobox(cv_opt_frame, textvariable=self.convert_sample_rate_var, values=["0", "48000", "44100", "24000", "16000"], width=8)
        sr_cb.grid(row=1, column=3, sticky=tk.W, pady=2, padx=5)

        ttk.Label(cv_opt_frame, text="覆盖模式:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ow_cb = ttk.Combobox(cv_opt_frame, textvariable=self.overwrite_mode_var, values=["跳过现有", "仅覆盖0kb", "全部覆盖"], width=12, state="readonly")
        ow_cb.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(cv_opt_frame, text="自定义输出目录(留空为原):").grid(row=2, column=2, sticky=tk.W, pady=2)
        ttk.Entry(cv_opt_frame, textvariable=self.convert_out_dir_var, width=28).grid(row=2, column=3, columnspan=2, sticky=tk.W, pady=2, padx=5)
        ttk.Button(cv_opt_frame, text="浏览", command=self.browse_convert_out_dir).grid(row=2, column=5, sticky=tk.W, padx=2)
        
        ttk.Checkbutton(cv_opt_frame, text="若存在同名图片，尝试作为专辑封面嵌入音频中(只适用于使用本工具下载的封面，即保存位置在`下载目录/images` 内部的图片)", variable=self.embed_cover_var).grid(row=3, column=0, columnspan=6, sticky=tk.W, pady=(5,0))
        ttk.Checkbutton(cv_opt_frame, text="转换成功后删除原文件 (危险!)", variable=self.delete_origin_var).grid(row=4, column=0, columnspan=6, sticky=tk.W, pady=(5,0))
        
        cv_manual_frame = ttk.LabelFrame(tab_convert, text="手动批处理转换区", padding="10")
        cv_manual_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        rmode_frame = ttk.Frame(cv_manual_frame)
        rmode_frame.pack(fill=tk.X, pady=2)
        ttk.Radiobutton(rmode_frame, text="自动扫描", variable=self.manual_convert_mode, value="auto", command=self.update_manual_ui).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(rmode_frame, text="全局目录", variable=self.manual_convert_mode, value="root", command=self.update_manual_ui).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(rmode_frame, text="单日目录", variable=self.manual_convert_mode, value="date", command=self.update_manual_ui).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(rmode_frame, text="单文件", variable=self.manual_convert_mode, value="file", command=self.update_manual_ui).pack(side=tk.LEFT, padx=5)
        
        self.mc_target_frame = ttk.Frame(cv_manual_frame)
        self.mc_target_frame.pack(fill=tk.X, pady=5)
        ttk.Label(self.mc_target_frame, text="目标路径/日期:").pack(side=tk.LEFT)
        self.mc_path_entry = ttk.Entry(self.mc_target_frame, textvariable=self.manual_convert_path, width=40)
        self.mc_path_entry.pack(side=tk.LEFT, padx=5)
        self.mc_browse_btn = ttk.Button(self.mc_target_frame, text="浏览...", command=self.browse_for_manual_convert)
        self.mc_browse_btn.pack(side=tk.LEFT)
        
        action_frame = ttk.Frame(cv_manual_frame)
        action_frame.pack(fill=tk.X, pady=5)
        self.generate_btn = ttk.Button(action_frame, text="1. 预先生成命令", command=self.generate_commands)
        self.generate_btn.pack(side=tk.LEFT, padx=5)
        self.run_cmd_btn = ttk.Button(action_frame, text="2. 运行下方命令", command=self.start_manual_exec_thread)
        self.run_cmd_btn.pack(side=tk.LEFT, padx=5)
        self.stop_cmd_btn = ttk.Button(action_frame, text="⏹ 停止转换", command=self.stop_manual_exec, state="disabled")
        self.stop_cmd_btn.pack(side=tk.LEFT, padx=5)
        
        self.cmd_frame = ttk.LabelFrame(cv_manual_frame, text="命令编辑区 (可自由查看并删改终端指令)", padding="5")
        self.cmd_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.cmd_text = tk.Text(self.cmd_frame, wrap="word", height=6)
        self.cmd_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cmd_scroll = ttk.Scrollbar(self.cmd_frame, command=self.cmd_text.yview)
        cmd_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cmd_text.configure(yscrollcommand=cmd_scroll.set)
        
        self.update_manual_ui()

    def update_ui_state(self):
        if self.mode_var.get() == "single":
            self.end_date_entry.config(state="disabled")
            self.date_label.config(text="日期:")
        else:
            self.end_date_entry.config(state="normal")
            self.date_label.config(text="开始日期:")

    def update_manual_ui(self):
        m = self.manual_convert_mode.get()
        if m in ["auto", "root"]:
            self.mc_path_entry.config(state="disabled")
            self.mc_browse_btn.config(state="disabled")
        else:
            self.mc_path_entry.config(state="normal")
            self.mc_browse_btn.config(state="normal")

    def bind_preview_traces(self):
        for var in [self.output_dir_var, self.start_date_var, self.filename_template_var, self.high_bitrate_var]:
            var.trace_add("write", lambda *_: self.update_filename_preview())

    def update_filename_preview(self):
        try:
            raw_date = self.start_date_var.get().strip()
            try:
                formatted_date = datetime.strptime(raw_date, "%y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                formatted_date = datetime.now().strftime("%Y-%m-%d")

            sample_name = "Morning Call 音乐叫早"
            sample_en, sample_ch = _split_program_name(sample_name)

            values = {
                "id": "1",
                "name": _sanitize_component_for_path(sample_name),
                "date": _sanitize_component_for_path(formatted_date),
                "name_ch": _sanitize_component_for_path(sample_ch),
                "name_en": _sanitize_component_for_path(sample_en),
                "bitrate": "High" if self.high_bitrate_var.get() else "Low",
                "start_time": _sanitize_component_for_path("06:00:00"),
                "end_time": _sanitize_component_for_path("07:00:00"),
            }

            template = self.filename_template_var.get().strip() or r"{date}\{name}"
            rendered = _render_filename_template(template, values)
            base_dir = self.output_dir_var.get().strip() or "downloads"
            preview_path = _build_output_file_path(
                base_downloads_dir=base_dir,
                template_rendered=rendered,
                download_url="https://example.com/sample.m4a",
                fallback_date=formatted_date,
                fallback_name=_sanitize_component_for_path(sample_name),
            )
            self.filename_preview_var.set(preview_path)
        except Exception as e:
            self.filename_preview_var.set(f"预览失败: {e}")

    def browse_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if d: self.output_dir_var.set(d)
            
    def browse_ffmpeg_dir(self):
        d = filedialog.askdirectory(initialdir=self.ffmpeg_path_var.get() or os.getcwd())
        if d: 
            self.ffmpeg_path_var.set(d)
            self.verify_ffmpeg_path(quiet=False)

    def browse_convert_out_dir(self):
        d = filedialog.askdirectory(initialdir=self.convert_out_dir_var.get() or self.output_dir_var.get())
        if d: self.convert_out_dir_var.set(d)

    def browse_for_manual_convert(self):
        m = self.manual_convert_mode.get()
        base = self.output_dir_var.get()
        if m == "file":
            f = filedialog.askopenfilename(initialdir=base, filetypes=[("音频", "*.m4a *.mp3 *.aac")])
            if f: self.manual_convert_path.set(f)
        else:
            d = filedialog.askdirectory(initialdir=base)
            if d: self.manual_convert_path.set(d)

    def save_config_manual(self):
        self.save_config()
        print("======> 配置已全量保存至 config.json <======")

    # ---------------- 状态与中断处理 -----------------
    def check_state(self, is_chunk=False):
        # 统一的“协作式中断点”：下载循环、延迟等待、网络分块都会调用这里。
        # is_chunk=True 时允许当前文件内继续处理中间块；False 时可按软停止退出下一任务。
        if self.stop_level == 2:
            raise StopDownloadException("强制拦截任务!")
        if self.stop_level == 1 and not is_chunk:
            raise StopDownloadException("操作取消.")
            
        if not self.pause_event.is_set():
            self.pause_event.wait()
            if self.stop_level == 2:
                raise StopDownloadException("强制拦截任务!")
            if self.stop_level == 1 and not is_chunk:
                raise StopDownloadException("操作取消.")

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="恢复")
            print("\n[ 系统：已请求暂停... ]")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="暂停")
            print("\n[ 系统：恢复执行 ]")

    def stop_download(self):
        if not self.is_downloading: return
        # 两段式停止：第一次只阻止后续任务，第二次强杀当前子进程。
        if self.stop_level == 0:
            self.stop_level = 1
            self.stop_btn.config(text="强制停止")
            self.pause_event.set()
            print("\n[ 系统：已取消后续下载进程，再次点击终止当前下载进程... ]")
        elif self.stop_level == 1:
            self.stop_level = 2
            self.stop_btn.config(state="disabled", text="终止中...")
            self.pause_event.set()
            for t in getattr(self, 'tasks', []):
                if 'proc' in t and t['proc'] and t['proc'].poll() is None:
                    try: t['proc'].kill()
                    except: pass
            print("\n[ 系统：已强制终止当前下载进程，正在清除下载缓存... ]")

    def stop_manual_exec(self):
        if not self.is_downloading: return
        self.run_cmd_btn.config(state="disabled")
        # 手动批处理也采用两段式停止，避免误触直接中断当前 ffmpeg 进程。
        if self.stop_convert_level == 0:
            self.stop_convert_level = 1
            self.stop_cmd_btn.config(text="强制停止(二次点击)")
            self.pause_event.set()
            print("\n[ 系统：已请求停止后续转换队列... ]")
            self.root.after(0, lambda: self.cmd_text.insert(tk.END, "\n# 已请求停止后续队列..."))
            if hasattr(self, 'ffmpeg_text'):
                self.root.after(0, lambda: self.ffmpeg_text.insert(tk.END, "\n# 已请求停止后续队列..."))
        elif self.stop_convert_level == 1:
            self.stop_convert_level = 2
            self.stop_cmd_btn.config(state="disabled", text="终止中...")
            self.pause_event.set()
            for t in getattr(self, 'tasks', []):
                if 'proc' in t and t['proc'] and t['proc'].poll() is None:
                    try: t['proc'].kill()
                    except: pass
            print("\n[ 系统：已强制终止当前转换进程... ]")
            self.root.after(0, lambda: self.cmd_text.insert(tk.END, "\n# 正在强制终止进程..."))
            if hasattr(self, 'ffmpeg_text'):
                self.root.after(0, lambda: self.ffmpeg_text.insert(tk.END, "\n# 正在强制终止进程..."))

    def reset_buttons(self):
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="暂停")
        self.stop_btn.config(state="disabled", text="停止")
        self.generate_btn.config(state="normal")
        self.run_cmd_btn.config(state="normal")
        self.stop_cmd_btn.config(state="disabled", text="⏹ 停止转换")
        self.cmd_frame.config(text="命令编辑区 (可自由查看并删改终端指令)")

    # ---------------- 下载与自动转换 -----------------
    def start_download_thread(self):
        if self.is_downloading: return
        self.save_config()
        self.verify_ffmpeg_path(quiet=True)
        
        # Check Opus + Sample rate warning for auto convert
        if self.auto_convert_var.get():
            fmt = self.convert_format_var.get().strip()
            sr = self.convert_sample_rate_var.get().strip()
            if fmt.lower() == 'opus' and sr not in ["0", "48000", "24000", "16000", "12000", "8000"]:
                messagebox.showwarning("兼容性提示", f"已开启自动转换。\n\nOpus 格式要求特定的采样率（如 48000, 24000, 16000 等）。\n您当前选择了 {sr} 采样率，FFmpeg 在执行时可能会报错退出。")

        self.is_downloading = True
        self.stop_level = 0
        self.pause_event.set()
        
        self.start_btn.config(state="disabled")
        self.generate_btn.config(state="disabled")
        self.run_cmd_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        
        self.log_text.delete(1.0, tk.END)
        # 指标统计在每次任务开始时归零，避免混入上次会话的数据。
        with self.metrics_lock:
            self.downloaded_bytes_total = 0
            self.last_speed_bytes = 0
        self.last_speed_ts = time.time()
        self.tasks = []
        self.ffmpeg_history_lines = []
        self.is_monitoring = False
        if hasattr(self, 'ffmpeg_text'):
            self.ffmpeg_text.delete("1.0", tk.END)
        print("="*40 + "\n启动自动化下载管线流\n" + "="*40)
        
        if self.auto_convert_var.get() and self.ffmpeg_valid:
            # 自动转换采用生产者-消费者模型：下载回调负责入队，后台 worker 负责执行 ffmpeg。
            self.auto_convert_queue = queue.Queue()
            workers_str = self.convert_threads_var.get()
            workers = int(workers_str) if workers_str.isdigit() and int(workers_str) > 0 else (os.cpu_count() or 4)
            self.num_workers = workers
            for _ in range(workers):
                threading.Thread(target=self.auto_convert_worker, daemon=True).start()
            if not getattr(self, 'is_monitoring', False):
                self.is_monitoring = True
                self.refresh_dashboard()
        else:
            self.auto_convert_queue = None

        threading.Thread(target=self.run_download, daemon=True).start()

    def run_download(self):
        try:
            mode = self.mode_var.get()
            start_date_str = self.start_date_var.get().strip()
            broadcast_id = self.broadcast_id_var.get().strip()
            base_dir = self.output_dir_var.get().strip()
            delay = float(self.delay_var.get().strip())
            api_key = self.api_key_var.get().strip()
            is_high_bitrate = self.high_bitrate_var.get()
            is_download_imgs = self.download_images_var.get()
            name_filter_regex = self.name_filter_regex_var.get().strip()
            filename_template = self.filename_template_var.get().strip() or r"{date}\{name}"
            max_rate_kbps = self.max_rate_kbps
            
            post_cb = self.auto_converter_callback if self.auto_convert_var.get() else None
            if post_cb and not self.ffmpeg_valid:
                print("[警告] 请求了自动转换但未配置FFmpeg！将忽略转换命令。")
                post_cb = None
                
            if mode == "single":
                self.check_state(is_chunk=False)
                self._run_downloader_wrapper(start_date_str, broadcast_id, base_dir, is_high_bitrate, is_download_imgs, api_key, post_cb, name_filter_regex, filename_template, max_rate_kbps)
            else:
                end_date_str = self.end_date_var.get().strip()
                start_date = datetime.strptime(start_date_str, "%y-%m-%d")
                end_date = datetime.strptime(end_date_str, "%y-%m-%d")
                
                curr = start_date
                while curr <= end_date:
                    self.check_state(is_chunk=False)
                    self._run_downloader_wrapper(curr.strftime("%y-%m-%d"), broadcast_id, base_dir, is_high_bitrate, is_download_imgs, api_key, post_cb, name_filter_regex, filename_template, max_rate_kbps)
                    curr += timedelta(days=1)
                    if curr <= end_date:
                        for _ in range(int(delay * 10)):
                            self.check_state(is_chunk=False)
                            time.sleep(0.1)
        except StopDownloadException as e:
            print(f"\n>>>> 任务安全切断: {e} <<<<")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n>>>> 未知异常捕获: {e}")
        finally:
            if getattr(self, "auto_convert_queue", None) is not None:
                w_count = getattr(self, 'num_workers', 4)
                # 每个 worker 投递一个哨兵，保证所有线程都能退出并让 queue.join() 正常返回。
                for _ in range(w_count):
                    self.auto_convert_queue.put(None)
                if getattr(self, 'stop_level', 0) < 2: 
                    print("\n[ 系统：下载爬取线程已结束，正等待后台转换队列处理剩余任务... ]")
                self.auto_convert_queue.join()
                self.auto_convert_queue = None

            if hasattr(self, 'stop_monitoring'): self.stop_monitoring()
            print("\n---------- 下载转换完成 ----------")
            self.is_downloading = False
            self.root.after(0, self.reset_buttons)
            
    def _run_downloader_wrapper(self, d_str, b_id, b_dir, h_bit, d_img, api, post_cb, name_filter_regex, filename_template, max_rate_kbps):
        download_by_date(
            date_str=d_str, broadcast_id=b_id, base_downloads_dir=b_dir, 
            high_bitrate=h_bit, download_imgs=d_img, api_key=api, 
            state_checker=self.check_state, post_process_cb=post_cb,
            download_progress_cb=self.on_download_progress,
            name_filter_regex=name_filter_regex,
            filename_template=filename_template,
            max_rate_kbps=max_rate_kbps,
        )

    def auto_converter_callback(self, filename, filepath, date_str):
        # 下载器在单个音频落盘后触发此回调，仅负责生成命令并入队，不阻塞主下载线程。
        if getattr(self, 'stop_level', 0) > 0: return
        base_root = self.output_dir_var.get().strip()
        cmd = self._build_cmd_for_file(filepath, base_root_for_rel=base_root)
        if cmd:
            cmd_str = subprocess.list2cmdline(cmd)
            if hasattr(self, 'auto_convert_queue') and self.auto_convert_queue:
                self.auto_convert_queue.put((cmd_str, filepath))
            else:
                # If queue not initialized correctly but FFmpeg should run
                pass

    def on_download_progress(self, chunk_size):
        # downloader 以 chunk 维度回调字节数，这里聚合到全局计数供速率计算。
        if not chunk_size:
            return
        with self.metrics_lock:
            self.downloaded_bytes_total += int(chunk_size)

    def schedule_metrics_refresh(self):
        if not self.metrics_running:
            return

        now = time.time()
        with self.metrics_lock:
            delta_bytes = self.downloaded_bytes_total - self.last_speed_bytes
            self.last_speed_bytes = self.downloaded_bytes_total

        dt = max(now - self.last_speed_ts, 1e-6)
        self.last_speed_ts = now

        speed_mbps = delta_bytes / dt / 1_000_000.0 if self.is_downloading else 0.0
        cpu_percent = self.cpu_sampler.get_percent()

        self.speed_var.set(f"下载速率 {speed_mbps:.2f}MB/s")
        self.cpu_var.set(f"CPU使用率 {int(round(cpu_percent))}%")
        self.root.after(1000, self.schedule_metrics_refresh)

    def stop_monitoring(self):
        self.is_monitoring = False
        self.root.after(0, self._render_ffmpeg_panel)

    def _build_dashboard_lines(self):
        # 仪表盘仅预览少量 pending，避免任务很多时刷屏影响可读性。
        dash_lines = []
        pending_count = 0
        tasks_ref = getattr(self, 'tasks', [])
        import os

        for t in tasks_ref:
            name = os.path.basename(t.get('file', '')) if t.get('file') else f"未知文件 {t.get('id', '?')}"
            status = t.get('status')

            if status == "running":
                progress = (t.get('progress', '') or '').strip()
                if not progress:
                    progress = f"{name} 转码中"
                dash_lines.append(f"[任务{t['id']}] 🚀 {name}  {progress}")
            elif status == "pending":
                if pending_count < self.max_pending_preview:
                    dash_lines.append(f"[任务{t['id']}] ⏳ {name} 等待转码")
                pending_count += 1

        if pending_count > self.max_pending_preview:
            dash_lines.append(f"...余下{pending_count - self.max_pending_preview}个任务...")

        return dash_lines

    def _render_ffmpeg_panel(self):
        if not hasattr(self, 'ffmpeg_text'):
            return

        lines = list(getattr(self, 'ffmpeg_history_lines', []))
        if getattr(self, 'is_monitoring', False):
            lines.extend(self._build_dashboard_lines())

        content = "\n".join(lines)
        if content:
            content += "\n"

        self.ffmpeg_text.delete("1.0", tk.END)
        if content:
            self.ffmpeg_text.insert("1.0", content)
        self.ffmpeg_text.see(tk.END)

    def refresh_dashboard(self):
        if not getattr(self, 'is_monitoring', False):
            return

        self.root.after(0, self._render_ffmpeg_panel)
        if getattr(self, 'is_monitoring', False):
            self.root.after(600, self.refresh_dashboard)

    def auto_convert_worker(self):
        # 后台消费者线程：持续取队列任务，遇到 None 哨兵后退出。
        while True:
            try:
                task_data = self.auto_convert_queue.get()
                if task_data is None:
                    self.auto_convert_queue.task_done()
                    break
                cmd_str, filepath = task_data
                if getattr(self, 'stop_level', 0) < 2:
                    t = {"id": len(self.tasks), "cmd": cmd_str, "file": filepath, "status": "pending", "progress": "初始化...", "start_time": 0, "end_time": 0}
                    self.tasks.append(t)
                    self._execute_task(t)
                self.auto_convert_queue.task_done()
            except Exception as e:
                print(f"[后台转换异常] {e}")

    def _report_task_finish(self, task, name):
        from datetime import datetime
        now_str = datetime.now().strftime("%H:%M:%S")
        if task['status'] == 'done':
            dt = int(task.get('end_time', 0) - task.get('start_time', 0))
            msg = f"[任务{task['id']}] {name} 完成 (耗时: {dt}秒)"
        else:
            msg = f"[任务{task['id']}] {name} 出错"
            
        def _op():
            self.ffmpeg_history_lines.append(msg)
            self._render_ffmpeg_panel()
        self.root.after(0, _op)

    def _execute_task(self, task):
        import time, subprocess, os
        # 单个 ffmpeg 任务执行入口：负责进程生命周期、暂停恢复、强制中断与状态汇报。
        task['status'] = 'running'
        task['start_time'] = time.time()
        task['reported'] = False
        name = os.path.basename(task['file']) if task.get('file') else f"未知文件 {task.get('id', '?')}"
        try:
            proc = subprocess.Popen(task['cmd'], shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, universal_newlines=True)
            task['proc'] = proc
            for line in proc.stdout:
                if getattr(self, 'stop_level', 0) == 2 or getattr(self, 'stop_convert_level', 0) == 2:
                    proc.kill()
                    task['status'], task['progress'] = 'error', '用户强制终止进程'
                    if not task.get('reported'):
                        self._report_task_finish(task, name)
                        task['reported'] = True
                    return
                if hasattr(self, 'pause_event') and not self.pause_event.is_set():
                    task['progress'] = '已暂停...'
                    self.pause_event.wait()
                    if getattr(self, 'stop_level', 0) == 2 or getattr(self, 'stop_convert_level', 0) == 2:
                        proc.kill()
                        task['status'] = 'error'
                        if not task.get('reported'):
                            self._report_task_finish(task, name)
                            task['reported'] = True
                        return
                l = line.strip("\r\n").strip()
                if not l: continue
                # 捕捉 ffmpeg 常见进度字段，截断后用于仪表盘实时显示。
                if '=' in l and any(k in l for k in ['size=', 'time=', 'frame=', 'bitrate=']): task['progress'] = l[:80]
                elif 'Error' in l or 'Invalid' in l: task['progress'] = '错误: ' + l[:80]
            proc.wait()
            task['end_time'] = time.time()
            if proc.returncode == 0:
                task['status'] = 'done'
                if self.delete_origin_var.get() and task.get('file') and os.path.exists(task['file']):
                    try: os.remove(task['file']); task['progress'] = '原文件已清理'
                    except: pass
            else: task['status'] = 'error'
        except Exception as e:
            task['status'], task['progress'], task['end_time'] = 'error', f'执行异常: {str(e)[:40]}', time.time()
            
        if not task.get('reported'):
            self._report_task_finish(task, name)
            task['reported'] = True

    # ---------------- 手动命令生成区 -------------------
    def scan_folder_for_audio(self, folder):
        res = []
        for file in os.listdir(folder):
            if file.lower().endswith((".m4a", ".aac", ".mp3")):
                res.append(os.path.join(folder, file))
        return res

    def _build_cmd_for_file(self, file_path, base_root_for_rel=None):
        base_dir = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        name_no_ext, _ = os.path.splitext(filename)
        
        fmt = self.convert_format_var.get()
        out_name = f"{name_no_ext}.{fmt}"
        
        custom_out = self.convert_out_dir_var.get().strip()
        if custom_out and base_root_for_rel:
            try:
                # 自定义输出目录时，尽量保留相对层级，便于和原下载目录对应。
                rel_path = os.path.relpath(base_dir, base_root_for_rel)
                out_dir = os.path.join(custom_out, rel_path)
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, out_name)
            except Exception:
                out_path = os.path.join(base_dir, out_name)
        else:
            out_path = os.path.join(base_dir, out_name)
        
        if file_path == out_path:
            return None

        ow_mode = self.overwrite_mode_var.get()
        if os.path.exists(out_path):
            if ow_mode == "跳过现有":
                return None
            elif ow_mode == "仅覆盖0kb":
                if os.path.getsize(out_path) > 0:
                    return None
            # if "全部覆盖", do nothing, proceed to build cmd

        cover_path = None
        if self.embed_cover_var.get():
            # 先找 date 同级 images 目录，找不到时回退到音频所在目录。
            img_dir = os.path.join(os.path.dirname(base_dir), "images")
            if not os.path.exists(img_dir): img_dir = base_dir 
            for p_ext in ['.jpg', '.jpeg', '.png']:
                t1 = os.path.join(img_dir, name_no_ext + p_ext)
                t2 = os.path.join(img_dir, name_no_ext + "_long" + p_ext)
                if os.path.exists(t1):
                    cover_path = t1; break
                if os.path.exists(t2):
                    cover_path = t2; break
        
        return build_ffmpeg_cmd(
            self.ffmpeg_exe, file_path, out_path, 
            fmt, self.convert_bitrate_var.get(), cover_path, 
            self.convert_threads_var.get(), self.convert_sample_rate_var.get()
        )

    def generate_commands(self):
        self.save_config()
        self.cmd_text.delete(1.0, tk.END)
        self.verify_ffmpeg_path(quiet=True)
        if not self.ffmpeg_valid:
            messagebox.showwarning("环境缺失", "找不到有效的 FFmpeg 路径，无法生成命令。")
            return
            
        fmt = self.convert_format_var.get().strip()
        sr = self.convert_sample_rate_var.get().strip()
        
        if fmt.lower() == 'opus' and sr not in ["0", "48000", "24000", "16000", "12000", "8000"]:
            messagebox.showwarning("兼容性提示", f"Opus 格式要求特定的采样率（如 48000, 24000, 16000 等）。\n您当前选择了 {sr} 采样率，FFmpeg 在执行时可能会报错退出。")

        if fmt.lower() == 'opus' and self.embed_cover_var.get():
            self.cmd_text.insert(tk.END, "# 提示: ffmpeg官方并不原生支持往opus写入封面轨，已自动忽略写入封面操作\n\n")

        mode = self.manual_convert_mode.get()
        target = self.manual_convert_path.get().strip()
        base_root = self.output_dir_var.get().strip()
        files = []
        # 不同扫描模式最终都统一产出 files，再走同一套命令生成逻辑。
        
        if mode == "file" and os.path.exists(target):
            files.append(target)
        elif mode == "date":
            d_path = target if os.path.isabs(target) else os.path.join(base_root, target)
            if os.path.exists(d_path): files.extend(self.scan_folder_for_audio(d_path))
        elif mode in ["root", "auto"]:
            if os.path.exists(base_root):
                for item in os.listdir(base_root):
                    full = os.path.join(base_root, item)
                    if os.path.isdir(full) and item != "images":
                        files.extend(self.scan_folder_for_audio(full))
        
        if not files:
            if mode == "auto":
                messagebox.showinfo("全部匹配", "当前已没有需要转换或遗漏转换的文件。或者请尝试手动指定模式。")
                self.manual_convert_mode.set("root")
                self.update_manual_ui()
            else:
                self.cmd_text.insert(tk.END, "# 未找到合适的音源文件。\n")
            return
            
        # Determine the base root for relative path calculation
        # If mode == 'file' or 'date', rel root could just be the base_root.
        rel_root = base_root
            
        cnt = 0
        for fp in files:
            cmd = self._build_cmd_for_file(fp, base_root_for_rel=rel_root)
            if cmd:
                cmd_str = subprocess.list2cmdline(cmd)
                self.cmd_text.insert(tk.END, cmd_str + "\n\n")
                cnt += 1
                
        if cnt == 0:
            print("扫描到的所有同名目标音频已被转换，队列空置。")
            self.cmd_text.insert(tk.END, "# 目标文件均已存在！如果要运行请先手动删除对应文件。\n")
        else:
            print(f"成功预生成 {cnt} 条转换排队指令，请在列表中直接运行。")
            messagebox.showinfo("生成完成", f"已成功生成 {cnt} 个文件的转换脚本！")

    def start_manual_exec_thread(self):
        if self.is_downloading:
            messagebox.showinfo("提示", "当前有任务正在运行，请先等待完成或停止后再启动。")
            return
        self.verify_ffmpeg_path(quiet=True)
        if not self.ffmpeg_valid:
            messagebox.showwarning("环境缺失", "找不到有效的 FFmpeg 路径，请先在“环境检测”中配置。")
            return
        
        raw_text = self.cmd_text.get(1.0, tk.END).strip()
        if not raw_text:
            messagebox.showwarning("警告", "命令区为空，请先在左侧点击[预先生成命令]。")
            return
            
        self.is_downloading = True
        self.stop_level = 0
        self.stop_convert_level = 0
        self.pause_event.set()
        # 手动执行沿用同一套 tasks/监控面板，便于和自动转换保持一致的可观测性。
        self.tasks = []
        self.ffmpeg_history_lines = []
        self.is_monitoring = False
        if hasattr(self, 'ffmpeg_text'):
            self.ffmpeg_text.delete("1.0", tk.END)
        
        # Modify UI for conversion
        self.cmd_frame.config(text="转换日志输出 (运行中)")
        self.start_btn.config(state="disabled")
        self.generate_btn.config(state="disabled")
        self.run_cmd_btn.config(state="disabled")
        self.stop_cmd_btn.config(state="normal")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        
        self.log_text.delete(1.0, tk.END)
        print("="*40 + "\n开始提取终端命令，执行转码\n" + "="*40)
        threading.Thread(target=self.run_manual_exec, daemon=True).start()

    def run_manual_exec(self):
        try:
            import os, shlex, concurrent.futures
            raw_text = self.cmd_text.get(1.0, tk.END)
            lines = [l.strip() for l in raw_text.split('\n') if l.strip() and not l.startswith('#')]
            
            self.tasks = []
            for line in lines:
                origin_file = None
                if "-i" in line:
                    try:
                        # 解析 -i 后输入路径，用于“转换成功后删除原文件”功能。
                        args = shlex.split(line)
                        if "-i" in args:
                            idx = args.index("-i") + 1
                            if idx < len(args): origin_file = args[idx].strip('"')
                    except: pass
                self.tasks.append({"id": len(self.tasks), "cmd": line, "file": origin_file, "status": "pending", "progress": "", "start_time": 0, "end_time": 0})
            
            self.root.after(0, lambda: self.cmd_text.delete(1.0, tk.END))
            self.root.after(0, lambda: self.cmd_text.insert(tk.END, "--- 并发转换已启动，请到【下载控制】选项卡查看日志进度 ---\n\n"))
            
            if not self.tasks:
                return

            self.is_monitoring = True
            self.refresh_dashboard()

            workers_str = self.convert_threads_var.get()
            workers = int(workers_str) if workers_str.isdigit() and int(workers_str) > 0 else (os.cpu_count() or 4)
            print(f"[配置] 启动并发转码池，最大线程数: {workers}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(self._execute_task, t) for t in self.tasks]
                for f in concurrent.futures.as_completed(futures):
                    if self.stop_level == 2 or getattr(self, 'stop_convert_level', 0) >= 1:
                        # 收到停止信号后，不再等待剩余 future，尽快回收线程池。
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

            if self.stop_convert_level == 0 and self.stop_level != 2:
                success_msg = f"\n[完成] 队列中的 {len(self.tasks)} 个转换任务已全部处理完毕。\n"
                print(success_msg)
                self.root.after(0, lambda: self.cmd_text.insert(tk.END, success_msg))
                self.root.after(0, lambda: messagebox.showinfo("转换完成", f"已成功处理 {len(self.tasks)} 段音频。"))

        except StopDownloadException as e:
            print(f"\n>>>> 任务安全切断: {e} <<<<")
            self.root.after(0, lambda txt=str(e): self.cmd_text.insert(tk.END, f"\n[终止] 用户操作: {txt}\n"))
        except Exception as e:
            print(f"\n>>>> 批量转码异常: {e}")
            self.root.after(0, lambda txt=str(e): self.cmd_text.insert(tk.END, f"\n[异常] {txt}\n"))
        finally:
            if hasattr(self, 'stop_monitoring'): self.stop_monitoring()
            print("\n---------- 命令池任务遍历结束 ----------")
            
            errors = [t for t in getattr(self, 'tasks', []) if t['status'] == 'error']
            if errors:
                print("\n" + "!"*40)
                print("以下任务出现错误:")
                for e in errors:
                    print(f" - [任务{e['id']}] {getattr(os.path, 'basename', lambda x:x)(e['file'] or '未知')}: {e.get('progress', '')}")
                print("!"*40)

            self.is_downloading = False
            self.stop_convert_level = 0
            self.root.after(0, self.reset_buttons)

if __name__ == '__main__':
    root = tk.Tk()
    app = YunTingDownloaderGUI(root)
    root.mainloop()
