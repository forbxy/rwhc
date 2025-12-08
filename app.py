from lut import *
from meta_data import *
from matrix import *
from convert_utils import *
from delteE import *
from icc_rw import ICCProfile
from color_test_suit import *
from color_rw import ColorReader, ColorWriter
from log import logging, TextHandler
from i18n.i18n_loader import _

from win_display import (
    get_all_display_config,
    get_monitor_rect_by_gdi_name,
    cp_add_display_association,
    install_icc,
    uninstall_icc,
    cp_remove_display_association,
    luid_from_dict,
)

from tkinter import filedialog, ttk, Canvas
import tkinter as tk
import numpy as np
import webbrowser
import subprocess
import threading
import traceback
import tempfile
import ctypes
import time
import uuid
import copy
import sys
import re
import os


class HDRCalibrationUI:
    def __init__(self, root):
        self.init_base_icc()
        self.target_xyz = []
        self.convert_command = []
        self.measured_xyz = {}

        self.gamut_test_rgb = {
            "red": [592, 0, 0],
            "green": [0, 592, 0],
            "blue": [0, 0, 592],
            "white": [1023, 1023, 1023],
            "white_200nit": [592, 592, 592],
            "black": [0, 0, 0],
        }
        self.measure_gamut_xyz = {}

        self.preview_icc_name = None
        self.measured_pq = {"red": [], "green": [], "blue": []}

        self.proc_color_write = None
        self.proc_color_reader = None

        self.icc_change_delay = 0

        self.eetf_args = {
            "source_max": 10000,
            "source_min": 0,
            "monitor_max": None,
            "monitor_min": None,
        }
        self._eetf_window = None

        self.project_url = "https://github.com/forbxy/rwhc"
        self.argyll_download_url = "https://www.argyllcms.com/downloadwin.html"

        self.root = root
        self.root.title("RealWindowsHDRCalibrator")
        self.set_dpi_awareness()

        self.displays_config = get_all_display_config()
        hc = {}
        for itm in self.displays_config:
            product_id = itm["target"]["device_path"].split("#")[1]
            f_name = itm["target"].get("friendly_name") or "none"
            h_dname = f"{itm['path_index']}_{f_name}_{product_id}"
            hc[h_dname] = copy.deepcopy(itm)
            hc[h_dname]["monitor_rect"] = get_monitor_rect_by_gdi_name(
                itm["source"]["gdi_name"]
            )
            hc[h_dname]["color_work_status"] = "sdr"
            # Generate the screen's address in the Windows registry
            t = itm["target"]["device_path"].split("\\")[-1].split("#")[:-1]
            hc[h_dname]["pnp_device_id"] = "\\".join(t)
            """SDR_ACM = advanced_color  & wide_color_enforced
               HDR =     advanced_color  & !wide_color_enforced
               SDR =     !advanced_color & !wide_color_enforced
            """
            if hc[h_dname]["target"]["advanced_color"]["enabled"]:
                hc[h_dname]["color_work_status"] = "hdr"
                if hc[h_dname]["target"]["advanced_color"]["wide_color_enforced"]:
                    hc[h_dname]["color_work_status"] = "sdr_acm"
        self.human_display_config_map = hc

        self.build_ui()
        self.init_logging()
        self.on_monitor_changed()
        

    def init_logging(self):
        th = TextHandler(self.log_text)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        th.setFormatter(fmt)
        root_logger = logging.getLogger()
        root_logger.addHandler(th)

        log_path = os.path.join(os.path.dirname(__file__), "hc.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        root_logger.addHandler(fh)

        root_logger.setLevel(logging.INFO)
        logging.info(_("Application started"))

    def build_ui(self):
        self.root.geometry("960x1000")
        self.root.configure(bg="#f8f8f8")
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        intro_font = ("Microsoft YaHei", 16)

        style = ttk.Style()
        style.theme_use("vista")
        style.configure(
            "TopBar.TMenubutton",
            font=("Microsoft YaHei", 14),
            padding=(5, 4),
            background="#f8f8f8",
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "TopBar.TMenubutton",
            background=[("active", "#e9eff5"), ("pressed", "#dbe6f0")],
            relief=[("pressed", "flat"), ("!pressed", "flat")],
        )
        try:
            style.layout(
                "TopBar.TMenubutton",
                [
                    (
                        "Menubutton.padding",
                        {
                            "children": [("Menubutton.label", {"sticky": "nswe"})],
                            "sticky": "nswe",
                        },
                    )
                ],
            )
        except tk.TclError:
            pass

        top_bar = tk.Frame(root, bg="#f8f8f8")
        top_bar.pack(fill="x", padx=36, pady=(0, 4))

        tk.Frame(top_bar, bg="#dcdcdc", height=1).pack(fill="x", side="bottom")

        tools_btn = ttk.Menubutton(top_bar, text=_("Tools"), style="TopBar.TMenubutton")
        tools_btn.pack(side="left", padx=(0, 24))
        tools_menu = tk.Menu(tools_btn, tearoff=0, font=("Microsoft YaHei", 14))
        tools_menu.add_command(label=_("ICC Modifier"), command=lambda: self.open_tools("icc_modifier_app.py"))
        tools_menu.add_command(label=_("Gamut Browser"), command=lambda: self.open_tools("gamut_browser_app.py"))
        tools_menu.add_command(label=_("View Grayscale"), command=lambda: self.open_tools("view_grayscale_app.py"))
        tools_menu.add_command(label=_("Manual Measurement"), command=lambda: self.open_tools("manual_measure_color_app.py"))
        tools_btn["menu"] = tools_menu  

        help_btn = ttk.Menubutton(top_bar, text=_("Help"), style="TopBar.TMenubutton")
        help_btn.pack(side="left")
        help_menu = tk.Menu(help_btn, tearoff=0, font=("Microsoft YaHei", 14))
        help_menu.add_command(label=_("User Guide"), command=self.open_user_guide_window)
        help_menu.add_command(label=_("Project Homepage"), command=self.open_project_homepage)
        help_btn["menu"] = help_menu
        self.help_window = None

        intro = "\n".join([
            _("Please read the Help page before use!"),
            _("Require win11 >= 22H2 win10 >= 1709"),
            _("Pattern generator: dogegen"),
            _("Colorimeter driver: argyllcms spotread")
        ])
        tk.Label(
            root,
            text=intro,
            font=intro_font,
            justify="left",
            bg="#f8f8f8",
            fg="#333333",
            anchor="w",
            pady=12,
            wraplength=2150,
        ).pack(pady=(0, 10), padx=36, anchor="w")

        tk.Frame(root, height=1, bg="#dcdcdc").pack(fill="x", padx=36, pady=(4, 8))

        style.configure(
            "TButton", font=("Microsoft YaHei", 16), padding=(12, 8), width=20
        )
        style.configure(
            "TCheckbutton",
            font=("Microsoft YaHei", 16),  # Set font size
            padding=(8, 4),  # Optional: adjust padding
        )


        button_frame = tk.Frame(root, bg="#f8f8f8")
        button_frame.pack(pady=20, anchor="w", padx=36)
        self.root.option_add("*TCombobox*Listbox*Font", ("Microsoft YaHei", 15))

        self.monitor_list = list(self.human_display_config_map.keys())
        self.monitor_list.sort()
        self.monitor_var = tk.StringVar(
            value=self.monitor_list[0] if self.monitor_list else "No Monitor Found"
        )
        tk.Label(
            button_frame, text=_("Select display:"), font=("Microsoft YaHei", 16), bg="#f8f8f8"
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 12), columnspan=3)
        monitor_menu = ttk.Combobox(
            button_frame,
            textvariable=self.monitor_var,
            values=self.monitor_list,
            font=("Microsoft YaHei", 16),
            width=40,
            state="readonly",
        )
        monitor_menu.grid(
            row=0, column=0, sticky="we", padx=(120, 0), pady=(0, 12), columnspan=3
        )
        monitor_menu.bind("<<ComboboxSelected>>", lambda e: self.on_monitor_changed())

        im = self.get_instrument_mode_options()
        self.instrument_desc = [itm[1] for itm in im[0]]
        self.instrument_choose = [itm[0] for itm in im[0]]
        self.mode_desc = [itm[1] for itm in im[1]]
        self.mode_choose = [itm[0] for itm in im[1]]
        if not self.instrument_desc:
            self.instrument_desc = [_("No instrument found")]
        self.instrument_var = tk.StringVar(value=self.instrument_desc[0])
        tk.Label(
            button_frame, text=_("Select instrument:"), font=("Microsoft YaHei", 16), bg="#f8f8f8"
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 12), columnspan=3)
        instrument_menu = ttk.Combobox(
            button_frame,
            textvariable=self.instrument_var,
            values=self.instrument_desc,
            font=("Microsoft YaHei", 16),
            width=40,
            state="readonly",
        )
        instrument_menu.grid(
            row=1, column=0, sticky="we", padx=(120, 0), pady=(0, 12), columnspan=3
        )
        if not self.mode_desc:
            self.mode_desc = [_("No instrument found")]
        self.mode_var = tk.StringVar(value=self.mode_desc[0])
        tk.Label(
            button_frame, text=_("Instrument mode:"), font=("Microsoft YaHei", 16), bg="#f8f8f8"
        ).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(0, 12), columnspan=3)
        mode_menu = ttk.Combobox(
            button_frame,
            textvariable=self.mode_var,
            values=self.mode_desc,
            font=("Microsoft YaHei", 16),
            width=40,
            state="readonly",
        )
        mode_menu.grid(
            row=2, column=0, sticky="we", padx=(120, 0), pady=(0, 12), columnspan=3
        )

        self.pq_points_var = tk.StringVar(value="128")  
        tk.Label(
            button_frame,
            text=_("Grayscale samples:"),
            font=("Microsoft YaHei", 16),
            bg="#f8f8f8",
        ).grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(0, 12))
        pq_points_menu = ttk.Combobox(
            button_frame,
            textvariable=self.pq_points_var,
            values=["128", "256", "512", "1024"],
            font=("Microsoft YaHei", 16),
            width=6,
            state="readonly",
        )
        pq_points_menu.grid(row=3, column=0, sticky="we", padx=(120, 33), pady=(0, 12))

        self.color_space_var = tk.StringVar(value="sRGB")
        tk.Label(
            button_frame,
            text=_("Color sample set:"),
            font=("Microsoft YaHei", 16),
            bg="#f8f8f8",
        ).grid(row=3, column=1, sticky="w", padx=(0, 10), pady=(0, 12))
        color_space_menu = ttk.Combobox(
            button_frame,
            textvariable=self.color_space_var,
            values=["sRGB", "sRGB+DisplayP3"],
            font=("Microsoft YaHei", 16),
            width=6,
            state="readonly",
        )
        color_space_menu.grid(
            row=3, column=1, sticky="we", padx=(120, 33), pady=(0, 12)
        )

        self.eetf_var = tk.BooleanVar(value=False)
        self.eetf_check = ttk.Checkbutton(
            button_frame,
            text=_("Luminance mapping"),
            variable=self.eetf_var,
            style="TCheckbutton",
            command=self.on_eetf_toggle,
        )
        # self.eetf_check.grid(row=3, column=2, sticky="w", padx=(0, 10), pady=(0, 12))
        # EETF functionality needs refactor before enabling
        
        self.bright_var = tk.BooleanVar(value=False) 
        self.bright_checkbutton = ttk.Checkbutton(
            button_frame,
            text=_("Bright mode"),
            variable=self.bright_var,
            style="TCheckbutton",
        )
        self.bright_checkbutton.grid(
            row=3, column=2, sticky="w", padx=(0, 0), pady=(0, 14)
        )

        self.preview_var = tk.BooleanVar(value=False) 
        self.preview_var.trace_add("write", lambda *a: self.on_preview_toggle())
        self.preview_checkbutton = ttk.Checkbutton(
            button_frame,
            text=_("Preview calibration result"),
            variable=self.preview_var,
            style="TCheckbutton",
        )
        self.preview_checkbutton.grid(
            row=4, column=0, sticky="w", padx=(0, 0), pady=(0, 14)
        )

        self.icc_set_var = tk.BooleanVar(value=True) 
        self.icc_set_checkbutton = ttk.Checkbutton(
            button_frame,
            text=_("Load as default ICC after saving"),
            variable=self.icc_set_var,
            style="TCheckbutton",
        )
        self.icc_set_checkbutton.grid(
            row=4, column=2, sticky="w", padx=(0, 0), pady=(0, 14)
        )

        ttk.Button(
            button_frame,
            text=_("Calibrate"),
            command=self.calibrate_monitor,
            style="TButton",  
            
            width=20,
        ).grid(row=5, column=0, padx=(0, 30), pady=(10, 0), sticky="w")

        ttk.Button(
            button_frame,
            text=_("Measure color accuracy"),
            command=self.measure_pq,
            style="TButton",
            width=20,
        ).grid(row=5, column=1, padx=(0, 30), pady=(10, 0), sticky="w")

        ttk.Button(
            button_frame,
            text=_("Save as ICC file"),
            command=self.generate_and_save_icc,
            style="TButton",
            width=20,
        ).grid(row=5, column=2, pady=(10, 0), sticky="w")

        ttk.Button(
            button_frame,
            text=_("Open Device Manager"),
            command=lambda: os.system("start devmgmt.msc"),
            style="TButton",
            width=20,
        ).grid(row=6, column=0, columnspan=2, pady=(20, 0), sticky="w")
        ttk.Button(
            button_frame,
            text=_("Open Windows Services"),
            command=lambda: os.system("start services.msc"),
            style="TButton",
            width=20,
        ).grid(row=6, column=1, columnspan=2, pady=(20, 0), sticky="w")

        ttk.Button(
            button_frame,
            text=_("Install Spyder driver"),
            command=lambda: webbrowser.open(self.argyll_download_url),
            style="TButton",
            width=20,
        ).grid(row=6, column=2, columnspan=2, pady=(20, 0), sticky="w")

        log_frame = ttk.LabelFrame(root, text=_("Log"))
        log_frame.pack(fill="both", expand=True, padx=36, pady=(0, 20))
        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            font=("Microsoft YaHei", 12),
            bg="#ffffff",
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True, padx=6, pady=6)

    def init_base_icc(self):
        self.icc_handle = ICCProfile("data/hdr_empty.icc")
        self.icc_data = self.icc_handle.read_all()
        self.MHC2 = copy.deepcopy(self.icc_data["MHC2"])
        if self.MHC2["red_lut"] == [0, 1]:
            self.MHC2["red_lut"] = generate_pq_lut().tolist()
            self.MHC2["green_lut"] = generate_pq_lut().tolist()
            self.MHC2["blue_lut"] = generate_pq_lut().tolist()
            self.MHC2["entry_count"] = len(self.MHC2["red_lut"])

    def set_dpi_awareness(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1) 
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def run_in_thread(self, worker, on_done):
        """
        worker: a function that takes no arguments (or only uses closure variables) — returns a result
        on_done(result): callback executed on the main (GUI) thread
        """

        def _wrap():
            try:
                res = worker()
            except Exception as e:
                res = e
            
            self.root.after(0, lambda: on_done(res))

        threading.Thread(target=_wrap, daemon=True).start()

    def get_instrument_mode_options(self):
        """
        Dynamically parse the output of spotread.exe --help
        to extract available instruments and their device file names.
        """
        exe_path = os.path.join(os.path.dirname(__file__), "bin", "spotread.exe")
        if not os.path.isfile(exe_path):
            return ([], [])
        try:
            proc = subprocess.run(
                [exe_path, "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
                check=False,
            )
            output = proc.stdout
        except Exception as e:
            return ([], [])

        lines = [itm.strip() for itm in output.splitlines()]

        c_list = []
        for i, ln in enumerate(lines):
            if "-c listno" in ln:
                # Collect downward until hitting the next argument (line starts with '-' and is not indented)
                j = i
                while j < len(lines):
                    l2 = lines[j]
                    if j != i and re.match(r"^-\w", l2):
                        break
                    # Match pattern like "  1 = 'xxxx'"
                    m = re.match(r"\s*(\d+)\s*=\s*'(.+)'", l2)
                    if m:
                        c_list.append([m.group(1), m.group(2)])
                    j += 1
                break  # Exit after finishing the block

        # -y
        y_list = []
        start_idx = None
        for i, ln in enumerate(lines):
            if re.match(r"^-y\s+", ln):
                start_idx = i
                break
        if start_idx is not None:
            # Collect the -y block
            block = []
            for j in range(start_idx, len(lines)):
                l2 = lines[j]
                if j == start_idx:
                    l2 = l2[3:]  # Strip the "-y " prefix
                if j > start_idx and re.match(r"^\-\w", l2):  # Next argument begins
                    break
                block.append(l2.rstrip())
            for raw in block:
                if not raw.strip():
                    continue
                m = raw.split("    ")
                code = m[0].strip()
                desc = m[-1].strip()
                y_list.append([code, desc])
        if not y_list:
            logging.error(_("Failed to parse spotread -y modes; the output format may have changed"))
        return c_list, y_list

    def get_spotread_args(self):
        args = []
        instrument_idx = self.instrument_desc.index(self.instrument_var.get())
        mode_idx = self.mode_desc.index(self.mode_var.get())
        args.append("-x")
        args.extend(["-c", self.instrument_choose[instrument_idx]])
        args.extend(["-y", self.mode_choose[mode_idx].split("|")[0]])
        return " ".join(args)
    
    def open_tools(self, tool_name):
        try:
            script = os.path.join(os.path.dirname(__file__), "tools", tool_name)
            if not os.path.isfile(script):
                tk.messagebox.showerror(_("Error"), _("File not found: {}").format(script))
                return
            subprocess.Popen([sys.executable, script], cwd=os.path.dirname(script))
        except Exception as e:
                tk.messagebox.showerror(_("Error"), _("Failed to launch {}: {}").format(tool_name, e))


    def open_project_homepage(self):
        webbrowser.open(self.project_url)

    def open_user_guide_window(self):
        webbrowser.open(self.project_url)

    def set_icc(self, path):
        """
        path: The file path of the ICC profile to install.
        Install the specified ICC file, 
        associate it with the currently selected display, 
        and set it as that display's default ICC.
        """
        install_icc(path)
        icc_name = os.path.basename(path)
        monitor = self.monitor_var.get()
        info = self.human_display_config_map.get(monitor)
        luid = luid_from_dict(info["adapter_luid"])
        sid = info["source"]["id"]
        hdr = False
        if info["color_work_status"] == "hdr":
            hdr = True
        cp_add_display_association(
            luid, sid, icc_name, set_as_default=True, associate_as_advanced_color=hdr
        )

    def clean_icc(self, name):
        """
        name: The name of the ICC profile to clean (without .icc or .icm).
        Unassociate the specified ICC file from the currently selected display, 
        unset it as that display's default profile, 
        and remove the ICC file from the system.
        """
        path = f"{name}.icc"
        monitor = self.monitor_var.get()
        info = self.human_display_config_map.get(monitor)
        luid = luid_from_dict(info["adapter_luid"])
        sid = info["source"]["id"]
        hdr = False
        if info["color_work_status"] == "hdr":
            hdr = True
        cp_remove_display_association(luid, sid, path, associate_as_advanced_color=hdr)
        uninstall_icc(path, force=True)

    def freeze_ui(self):
        """
        Disable all interactive controls in the window; 
        save their original states (including Combobox 'readonly' state).
        """
        if getattr(self, "_ui_frozen", False):
            return
        self._ui_frozen = True
        self._disabled_widgets = []

        def add(widget, prev_state):
            self._disabled_widgets.append((widget, prev_state))

        def walk(w):
            for child in w.winfo_children():
                walk(child)
                if isinstance(
                    child,
                    (
                        tk.Button,
                        tk.Checkbutton,
                        tk.Radiobutton,
                        tk.Scale,
                        tk.Entry,
                        tk.Text,
                    ),
                ):
                    prev = child.cget("state")
                    if prev != "disabled":
                        add(child, prev)
                        child.config(state="disabled")
                elif isinstance(
                    child,
                    (
                        ttk.Button,
                        ttk.Checkbutton,
                        ttk.Radiobutton,
                        ttk.Entry,
                        ttk.Menubutton,
                    ),
                ):
                    try:
                        prev = child.cget("state")
                    except Exception:
                        try:
                            prev = (
                                "disabled" if "disabled" in child.state() else "normal"
                            )
                        except Exception:
                            prev = "normal"
                    if prev != "disabled":
                        add(child, prev)
                        child.configure(state="disabled")
                elif isinstance(child, ttk.Combobox):
                    prev = child.cget("state")  # Could be 'readonly' or 'normal'
                    if prev != "disabled":
                        add(child, prev)
                        child.configure(state="disabled")
                if isinstance(child, ttk.Menubutton):
                    m = child["menu"] if "menu" in child.keys() else None
                    if isinstance(m, tk.Menu):
                        entry_states = []
                        end = m.index("end")
                        if end is not None:
                            for i in range(end + 1):
                                try:
                                    st = m.entrycget(i, "state")
                                    entry_states.append(st)
                                    m.entryconfig(i, state="disabled")
                                except Exception:
                                    entry_states.append(None)
                        add(m, entry_states)

        walk(self.root)
        self.root.configure(cursor="wait")
        self.root.update_idletasks()

    def unfreeze_ui(self):
        """
        Restore the interactive controls' states that were saved prior to calling freeze_ui.
        """
        if not getattr(self, "_ui_frozen", False):
            return
        for widget, prev in getattr(self, "_disabled_widgets", []):
            if isinstance(widget, tk.Menu):
                for i, st in enumerate(prev):
                    if st is not None:
                        try:
                            widget.entryconfig(i, state=st)
                        except Exception:
                            pass
                continue
            try:
                if prev != "disabled":
                    widget.configure(state=prev)
            except Exception:
                pass
        self._disabled_widgets.clear()
        self._ui_frozen = False
        self.root.configure(cursor="")
        self.root.update_idletasks()

    @staticmethod
    def safe_call(func):
        """
        Decorator for GUI action methods that:
        - Catches and logs any exception raised by the wrapped function.
        - Ensures cleanup steps run on error (unfreeze UI, stop reader/writer processes).
        - Resets transient ICC/preview state to a safe default.
        - Prevents the exception from propagating to the caller (avoids crashing the GUI thread).
        """
        def wrapper(*args, **kwargs):
            self = args[0]
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logging.error(_("Error while executing {}: {}").format(func.__name__, e))
                logging.error(traceback.format_exc())
                try:
                    self.unfreeze_ui()
                except Exception:
                    pass
                try:
                    self.clean_color_rw_process()
                except Exception:
                    pass
                self.icc_change_delay = 0
                if self.preview_icc_name:
                    try:
                        self.preview_var.set(False)
                    except Exception:
                        pass

        return wrapper

    def clean_color_rw_process(self):
        try:
            if self.proc_color_write:
                self.proc_color_write.terminate()
                self.proc_color_write = None
            if self.proc_color_reader:
                self.proc_color_reader.terminate()
                self.proc_color_reader = None
        except Exception as e:
            logging.error(_("Error cleaning color read/write processes: {}").format(e))
            logging.error(traceback.format_exc())

    def on_exit(self):
        # exit clean
        try:
            if self.preview_icc_name:
                self.clean_icc(self.preview_icc_name)
            self.clean_color_rw_process()
        except Exception as e:
            logging.error(_("Error during on_exit: {}").format(e))
            logging.error(traceback.format_exc())
        try:
            self.root.destroy()
        except Exception:
            pass

    def on_monitor_changed(self, event=None):
        """
        Display change notification: 
        show a short, undecorated overlay centered on the selected monitor 
        """
        sel = self.monitor_var.get()
        info = self.human_display_config_map.get(sel)
        if not info:
            return

        mon = info.get("monitor_rect")
        if not mon:
            try:
                mon = get_monitor_rect_by_gdi_name(info["source"]["gdi_name"])
            except Exception:
                return

        box_w = 500
        box_h = 300
        duration_ms = 1500
        text = _("Selected this display")

        mon_left = int(mon.get("left", 0))
        mon_top = int(mon.get("top", 0))
        mon_right = int(mon.get("right", mon_left + box_w))
        mon_bottom = int(mon.get("bottom", mon_top + box_h))
        mon_w = max(1, mon_right - mon_left)
        mon_h = max(1, mon_bottom - mon_top)

        x = mon_left + (mon_w - box_w) // 2
        y = mon_top + (mon_h - box_h) // 2

        try:
            prev_top = self.root.attributes("-topmost")
        except Exception:
            prev_top = False

        def _to_bool(v):
            if isinstance(v, str):
                return v in ("1", "true", "True")
            return bool(v)

        prev_top_bool = _to_bool(prev_top)

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.transient(self.root)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="white")
        overlay.geometry(f"{box_w}x{box_h}+{x}+{y}")
        overlay.lift(self.root)

        frm = tk.Frame(
            overlay, bg="white", highlightthickness=1, highlightbackground="#888888"
        )
        frm.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            frm, width=box_w, height=box_h, highlightthickness=0, bg="white"
        )
        canvas.pack(fill="both", expand=True)

        canvas.create_text(
            box_w // 2,
            box_h // 2,
            text=text,
            fill="black",
            font=("Segoe UI", 16, "bold"),
        )

        def _cleanup():
            try:
                if overlay.winfo_exists():
                    overlay.destroy()
            except Exception:
                pass
            try:
                self.root.attributes("-topmost", True)
                self.root.lift()
                # try:
                #     self.root.focus_force()
                # except Exception:
                #     pass

                def _restore():
                    try:
                        self.root.attributes("-topmost", prev_top_bool)
                    except Exception:
                        pass

                self.root.after(10, _restore)
            except Exception:
                pass

        overlay.after(duration_ms, _cleanup)

    def on_eetf_toggle(self):
        if self.eetf_var.get():
            self.open_eetf_window()
        else:
            self.eetf_args = {
                "source_max": 10000,
                "source_min": 0,
                "monitor_max": None,
                "monitor_min": None,
            }

    def open_eetf_window(self):
        if self._eetf_window and self._eetf_window.winfo_exists():
            self._eetf_window.lift()
            return

        win = tk.Toplevel(self.root)
        win.title(_("EETF parameters"))
        win.geometry("360x330")
        win.resizable(True, True)
        self._eetf_window = win

        frm = tk.Frame(win, padx=14, pady=12)
        frm.pack(fill="both", expand=True)

        src_max_default = self.eetf_args.get("source_max", 10000)
        src_min_default = self.eetf_args.get("source_min", 0)
        mon_max_default = self.eetf_args.get("monitor_max")
        mon_min_default = self.eetf_args.get("monitor_min")

        v_src_max = tk.StringVar(
            value=str(src_max_default if src_max_default is not None else "10000")
        )
        v_src_min = tk.StringVar(
            value=str(src_min_default if src_min_default is not None else "0")
        )
        v_max = tk.StringVar(
            value=("" if mon_max_default is None else f"{mon_max_default}")
        )
        v_min = tk.StringVar(
            value=("" if mon_min_default is None else f"{mon_min_default}")
        )

        tk.Label(frm, text=_("Source max luminance (nit):"), font=("Microsoft YaHei", 13)).grid(
            row=0, column=0, sticky="w", pady=6
        )
        e1 = ttk.Entry(frm, textvariable=v_src_max, width=18)
        e1.grid(row=0, column=1, sticky="w", pady=6)

        tk.Label(frm, text=_("Source min luminance (nit):"), font=("Microsoft YaHei", 13)).grid(
            row=1, column=0, sticky="w", pady=6
        )
        e2 = ttk.Entry(frm, textvariable=v_src_min, width=18)
        e2.grid(row=1, column=1, sticky="w", pady=6)

        tk.Label(frm, text=_("Display max luminance (nit):"), font=("Microsoft YaHei", 13)).grid(
            row=2, column=0, sticky="w", pady=6
        )
        e3 = ttk.Entry(frm, textvariable=v_max, width=18)
        e3.grid(row=2, column=1, sticky="w", pady=6)

        tk.Label(frm, text=_("Display min luminance (nit):"), font=("Microsoft YaHei", 13)).grid(
            row=3, column=0, sticky="w", pady=6
        )
        e4 = ttk.Entry(frm, textvariable=v_min, width=18)
        e4.grid(row=3, column=1, sticky="w", pady=6)

        tk.Label(
            frm,
            text=_("Tip: leave display max/min empty to use measured values."),
            font=("Microsoft YaHei", 13),
            fg="#333333",
            wraplength=320,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = tk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=2, pady=(14, 0), sticky="e")

        def on_ok():
            # Parse to float; allow empty values as None
            try:
                smx = float(v_src_max.get())
                smn = float(v_src_min.get())
            except Exception:
                tk.messagebox.showerror(_("Error"), _("Source luminance must be numeric"))
                return
            try:
                mmx = float(v_max.get()) if v_max.get().strip() != "" else None
                mmn = float(v_min.get()) if v_min.get().strip() != "" else None
            except Exception:
                tk.messagebox.showerror(_("Error"), _("Display luminance must be numeric or left blank"))
                return

            if smx <= 0 or smn < 0 or smn > smx:
                tk.messagebox.showerror(
                    _("Error"), _("Source max must be > 0 and source min must be <= source max")
                )
                return

            if mmx is not None and mmx <= 0:
                tk.messagebox.showerror(_("Error"), _("Display max luminance must be > 0"))
                return
            if (mmx is not None and mmn is not None) and (mmn < 0 or mmn > mmx):
                tk.messagebox.showerror(_("Error"), _("Display min luminance must be within [0, max]"))
                return

            self.eetf_args = {
                "source_max": smx,
                "source_min": smn,
                "monitor_max": mmx,
                "monitor_min": mmn,
            }
            logging.info(_("EETF params: %s"), self.eetf_args)
            win.destroy()

        def on_cancel():
            self.eetf_var.set(False)
            win.destroy()

        ttk.Button(btns, text=_("OK"), command=on_ok, width=10).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(btns, text=_("Cancel"), command=on_cancel, width=10).pack(side="right")

        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: on_cancel())

    def on_preview_toggle(self):
        """
        Implement a preview: loading a temporary ICC profile onto the selected display.
        before measurement load hdr_empty.icc as a preview; 
        after measurement preview the measured results 
        """
        state = self.preview_var.get()
        if state:
            if self.preview_icc_name:
                self.clean_icc(self.preview_icc_name)
                self.preview_icc_name = None
                time.sleep(self.icc_change_delay)
            self.preview_icc_name = "CC_" + str(uuid.uuid4())
            temp_dir = tempfile.gettempdir()
            icc_file_name = self.preview_icc_name + ".icc"
            path = os.path.join(temp_dir, icc_file_name)
            desc = [{"lang": "en", "country": "US", "text": self.preview_icc_name}]
            self.icc_handle.write_desc(desc)
            self.icc_handle.rebuild()
            self.icc_handle.save(path)
            self.set_icc(path)
            os.remove(path)
            time.sleep(self.icc_change_delay)
        else:
            if self.preview_icc_name:
                self.clean_icc(self.preview_icc_name)
                self.preview_icc_name = None
                time.sleep(self.icc_change_delay)

    def temp_save_icc(self, path):
        # debug only
        filename = os.path.basename(path)
        name_without_ext = os.path.splitext(filename)[0]
        desc = [{"lang": "en", "country": "US", "text": name_without_ext}]
        self.icc_handle.write_desc(desc)
        self.icc_handle.rebuild()
        self.icc_handle.save(path)

    @safe_call
    def calibrate_monitor(self):
        logging.info(_("Calibration started"))
        self.freeze_ui()
        hdr_status = self.human_display_config_map[self.monitor_var.get()]["color_work_status"]
        logging.info(_("Selected screen HDR state: {}").format(hdr_status))
        if hdr_status != "hdr":
            msg = _("The selected screen HDR is off. Please enable HDR in system settings before calibration.")
            tk.messagebox.showerror(_("Error"), msg)
            logging.error(msg)
            self.clean_color_rw_process()
            self.unfreeze_ui()
            return

        self.proc_color_write = ColorWriter()
        args = self.get_spotread_args()
        self.proc_color_reader = ColorReader(args)
        # Send command to the child process
        self.proc_color_write.write_rgb([800, 800, 800])
        msg = _("Move the white window to the target screen, resize it to fully cover the meter, place the meter on the window, then click OK.")
        answer = tk.messagebox.askokcancel(_("Place the colorimeter"), msg)
        if not answer:
            logging.info(_("User canceled calibration"))
            self.clean_color_rw_process()
            self.unfreeze_ui()
            return

        self.init_base_icc()
        origin_preview_status = self.preview_var.get()

        self.icc_change_delay = 0.5
    
        def calibrate_control():
            self.measure_gamut_before()
            self.calibrate_pq()
            # self.calibrate_white_by_lut()
            self.calibrate_chromaticity()
            self.measure_gamut_after()
            
            return
            

        def measure_control_cb(result):
            if isinstance(result, Exception):
                msg = _("Matrix LUT generation failed: {}").format(result)
                logging.error(msg)
                tk.messagebox.showerror(_("Error"), msg)
            else:
                logging.info(_("Matrix LUT generated"))
            self.unfreeze_ui()
            self.clean_color_rw_process()
            self.icc_change_delay = 0
            self.preview_var.set(origin_preview_status)
            if isinstance(result, Exception):
                raise result
            

        self.run_in_thread(calibrate_control, measure_control_cb)

    def measure_gamut_before(self):
        self.preview_var.set(True)
        max_lumi = 0
        min_lumi = 0
        for color, rgb in self.gamut_test_rgb.items():
            self.proc_color_write.write_rgb(rgb, delay=0.1)
            XYZ = self.proc_color_reader.read_XYZ()
            logging.info(_("Color {} measured XYZ: {}").format(color, XYZ))
            eetf = self.eetf_var.get()
            # If EETF is enabled, 
            # set the luminance parameters in the ICC 
            # to avoid double mapping.
            if color == "white":
                if eetf and self.eetf_args["monitor_max"] != 10000 and \
                    self.eetf_args["monitor_max"] is not None:
                    max_lumi = self.eetf_args["monitor_max"]
                else:
                    max_lumi = XYZ[1]
            if color == "black":
                if eetf and self.eetf_args["monitor_min"] != 0:
                    min_lumi = 0
                else:
                    min_lumi = XYZ[1]
            self.measure_gamut_xyz[color] = XYZ
            
            
        start_lumi = self.measure_gamut_xyz["black"][1]
        delta = max(start_lumi * 0.01, 0.0005)  # Adjust threshold as needed
        logging.info(_("Start binary search for activated black: start_lumi={} delta={}").format(start_lumi, delta))

        def measure_gray(code):
            rgb = [code, code, code]
            self.proc_color_write.write_rgb(rgb, delay=0.1)
            XYZ = self.proc_color_reader.read_XYZ()
            logging.info(_("Gray test code={} RGB={} measured XYZ: {}").format(code, rgb, XYZ))
            return XYZ

        high_XYZ = measure_gray(255)
        if high_XYZ[1] <= start_lumi + delta:
            logging.info(_("No significant luminance increase found in 0-255 range; skipping activated black detection"))
            self.measure_gamut_xyz["min_activated_black"] = self.measure_gamut_xyz["black"]
        else:
            lo, hi = 1, 255
            found_code = None
            found_XYZ = None
            while lo <= hi:
                mid = (lo + hi) // 2
                XYZ = measure_gray(mid)
                if XYZ[1] > start_lumi + delta:
                    found_code = mid
                    found_XYZ = XYZ
                    hi = mid - 1  
                else:
                    lo = mid + 1
            if found_XYZ is not None:
                self.measure_gamut_xyz["min_activated_black"] = found_XYZ
                logging.info(_("Activated black level found: code={} XYZ={}").format(found_code, found_XYZ))
            else:
                logging.info(_("Activated black not found (grayscale differences may be below threshold)"))

        """
        FIXME 
        The full‑frame luminance of an OLED may be lower than the maximum luminance of a patch, 
        but currently I can't get dogegen to display in fullscreen.
        """
        peak_lumi = max_lumi
        logging.info(_("Writing max full-frame luminance {}, peak luminance {}, min luminance {}").format(max_lumi, peak_lumi, min_lumi))
        self.MHC2["min_luminance"] = min_lumi
        self.MHC2["peak_luminance"] = peak_lumi
        self.icc_handle.write_XYZType("lumi", [[max_lumi, max_lumi, max_lumi]])
        
        r = l2_normalize_XYZ(self.measure_gamut_xyz["red"])
        g = l2_normalize_XYZ(self.measure_gamut_xyz["green"])
        b = l2_normalize_XYZ(self.measure_gamut_xyz["blue"])
        w = l2_normalize_XYZ(self.measure_gamut_xyz["white_200nit"])
        logging.info(_("Writing RGBW XYZ:\n {}\n {}\n {}\n {}").format(r, g, b, w))
        self.icc_handle.write_XYZType("rXYZ", [r])
        self.icc_handle.write_XYZType("gXYZ", [g])
        self.icc_handle.write_XYZType("bXYZ", [b])
        self.icc_handle.write_XYZType("wtpt", [w])
        
        self.icc_handle.write_MHC2(self.MHC2)

        logging.info(_("Gamut measurement finished"))
    
    def measure_gamut_after(self):
        self.preview_var.set(True)
        max_lumi = 0
        min_lumi = 0
        for color, rgb in self.gamut_test_rgb.items():
            self.proc_color_write.write_rgb(rgb, delay=0.1)
            XYZ = self.proc_color_reader.read_XYZ()
            logging.info(_("Color {} measured XYZ: {}").format(color, XYZ))
            if color == "white":
                max_lumi = XYZ[1]
            if color == "black":
                min_lumi = XYZ[1]
            self.measure_gamut_xyz[color] = XYZ

        """
        FIXME 
        The full‑frame luminance of an OLED may be lower than the maximum luminance of a patch, 
        but currently I can't get dogegen to display in fullscreen.
        """
        if self.bright_var.get():
            lut = generate_inversed_lut(generate_bright_pq_lut())
            bright_lut_inv = {"red_lut": lut.tolist(),
                              "green_lut": lut.tolist(),
                              "blue_lut": lut.tolist()}

            white_rgb_fix = apply_lut(XYZ_to_BT2020_PQ_rgb(self.measure_gamut_xyz["white"]/10000), bright_lut_inv)
            black_rgb_fix = apply_lut(XYZ_to_BT2020_PQ_rgb(self.measure_gamut_xyz["black"]/10000), bright_lut_inv)
            white_xyz_fix = BT2020_PQ_rgb_to_XYZ(white_rgb_fix)
            black_xyz_fix = BT2020_PQ_rgb_to_XYZ(black_rgb_fix)
            logging.info(_("Brightness-compensated white RGB: {} XYZ: {}").format(white_rgb_fix, white_xyz_fix))
            logging.info(_("Brightness-compensated black RGB: {} XYZ: {}").format(black_rgb_fix, black_xyz_fix))
            max_lumi = white_xyz_fix[1]*10000
            min_lumi = black_xyz_fix[1]*10000
        peak_lumi = max_lumi
        logging.info(_("Writing max full-frame luminance {}, peak luminance {}, min luminance {}").format(max_lumi, peak_lumi, min_lumi))
        self.MHC2["min_luminance"] = min_lumi
        self.MHC2["peak_luminance"] = peak_lumi
        self.icc_handle.write_XYZType("lumi", [[max_lumi, max_lumi, max_lumi]])
        
        r = l2_normalize_XYZ(self.measure_gamut_xyz["red"])
        g = l2_normalize_XYZ(self.measure_gamut_xyz["green"])
        b = l2_normalize_XYZ(self.measure_gamut_xyz["blue"])
        w = l2_normalize_XYZ(self.measure_gamut_xyz["white_200nit"])
        logging.info(_("Writing RGBW XYZ:\n {r}\n {g}\n {b}\n {w}").format(r=r, g=g, b=b, w=w))
        self.icc_handle.write_XYZType("rXYZ", [r])
        self.icc_handle.write_XYZType("gXYZ", [g])
        self.icc_handle.write_XYZType("bXYZ", [b])
        self.icc_handle.write_XYZType("wtpt", [w])
        
        self.icc_handle.write_MHC2(self.MHC2)

        logging.info(_("Gamut measurement finished"))

    def calibrate_chromaticity(self):
        # measure and build matrix
        self.preview_var.set(True)
        logging.info(_("Start color measurement and generate matrix"))
        self.target_xyz = get_srgb_calibrate_XYZ_suit(self.measure_gamut_xyz)
        if self.color_space_var.get() == "sRGB+DisplayP3":
            self.target_xyz.extend(get_P3D65_calibrate_XYZ_suit(self.measure_gamut_xyz))
        white_points = get_D65_white_calibrate_test_XYZ_suit(self.measure_gamut_xyz)
        self.target_xyz.extend(white_points)
        self.measured_xyz = []
        i = 1
        l = len(self.target_xyz)
        for itm in self.target_xyz:
            pq = XYZ_to_BT2020_PQ_rgb(itm)
            rgb = (pq * 1023).round().astype(int)
            self.proc_color_write.write_rgb(rgb, delay=0.1)
            XYZ = self.proc_color_reader.read_XYZ()
            XYZ = [float(itm) / 10000 for itm in XYZ]
            logging.info(_("({}) Color: {} Target XYZ:{} Measured: {}").format(i/l, rgb , itm, XYZ))
            self.measured_xyz.append(XYZ)
            i += 1
        matrix = fit_XYZ2XYZ_wlock_dropY(self.measured_xyz, self.target_xyz,self.measured_xyz[-1], self.target_xyz[-1])
        # matrix = fit_XYZ2XYZ(self.measure_convert_xyz, self.convert_xyz)
        ori_matrix = np.array(self.MHC2["matrix"]).reshape(3, 3)
        matrix2 = ori_matrix @ matrix
        self.MHC2["matrix"] = matrix2.flatten().tolist()
        self.icc_handle.write_MHC2(self.MHC2)
        logging.info(_("Color matrix measurement finished, matrix: {}").format(self.MHC2["matrix"]))
    
    def calibrate_white_by_lut(self):
        logging.info(_("Start calibrating grayscale chromaticity to D65"))
        MEASURE_POINTS_COUNT = 32
        pq_lut_origin = {"red": copy.deepcopy(self.MHC2["red_lut"]),
                         "green": copy.deepcopy(self.MHC2["green_lut"]),
                         "blue": copy.deepcopy(self.MHC2["blue_lut"])}
        max_nit = 0
        self.proc_color_write.write_rgb([1023,1023,1023], delay=0.3)
        XYZ = self.proc_color_reader.read_XYZ()
        max_nit = XYZ[1]
        min_nit = 10
        logging.info(_("Measured display peak luminance: {} nit").format(max_nit))
        measure_points_t = np.linspace(0, 1023, MEASURE_POINTS_COUNT, dtype=int)
        measure_points = [i for i in measure_points_t if min_nit < pq_eotf(i / 1023) < max_nit*0.8]
        
        # measure_points = [719]
        
        measure_points.insert(0, 0)
        measure_points.append(1023)
        logging.info(_("Grayscale points measured this run ({}): {}".format(len(measure_points), measure_points)))
        scales = []
        for grayscale in measure_points:
            nit = pq_eotf(grayscale / 1023)
            if nit > max_nit:
                logging.info(_("Grayscale {} target {} nit exceeds 90% of display peak {}, skip").format(
                    grayscale, nit, max_nit*0.9))
                scales.append({"grayscale":grayscale, "red": None, "green": None, "blue": None})
                continue
            if grayscale == 0:
                logging.info(_("Grayscale {} target {} nit is 0, skip").format(grayscale, nit))
                scales.append({"grayscale":grayscale, "red": None, "green": None, "blue": None})
                continue
            self.MHC2["red_lut"]     = copy.deepcopy(pq_lut_origin["red"])
            self.MHC2["green_lut"]   = copy.deepcopy(pq_lut_origin["green"])
            self.MHC2["blue_lut"]    = copy.deepcopy(pq_lut_origin["blue"])
            self.MHC2["entry_count"] = len(pq_lut_origin["red"])
            self.icc_handle.write_MHC2(self.MHC2)
            rgb_pq = [int(grayscale)] * 3
            target_rgb_pq = np.array(rgb_pq)/1023
            channel_scale = {"grayscale": grayscale, "red": 1, "green": 1, "blue": 1}
            for loop_count in range(2):
                for idx, channel in enumerate(["red","green", "blue"]):
                    logging.info(_("Adjust {} channel").format(channel))
                    total_scale = channel_scale[channel]
                    current_scale = 1
                    step = 0.00390625
                    target = target_rgb_pq[idx]
                    done = False
                    last_ratio = None
                    while 1:
                        self.preview_var.set(True)
                        logging.info(_("Grayscale {} loop {} channel {} target: PQ->{} RGB->{}").format(
                            grayscale, loop_count, channel, target_rgb_pq, rgb_pq))
                        self.proc_color_write.write_rgb(rgb_pq, delay=0.1)
                        measure_xyz = np.array(self.proc_color_reader.read_XYZ())
                        measure_rgb_pq = XYZ_to_BT2020_PQ_rgb(measure_xyz/10000)
                        measure = measure_rgb_pq[idx]
                        ratio = measure / target
                        total_ratio = (measure_rgb_pq / target_rgb_pq).round(4).tolist()
                        if last_ratio is None:
                            last_ratio = ratio
                        logging.info(_("Grayscale {} loop {} channel {} measured: XYZ->{} PQ->{} "
                                       "ratio->{} total_ratio->{} scale->{}").format(
                            grayscale, loop_count, channel,
                            measure_xyz.round(4).tolist(),
                            measure_rgb_pq,
                            round(ratio, 4),
                            total_ratio,
                            round(current_scale, 4)))

                        if ratio > 1:
                            if current_scale > 1:
                                # 加超了
                                last = abs(last_ratio - 1)
                                current = abs(ratio - 1)
                                if current >= last:
                                    current_scale -= step
                                done = True
                            else:
                                current_scale -= step
                        elif ratio < 1:
                            if current_scale < 1:
                                # 减超了
                                last = abs(last_ratio - 1)
                                current = abs(ratio - 1)
                                if current >= last:
                                    current_scale += step
                                done = True
                            else:
                                current_scale += step
                        else:
                            done = True
                        scale = total_scale + current_scale - 1
                        pq_lut_scale = lut_scale(pq_lut_origin[channel], scale)
                        pq_lut_scale[0] = 0
                        self.MHC2[f"{channel}_lut"] = pq_lut_scale.tolist()
                        self.icc_handle.write_MHC2(self.MHC2)
                        last_ratio = ratio
                        if done:
                            channel_scale[channel] = scale
                            logging.info(_("Grayscale {} loop {} channel {} adjusted, scale {}").format(
                                grayscale, loop_count, channel, scale))
                            break
                logging.info(_("Grayscale {} loop {} calibration done, red {} green {} blue {}").format(
                    grayscale, loop_count,
                    channel_scale["red"], channel_scale["green"], channel_scale["blue"]))
            scales.append(channel_scale)
            self.proc_color_write.write_rgb(rgb_pq, delay=0.3)
            measure_xyz = np.array(self.proc_color_reader.read_XYZ())
            measure_rgb_pq = XYZ_to_bt2020_linear(measure_xyz/10000)
            logging.info(_("Grayscale {} post-calibration: CIEXYZ->{} Linear RGB:{}->{}").format(
                grayscale, measure_xyz, target_rgb_pq, measure_rgb_pq))
        logging.info(_("All grayscale calibration finished, scales: {}").format(scales))
        last_activated_scale = None
        target_pq_lut_red = copy.deepcopy(pq_lut_origin["red"])
        target_pq_lut_green = copy.deepcopy(pq_lut_origin["green"])
        target_pq_lut_blue = copy.deepcopy(pq_lut_origin["blue"])
        if scales[0]["grayscale"] == 0:
            scales[0] = copy.deepcopy(scales[1])
            scales[0]["grayscale"] = 0
        lrscale = None
        lgscale = None
        lbscale = None
        lgrayscale = None
        for scale in scales:
            cgrayscale = scale["grayscale"]
            if scale["red"] is None:
                crscale = last_activated_scale["red"]
                cgscale = last_activated_scale["green"]
                cbscale = last_activated_scale["blue"]
            else:
                last_activated_scale = scale
                crscale = scale["red"]
                cgscale = scale["green"]
                cbscale = scale["blue"]
            if lgrayscale is None:
                lrscale = crscale
                lgscale = cgscale
                lbscale = cbscale
                lgrayscale = 0
            logging.info(_("Grayscale {} RED interpolation range {}-{} scale {}-{}").format(
                cgrayscale, lgrayscale, cgrayscale, lrscale, crscale))
            logging.info(_("Grayscale {} GREEN interpolation range {}-{} scale {}-{}").format(
                cgrayscale, lgrayscale, cgrayscale, lgscale, cgscale))
            logging.info(_("Grayscale {} BLUE interpolation range {}-{} scale {}-{}").format(
                cgrayscale, lgrayscale, cgrayscale, lbscale, cbscale))
            for idx in range(lgrayscale, cgrayscale):
                
                num = cgrayscale - lgrayscale
                rstep = (crscale - lrscale) / num if num != 0 else 0
                gstep = (cgscale - lgscale) / num if num != 0 else 0
                bstep = (cbscale - lbscale) / num if num != 0 else 0
                r = idx - lgrayscale
                target_pq_lut_red[idx] = lut_scale(target_pq_lut_red[idx], lrscale + r*rstep) 
                target_pq_lut_green[idx] = lut_scale(target_pq_lut_green[idx], lgscale + r*gstep)
                target_pq_lut_blue[idx] = lut_scale(target_pq_lut_blue[idx], lbscale + r*bstep)

            target_pq_lut_red[cgrayscale] = lut_scale(target_pq_lut_red[cgrayscale], crscale)
            target_pq_lut_green[cgrayscale] = lut_scale(target_pq_lut_green[cgrayscale], cgscale)
            target_pq_lut_blue[cgrayscale] = lut_scale(target_pq_lut_blue[cgrayscale], cbscale)

            lrscale = crscale
            lgscale = cgscale
            lbscale = cbscale
            lgrayscale = cgrayscale
        self.MHC2["red_lut"]     = target_pq_lut_red
        self.MHC2["green_lut"]   = target_pq_lut_green
        self.MHC2["blue_lut"]    = target_pq_lut_blue
        self.MHC2["entry_count"] = len(target_pq_lut_red)
        self.icc_handle.write_MHC2(self.MHC2)

        return
    
    def calibrate_pq(self, eetf=False):
        self.preview_var.set(True)
        logging.info(_("Start calibrating PQ grayscale curve"))
        self.measured_pq["red"] = []
        self.measured_pq["green"] = []
        self.measured_pq["blue"] = []
        num = int(self.pq_points_var.get())
        for idx, grayscale in enumerate(np.linspace(0, 1023, num, endpoint=True).round().astype(np.int32)):
            grayscale = int(grayscale)
            rgb = [grayscale, grayscale, grayscale]
            self.proc_color_write.write_rgb(rgb, delay=0.03)
            XYZ = self.proc_color_reader.read_XYZ()
            rgb_measured = XYZ_to_BT2020_PQ_rgb(XYZ/10000)
            logging.info(_("({}/{}) Output RGB: {} Measured XYZ: {} RGB: {}").format(idx+1, num, rgb, XYZ, rgb_measured*1023))
            self.measured_pq["red"].append(float(rgb_measured[0]))
            self.measured_pq["green"].append(float(rgb_measured[1]))
            self.measured_pq["blue"].append(float(rgb_measured[2]))

        eetf_args = None
        if eetf:
            eetf_args = copy.deepcopy(self.eetf_args)
            if self.eetf_args["monitor_max"] is None:
                eetf_args["monitor_max"] = self.measure_gamut_xyz["white"][1]
            if self.eetf_args["monitor_min"] is None:
                eetf_args["monitor_min"] = self.measure_gamut_xyz["min_activated_black"][1]
        target_pq = self.MHC2
        if self.bright_var.get():
            target_pq = {"red_lut": generate_bright_pq_lut().tolist(),
                         "green_lut": generate_bright_pq_lut().tolist(),
                         "blue_lut": generate_bright_pq_lut().tolist()}
        
        red_lut = generate_mhc2_lut_from_measured_pq(
            self.measured_pq["red"], target_pq=target_pq["red_lut"])
        blue_lut = generate_mhc2_lut_from_measured_pq(
            self.measured_pq["blue"], target_pq=target_pq["blue_lut"])
        green_lut = generate_mhc2_lut_from_measured_pq(
            self.measured_pq["green"], target_pq=target_pq["green_lut"])
        
        
            
            # red_lut = generate_mhc2_lut_from_measured_pq(
            #     red_lut, target_pq=target_pq["red_lut"])
            # blue_lut = generate_mhc2_lut_from_measured_pq(
            #     blue_lut, target_pq=target_pq["blue_lut"])
            # green_lut = generate_mhc2_lut_from_measured_pq(
            #     green_lut, target_pq=target_pq["green_lut"])

        self.MHC2["red_lut"] = red_lut.tolist()
        self.MHC2["green_lut"] = green_lut.tolist()
        self.MHC2["blue_lut"] = blue_lut.tolist()
        self.MHC2["entry_count"] = len(red_lut)
        self.icc_handle.write_MHC2(self.MHC2)
        logging.info(_("PQ LUT measurement finished"))

    
    @safe_call
    def measure_pq(self):
        self.proc_color_write = ColorWriter()
        args = self.get_spotread_args()
        self.proc_color_reader = ColorReader(args)
        self.proc_color_write.write_rgb([800, 800, 800])
        answer = tk.messagebox.askokcancel(
            _("Notice"),
            _(
                "If you want to measure calibrated but unsaved/unloaded data, please enable Preview first.\n\n"
                "Resize and position the white window, place the colorimeter on it, then click OK"
            ),
        )
        if not answer:
            self.clean_color_rw_process()
            logging.info(_("User canceled measurement"))
            return
        self.freeze_ui()
        logging.info(_("Start measuring PQ response"))
        def m():
            target_white_xyz = []
            target_pq = []
            measured_pq = []
            measured_white_xyz = []
            num = 256

            for idx, grayscale in enumerate(np.linspace(0, 1023, num, endpoint=True).round().astype(np.int32)):
                grayscale = int(grayscale)
                pq = grayscale / 1023
                target_white_xyz.append(BT2020_PQ_rgb_to_XYZ([pq, pq, pq]))
                target_pq.append(pq)
                rgb = [grayscale, grayscale , grayscale]
                self.proc_color_write.write_rgb(rgb, delay=0.1)
                XYZ = np.array(self.proc_color_reader.read_XYZ())
                logging.info(_("({}/{}) Measure RGB: {} Result: {}").format(idx+1, num, rgb, XYZ))
                measured_white_xyz.append([itm/10000 for itm in XYZ])
                nit = float(XYZ[1])
                measured_pq.append(float(pq_oetf(nit)))
            
            max_nit = max([itm[1] for itm in measured_white_xyz])
            color_gamut = {"red": xyY_to_XYZ([*BT2020_xy["red"], max_nit*10000]),
                           "green": xyY_to_XYZ([*BT2020_xy["green"], max_nit*10000]),
                           "blue": xyY_to_XYZ([*BT2020_xy["blue"], max_nit*10000]),
                           "white": xyY_to_XYZ([*BT2020_xy["white"], max_nit*10000])}
            target_colored_xyz = get_srgb_measure_XYZ_suit(color_gamut)
            # target_colored_xyz.extend(get_P3D65_test_XYZ_suit(color_gamut))
            measured_colored_xyz = []
            num = len(target_colored_xyz)
            logging.info(_("Start measuring color points"))
            for idx, xyz in enumerate(target_colored_xyz):
                rgb = (XYZ_to_BT2020_PQ_rgb(xyz) * 1023).round().astype(int).tolist()
                self.proc_color_write.write_rgb(rgb, delay=0.1)
                XYZ = np.array(self.proc_color_reader.read_XYZ())
                logging.info(_("({}/{}) Measure RGB: {} Target XYZ:{} Result: {}").format(
                    idx+1, num, rgb, xyz, XYZ))
                measured_colored_xyz.append([itm/10000 for itm in XYZ])
            
            logging.info(_("Measurement finished: {}").format(measured_colored_xyz))

            return {
                "target_xyz": np.array(target_white_xyz),
                "measured_xyz": np.array(measured_white_xyz),
                "target_pq": np.array(target_pq),
                "measured_pq": np.array(measured_pq),
                "target_colored_xyz": np.array(target_colored_xyz),
                "measured_colored_xyz": np.array(measured_colored_xyz),
            }
        
        def cb(result):
            self.unfreeze_ui()
            self.clean_color_rw_process()
            if isinstance(result, Exception):
                msg = _("Measuring PQ response failed: {}").format(result)
                logging.error(msg)
                tk.messagebox.showerror(_("Error"), msg)
                raise result
            else:
                logging.info(_("Measuring PQ response finished"))
                try:
                    self._show_pq_plot(result["target_pq"], result["measured_pq"])
                except Exception as e:
                    logging.error(_("Failed to plot PQ curve: {}").format(e))
            min_care_nit = max(1/10000, result["measured_xyz"][0][1] * 1.1)
            max_care_nit = result["measured_xyz"][-1][1] * 0.9
            logging.info(_("Measured min luminance: {} nit, max luminance: {} nit").format(
                min_care_nit*10000, max_care_nit*10000))
            white_de_result = []
            logging.info(_("Start computing grayscale deltaE_ITP"))
            for idx in range(len(result["measured_xyz"])):
                if min_care_nit < result["measured_xyz"][idx][1] < max_care_nit:
                    t = result["target_xyz"][idx]
                    m = result["measured_xyz"][idx]
                    de = XYZdeltaE_ITP(t, m)
                    white_de_result.append([t, m, de])
                    logging.info(_("Target: {} Measured: {} dE_ITP: {}").format(
                        t, m, de.round(2)))
            colored_de_result = []
            logging.info(_("Start computing color deltaE_ITP"))
            for idx in range(len(result["measured_colored_xyz"])):
                t = result["target_colored_xyz"][idx]
                m = result["measured_colored_xyz"][idx]
                de = XYZdeltaE_ITP(t, m)
                colored_de_result.append([t, m, de])
                logging.info(_("Target: {} Measured: {} dE_ITP: {}").format(
                    t, m, de.round(2)))
            white_de_avg = np.mean([itm[2] for itm in white_de_result]).round(2)
            white_de_max = np.max([itm[2] for itm in white_de_result]).round(2)
            colored_de_avg = np.mean([itm[2] for itm in colored_de_result]).round(2)
            colored_de_max = np.max([itm[2] for itm in colored_de_result]).round(2)
            logging.info(_("Within luminance range ({}-{}), grayscale average deltaE_ITP: {}, max deltaE_ITP: {}").format(
                round(min_care_nit*10000,2), round(max_care_nit*10000,2),
                white_de_avg, white_de_max))
            logging.info(_("At 200 nit D65 white, color average deltaE_ITP: {}, max deltaE_ITP: {}").format(
                colored_de_avg, colored_de_max))
        self.run_in_thread(m, cb)
    
    def _show_pq_plot(self, target_pq, measured_pq):
        """
        绘制 PQ 曲线（自适应窗口大小）:
        - x 轴: 索引/(N-1)*100 (%), 0..100
        - y 轴: PQ*100 (%), 0..100
        在同一图中绘制 target_pq 与 measured_pq
        """
        tp = np.asarray(target_pq, dtype=float).flatten()
        mp = np.asarray(measured_pq, dtype=float).flatten()
        if tp.size != mp.size or tp.size < 2:
            tk.messagebox.showwarning(_("Warning"), _("Not enough data to plot"))
            return
        n = tp.size

        win = tk.Toplevel(self.root)
        win.title(_("PQ measurement curve"))
        w, h = 760, 460
        win.geometry(f"{w}x{h}")
        frm = tk.Frame(win, bg="white")
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        canvas = Canvas(frm, bg="white", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        def draw():
            canvas.delete("all")
            # 当前画布大小
            cw = max(200, canvas.winfo_width())
            ch = max(160, canvas.winfo_height())
            margin_l = 60
            margin_r = 20
            margin_t = 20
            margin_b = 50
            x0, y0 = margin_l, ch - margin_b
            x1, y1 = cw - margin_r, margin_t
            plot_w = max(1, x1 - x0)
            plot_h = max(1, y0 - y1)

            # 轴线
            canvas.create_line(x0, y0, x1, y0, fill="#444")  # x 轴
            canvas.create_line(x0, y0, x0, y1, fill="#444")  # y 轴

            # 刻度与标签（0..100 每 20）
            for p in range(0, 101, 20):
                # x 轴刻度
                xx = x0 + plot_w * (p / 100.0)
                canvas.create_line(xx, y0, xx, y0 + 5, fill="#444")
                canvas.create_text(xx, y0 + 18, text=str(p), fill="#444", font=("Segoe UI", 10))
                # y 轴刻度
                yy = y0 - plot_h * (p / 100.0)
                canvas.create_line(x0 - 5, yy, x0, yy, fill="#444")
                canvas.create_text(x0 - 28, yy, text=str(p), fill="#444", font=("Segoe UI", 10))

            # 标签
            canvas.create_text((x0 + x1) // 2, y1 - 6, text="PQ (%)", fill="#333", font=("Microsoft YaHei", 11))
            canvas.create_text((x0 + x1) // 2, y0 + 35, text=_("Position (%)"), fill="#333", font=("Microsoft YaHei", 11))

            def to_points(arr):
                pts = []
                for i, v in enumerate(arr):
                    fx = i / (n - 1)                  # 0..1
                    xx = x0 + fx * plot_w
                    fy = np.clip(float(v), 0.0, 1.0)  # v in [0,1]
                    yy = y0 - (fy * plot_h)
                    pts.append((xx, yy))
                return pts

            pts_t = to_points(tp)
            pts_m = to_points(mp)

            def draw_poly(points, color, width=2):
                flat = []
                for (px, py) in points:
                    flat.extend([px, py])
                if len(flat) >= 4:
                    canvas.create_line(*flat, fill=color, width=width, smooth=True)

            draw_poly(pts_t, "#1f77b4", 2)  # target: 蓝
            draw_poly(pts_m, "#d62728", 2)  # measured: 红

            # 图例
            box_w = 160
            box_h = 44
            canvas.create_rectangle(x1 - box_w, y1 + 8, x1 - 20, y1 + 8 + box_h, outline="#ccc", fill="#fff")
            canvas.create_line(x1 - box_w + 10, y1 + 20, x1 - box_w + 40, y1 + 20, fill="#1f77b4", width=2)
            canvas.create_text(x1 - box_w + 50, y1 + 20, text="target_pq", anchor="w", fill="#333", font=("Segoe UI", 10))
            canvas.create_line(x1 - box_w + 10, y1 + 36, x1 - box_w + 40, y1 + 36, fill="#d62728", width=2)
            canvas.create_text(x1 - box_w + 50, y1 + 36, text="measured_pq", anchor="w", fill="#333", font=("Segoe UI", 10))

        # 绑定自适应重绘
        canvas.bind("<Configure>", lambda e: draw())
        # 初次绘制
        win.after(10, draw)
    
    @safe_call
    def measure_color_accuracy(self):
        with open("data\\verify_video_extended_smpte2084_1000_p3_2020.ti1", "r") as f:
            lines = f.readlines()
        data_section = False
        rgb_list = []
        xyz_list = []
        for line in lines:
            line = line.strip()
            if line == "BEGIN_DATA":
                data_section = True
                continue
            elif line == "END_DATA":
                break
            if data_section:
                parts = line.split()
                t = list(map(float, parts))
                xyz = [itm * 6 / 10000 for itm in t[4:7]]
                xyz_list.append(xyz)
                rgb_list.append(
                    [
                        round(float(itm) * 1023)
                        for itm in XYZ_to_BT2020_PQ_rgb(xyz).tolist()
                    ]
                )

        self.proc_color_write = ColorWriter()
        args = self.get_spotread_args()
        self.proc_color_reader = ColorReader(args)

        self.proc_color_write.write_rgb([800, 800, 800])
        answer = tk.messagebox.askokcancel(
            _("Notice"),
            _(
                "If you want to measure calibrated but unsaved/unloaded data, please enable Preview first.\n\n"
                "Resize and position the white window, place the colorimeter on it, then click OK"
            ),
        )
        if not answer:
            self.clean_color_rw_process()
            logging.info(_("User canceled measurement"))
            return
        def cb(result):
            pass
        def m():
            real_xyz = []
            logging.info(_("Measured RGB list: {}").format(rgb_list))
            l = len(rgb_list)
            for i, rgb in enumerate(rgb_list):
                self.proc_color_write.write_rgb(rgb, delay=0.1)
                XYZ = self.proc_color_reader.read_XYZ()
                logging.info(_("({}/{}) Measure RGB: {} Target XYZ:{} Result: {}").format(
                    i+1, l, rgb, xyz_list[i], XYZ))
                real_xyz.append([float(itm) / 10000 for itm in XYZ])

            self.clean_color_rw_process()
            de_list = []
            for idx in range(len(real_xyz)):
                de = XYZdeltaE_ITP(real_xyz[idx], xyz_list[idx])
                de_list.append(de)
                logging.info(_("Target {}: {}").format(xyz_list[idx], de))
            logging.info(_("Measured XYZ list: {}").format(xyz_list))
            logging.info(_("Measured actual XYZ values: {}").format(real_xyz))
            logging.info(_("Measured color differences: {}").format(de_list))
            logging.info(_("Average color difference: {}, maximum difference: {}").format(
                sum(de_list) / len(de_list), max(de_list)))

        self.run_in_thread(m, cb)

    def generate_and_save_icc(self):
        path = filedialog.asksaveasfilename(
            initialdir=os.path.expanduser("~/Documents"),
            title=_("Save ICC file"),
            defaultextension=".icc",
            filetypes=[(_("ICC file"), "*.icc"), (_("All files"), "*.*")],
        )
        if not path:
            return
        filename = os.path.basename(path)
        name_without_ext = os.path.splitext(filename)[0]
        desc = [{"lang": "en", "country": "US", "text": name_without_ext}]
        self.icc_handle.write_desc(desc)
        self.icc_handle.rebuild()
        self.icc_handle.save(path)
        if self.icc_set_var.get():
            self.preview_var.set(False)
            self.set_icc(path)


if __name__ == "__main__":
    root = tk.Tk()
    app = HDRCalibrationUI(root)
    root.mainloop()
