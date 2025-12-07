import tkinter as tk
import os
import sys

# --- ensure project root in sys.path ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import copy
import re
import time
import tempfile
from tkinter import ttk, messagebox, filedialog
from meta_data import *
from icc_rw import ICCProfile
from win_display import get_all_display_config,get_monitor_rect_by_gdi_name,cp_add_display_association
from win_display import install_icc,uninstall_icc,cp_remove_display_association, luid_from_dict
from convert_utils import *
from matrix import *
from lut import eetf_from_lut
from monitor_info import get_edid_info
from i18n.i18n_loader import _

class CyberFixerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
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
        
        self.game_setting = {
            "lumi": 0,
            "saturation": 0,
            "mapping_midpoint": 2
        }

        self.icc_path = os.path.join(PROJECT_ROOT, "data", "hdr_empty.icc")
        self.init_base_icc()
        
        self.dynamic_loading_name = None
        self.dynamic_last_call = 0
        
        self.title(_("Cyberpunk HDR Fixer (by Baiyang Chunxiao)"))
        self.resizable(True, True)

        self.saturation_var = tk.DoubleVar(value=0.0)
        self.sat_display_var = tk.StringVar(value="(0.00)")
        self.map_mid_var = tk.DoubleVar(value=2.0)
        self.map_mid_display_var = tk.StringVar(value="(2.00)")
        # bind map_mid_var changes to handler (works for modern and older tkinter)
        try:
            self.map_mid_var.trace_add("write", lambda *a: self.on_map_mid_change())
        except Exception:
            self.map_mid_var.trace("w", lambda *a: self.on_map_mid_change())
        # Luminance settings (visible in UI rows under row 1)
        self.source_max_var = tk.DoubleVar(value=10000.0)   # source maximum luminance (nits)
        self.source_min_var = tk.DoubleVar(value=0.17)      # source minimum luminance (nits)
        self.monitor_max_var = tk.DoubleVar(value=1000.0)   # display maximum luminance (nits)
        self.monitor_min_var = tk.DoubleVar(value=0.0)      # display minimum luminance (nits)
        # bind change event for monitor_max_var (works with both trace_add and legacy trace)
        try:
            # modern tkinter
            self.monitor_max_var.trace_add("write", self.on_monitor_max_changed)
        except Exception:
            # fallback for older tkinter
            self.monitor_max_var.trace("w", lambda *a: self.on_monitor_max_changed(*a))
        self.monitor_list = list(self.human_display_config_map.keys())
        self.monitor_list.sort()
        self.monitor_var = tk.StringVar(value=self.monitor_list[0] if self.monitor_list else _("No Monitor Found"))
        self.config_name_var = tk.StringVar(value="cyberpunk2077-hdr-fixed")
        
        self.game_setting_display_var = tk.StringVar(value="")
 
        self._build_ui()
        self._center_window(500, 380)
        self.on_monitor_max_changed()
        

    def _center_window(self, w=340, h=340):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry("{}x{}+{}+{}".format(w, h, x, y))

    def _build_ui(self):
        pad = {"padx": 14, "pady": 10}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **pad)

        ttk.Label(frm, text=_("Display:"), font=("Microsoft YaHei", 11)).grid(row=0, column=0, sticky="w") 
        monitor_box = ttk.Combobox(
            frm,
            textvariable=self.monitor_var,
            values=self.monitor_list,
            state="readonly", width=22
        )
        monitor_box.grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text=_("Profile name:"), font=("Microsoft YaHei", 11)).grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=self.config_name_var, width=26).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6,0))

        ttk.Label(frm, text=_("Saturation:"), font=("Microsoft YaHei", 11)).grid(row=2, column=0, sticky="w", pady=(8,0))
        ttk.Label(frm, textvariable=self.sat_display_var).grid(row=2, column=0, sticky="w", padx=(53,0), pady=(8,2))
        sat_scale = ttk.Scale(
            frm,
            from_=0.0,
            to=1.0,
            orient="horizontal",
            variable=self.saturation_var,
            command=self.on_saturation_change,
            length=180
        )
        sat_scale.grid(row=2, column=1, sticky="w", pady=(8,0))
        # display current saturation value next to the slider

        # Make clicks jump to the exact mouse position and support dragging.
        sat_scale.bind("<Button-1>", self.on_scale_click)
        sat_scale.bind("<B1-Motion>", self.on_scale_motion)

        # ---------- luminance input rows (placed under row 2) ----------
        ttk.Label(frm, text=_("Source max luminance (nits):"), font=("Microsoft YaHei", 10)).grid(row=3, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=self.source_max_var, width=18).grid(row=3, column=1, sticky="w", pady=(6,0))

        ttk.Label(frm, text=_("Source min luminance (nits):"), font=("Microsoft YaHei", 10)).grid(row=4, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=self.source_min_var, width=18).grid(row=4, column=1, sticky="w", pady=(6,0))

        ttk.Label(frm, text=_("Display max luminance (nits):"), font=("Microsoft YaHei", 10)).grid(row=5, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=self.monitor_max_var, width=18).grid(row=5, column=1, sticky="w", pady=(6,0))

        ttk.Label(frm, text=_("Display min luminance (nits):"), font=("Microsoft YaHei", 10)).grid(row=6, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=self.monitor_min_var, width=18).grid(row=6, column=1, sticky="w", pady=(6,0))
        # ---------- end luminance rows ----------
 
        # 映射中点（放在按钮上面）
        ttk.Label(frm, text=_("Tone-mapping midpoint:"), font=("Microsoft YaHei", 10)).grid(row=7, column=0, sticky="w", pady=(8,2))
        ttk.Label(frm, textvariable=self.map_mid_display_var).grid(row=7, column=0, sticky="w", padx=(85,0), pady=(8,2))
        self.map_scale = ttk.Scale(
            frm,
            from_=0.1,
            to=3.0,
            orient="horizontal",
            variable=self.map_mid_var,
            # command=self.on_map_mid_change,
            length=180
        )
        self.map_scale.grid(row=7, column=1, sticky="w", pady=(8,0))
        # click/drag support like saturation slider
        self.map_scale.bind("<Button-1>", self.on_map_scale_click)
        self.map_scale.bind("<B1-Motion>", self.on_map_scale_motion)

         # 按钮
        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=3, sticky="w", pady=(18, 0))
        ttk.Button(btns, text=_("Import ICC"), command=self.on_import_icc, width=12).pack(side="left")
        ttk.Button(btns, text=_("Generate & Load"), command=self.on_generate, width=12).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text=_("Cancel Load"), command=self.on_cancel_load, width=12).pack(side="left", padx=(8, 0))
        # 按钮下面的文字标签（用于显示状态/提示）
        ttk.Label(frm, textvariable=self.game_setting_display_var, font=("Microsoft YaHei", 10), foreground="blue").grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

    def init_base_icc(self):
        self.icc_handle = ICCProfile(self.icc_path)
        self.icc_data = self.icc_handle.read_all()
        self.MHC2 = copy.deepcopy(self.icc_data["MHC2"])
    
    def on_import_icc(self):
        path = filedialog.askopenfilename(
            initialdir=os.path.expanduser("C:/Windows/System32/spool/drivers/color"),
            title=_("Import ICC file"),
            defaultextension=".icc",
            filetypes=[(_("ICC files"), "*.icc"), (_("All files"), "*.*")],
        )
        if not path:
            return
        self.icc_path = path
        self.init_base_icc()
        self.monitor_max_var.set(self.icc_data["lumi"][0][0])
        self.monitor_min_var.set(self.MHC2["min_luminance"])

    def on_scale_click(self, event):
        """Set scale value to the mouse click position (and update display)."""
        widget = event.widget
        try:
            w = widget.winfo_width()
            if w <= 0:
                return "break"
            x = max(0, min(event.x, w))
            f = float(widget.cget("from"))
            t = float(widget.cget("to"))
            frac = x / float(w)
            val = f + frac * (t - f)
            # update the associated variable and the visible slider handle
            self.saturation_var.set(val)
            # call the display update (same as command)
            self.on_saturation_change(str(val))
        except Exception:
            pass
        # prevent default handler which may jump to ends
        return "break"

    def on_scale_motion(self, event):
        """Update scale value while dragging (B1 motion)."""
        widget = event.widget
        try:
            w = widget.winfo_width()
            if w <= 0:
                return
            x = max(0, min(event.x, w))
            f = float(widget.cget("from"))
            t = float(widget.cget("to"))
            frac = x / float(w)
            val = f + frac * (t - f)
            self.saturation_var.set(val)
            self.on_saturation_change(str(val))
        except Exception:
            pass
    
    def on_saturation_change(self, v):
        """Update the saturation display label when the slider moves."""
        try:
            val = float(v)
        except Exception:
            val = self.saturation_var.get()
        self.sat_display_var.set(_("({:.2f})").format(val))
        # self.dynamic_load_icc()
    
    def on_map_mid_change(self, *args):
        """
        Called when mapping-midpoint slider value changes.
        Accepts being called from Scale (value passed) or from variable trace.
        """
        def map_midpoint_to_min_lumi(x):
            x = float(x)
            if x <= 0.1:
                return 0.01
            if x < 1.0:
                a = (0.05 - 0.01) / (1.0 - 0.1)    # 0.04 / 0.9
                b = 0.01 - a * 0.1
                return a * x + b
            if x < 2.0:
                a = (0.17 - 0.05) / (2.0 - 1.0)    # 0.12
                b = 0.05 - a * 1.0
                return a * x + b
            if x < 3.0:
                a = (0.25 - 0.17) / (3.0 - 2.0)    # 0.08
                b = 0.17 - a * 2.0
                return a * x + b
            return 0.25 
        try:
            val = float(self.map_mid_var.get())
        except Exception:
            return
        self.map_mid_display_var.set(_("({:.1f})").format(val))
        # placeholder for additional behavior on mapping-midpoint change
        # e.g. self.game_setting["mapping_midpoint"] = val
        self.game_setting["mapping_midpoint"] = round(val, 1)
        source_min = map_midpoint_to_min_lumi(round(val, 1))
        self.source_min_var.set("{:.2f}".format(source_min))
        s = _("In-game settings:\n")
        s += _("Max brightness: {}" ).format(self.game_setting['lumi'])
        s += _("    Tone-mapping midpoint: {}" ).format(self.game_setting['mapping_midpoint'])
        s += _("    Saturation: {}\n" ).format(self.game_setting['saturation'])
        self.game_setting_display_var.set(s)
        

    def on_map_scale_click(self, event):
        """Set mapping-midpoint scale value to the mouse click position (and update display)."""
        widget = event.widget
        try:
            w = widget.winfo_width()
            if w <= 0:
                return "break"
            x = max(0, min(event.x, w))
            f = float(widget.cget("from"))
            t = float(widget.cget("to"))
            frac = x / float(w)
            val = f + frac * (t - f)
            self.map_mid_var.set(val)
        except Exception:
            pass
        return "break"

    def on_map_scale_motion(self, event):
        """Update mapping-midpoint scale value while dragging (B1 motion)."""
        widget = event.widget
        try:
            w = widget.winfo_width()
            if w <= 0:
                return
            x = max(0, min(event.x, w))
            f = float(widget.cget("from"))
            t = float(widget.cget("to"))
            frac = x / float(w)
            val = f + frac * (t - f)
            self.map_mid_var.set(val)
        except Exception:
            pass
    
    def on_monitor_max_changed(self, *args):
        def get_game_lumi(monitor_max):
            l = 0.771569 * monitor_max - 1.894394
            l  = round(l / 10)*10
            print(l)
            if l < 500:
                l = 500
            return l
        try:
            monitor_max = float(self.monitor_max_var.get())
        except Exception:
            return
        if monitor_max > 10000:
            monitor_max = 10000
            self.monitor_max_var.set("10000")
            return
        elif monitor_max < 0:
            monitor_max = 0
            self.monitor_max_var.set("0")
            return
        suggest_message = ""
        if monitor_max < 500:
            self.map_scale.set("1.5")
            suggest_message = "1.4-1.7"
        elif monitor_max < 1000:
            self.map_scale.set("2.1")
            suggest_message = "1.8-2.2"
        else:
            self.map_scale.set("2.4")
            suggest_message = "2.2-3"
        game_max = get_game_lumi(monitor_max)
        game_max = game_max if game_max <= 3000 else 3000
        source_max = float(game_max) * 2.5
        source_max = source_max if source_max >= monitor_max else monitor_max
        self.game_setting["lumi"] = game_max
        self.game_setting_display_var.set(str(self.game_setting))
        s = _("In-game settings:\n")
        s += _("Max brightness: {}" ).format(self.game_setting['lumi'])
        s += _("  Tone-mapping midpoint: {} (recommend: {})" ).format(self.game_setting['mapping_midpoint'], suggest_message)
        s += _("  Saturation: {}\n" ).format(self.game_setting['saturation'])
        self.game_setting_display_var.set(s)
        self.source_max_var.set(source_max)

    def set_icc(self, path):
        install_icc(path)
        icc_name = os.path.basename(path)
        monitor = self.monitor_var.get()
        info = self.human_display_config_map.get(monitor)
        luid = luid_from_dict(info["adapter_luid"])
        sid  = info["source"]["id"]
        hdr = False
        if info["color_work_status"] == "hdr":
            hdr = True
        cp_add_display_association(luid, sid, icc_name, set_as_default=True, associate_as_advanced_color=hdr)
    
    def clean_icc(self, name):
        path = f"{name}.icc"
        monitor = self.monitor_var.get()
        info = self.human_display_config_map.get(monitor)
        luid = luid_from_dict(info["adapter_luid"])
        sid  = info["source"]["id"]
        hdr = False
        if info["color_work_status"] == "hdr":
            hdr = True
        cp_remove_display_association(luid, sid, path, associate_as_advanced_color=hdr)
        uninstall_icc(path, force=True)

    @staticmethod
    def line_intersection_in_unit_square(a, b, c, d, eps=1e-9):
        """
        Compute the intersection of two infinite lines defined by points a-b and c-d.
        Only return (x, y) if the intersection lies inside the unit square [0,1]x[0,1],
        otherwise return None.
        If the lines are parallel or coincident (no unique intersection), return None.

        Args:
        a, b, c, d: each a tuple (x, y)
        eps: tolerance for floating point errors

        Returns:
        (x, y) or None
        """
        x1, y1 = a; x2, y2 = b
        x3, y3 = c; x4, y4 = d

        # Degenerate input check (two identical points, cannot define a line)
        if abs(x1 - x2) < eps and abs(y1 - y2) < eps:
            return None
        if abs(x3 - x4) < eps and abs(y3 - y4) < eps:
            return None

        # Determinant to check if lines are parallel or coincident
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < eps:
            return None

        # Intersection point (infinite lines)
        px = ((x1*y2 - y1*x2) * (x3 - x4) - (x1 - x2) * (x3*y4 - y3*x4)) / denom
        py = ((x1*y2 - y1*x2) * (y3 - y4) - (y1 - y2) * (x3*y4 - y3*x4)) / denom

        # Check if inside unit square
        if -eps <= px <= 1 + eps and -eps <= py <= 1 + eps:
            px = min(max(px, 0.0), 1.0)  # clamp within [0,1] if slightly out due to float error
            py = min(max(py, 0.0), 1.0)
            return (px, py)
        return None
    
    @staticmethod
    def scale_segment_about_first(p1, p2, scale):
        """
        Scale the segment defined by points p1->p2 about p1, keeping slope unchanged.
        - p1, p2: (x, y) tuples or lists
        - scale: numeric factor (1.0 keeps p2; 0.5 moves p2 halfway to p1; negative allowed)
        Returns the new second point (x2_new, y2_new).
        """
        x1, y1 = float(p1[0]), float(p1[1])
        x2, y2 = float(p2[0]), float(p2[1])
        dx = x2 - x1
        dy = y2 - y1
        return (x1 + dx * scale, y1 + dy * scale)
    
    def get_eetf_args(self):
        args = {}
        args["monitor_min"] = float(self.monitor_min_var.get())
        args["monitor_max"] = float(self.monitor_max_var.get())
        args["source_min"] = float(self.source_min_var.get())
        args["source_max"] = float(self.source_max_var.get())
        if 10000 < args["monitor_max"] <= 200:
            messagebox.showerror(_("Error"), _("Display max luminance must be between 200 and 10000"))
            raise ValueError("Display max luminance must be between 200 and 10000")
        if 10000 < args["source_max"] <= 200:
            messagebox.showerror(_("Error"), _("Source max luminance must be between 200 and 10000"))
            raise ValueError("Source max luminance must be between 200 and 10000")
        if args["monitor_min"] > 10 or args["monitor_min"] < 0:
            messagebox.showerror(_("Error"), _("Display min luminance must be between 0 and 10"))
            raise ValueError("Display min luminance must be between 0 and 10")
        if args["source_min"] > 10 or args["source_min"] < 0:
            messagebox.showerror(_("Error"), _("Source min luminance must be between 0 and 10"))
            raise ValueError("Source min luminance must be between 0 and 10")
        return args

    def get_convert_suit(self, saturation):
        source_gamut = copy.deepcopy(sRGB_xy)
        # source_gamut["RG"] = [0.4194, 0.5053]
        # source_gamut["RB"] = [0.3209, 0.1542]
        # source_gamut["GB"] = [0.2247, 0.3287]
        
        target_gamut_max = {
            "red": self.line_intersection_in_unit_square(D65_WHITE_POINT, source_gamut["red"], 
                                           P3D65_xy["green"], P3D65_xy["red"]),
            "green": self.line_intersection_in_unit_square(D65_WHITE_POINT, source_gamut["green"],
                                             P3D65_xy["red"], P3D65_xy["green"]),
            "blue": copy.deepcopy(P3D65_xy["blue"]),
            # "RG": self.line_intersection_in_unit_square(D65_WHITE_POINT, source_gamut["RG"],
            #                                P3D65_xy["red"], P3D65_xy["green"]),
            # "RB": self.line_intersection_in_unit_square(D65_WHITE_POINT, source_gamut["RB"],
            #                                P3D65_xy["red"], P3D65_xy["blue"]),
            # "GB": self.line_intersection_in_unit_square(D65_WHITE_POINT, source_gamut["GB"],
            #                                P3D65_xy["green"], P3D65_xy["blue"])
        }
        target_gamut_max = P3D65_xy
        target_gamut = {
            "red": self.scale_segment_about_first(source_gamut["red"], target_gamut_max["red"], saturation),
            "green": self.scale_segment_about_first(source_gamut["green"], target_gamut_max["green"], saturation),
            "blue": copy.deepcopy(P3D65_xy["blue"]),
            # "RG": self.scale_segment_about_first(source_gamut["RG"], target_gamut_max["RG"], saturation),
            # "RB": self.scale_segment_about_first(source_gamut["RB"], target_gamut_max["RB"], saturation),
            # "GB": self.scale_segment_about_first(source_gamut["GB"], target_gamut_max["GB"], saturation)
        }
        print(source_gamut)
        print(target_gamut)
        # for color in ["red", "green", "blue", "RG", "RB", "GB"]:
        #     print("{}: {} {}".format(color, source_gamut[color], target_gamut[color]))
            
        source_points = []
        target_points = []
        # for color in ["red", "green", "blue", "RG", "RB", "GB"]:
        for color in ["red", "green", "blue"]:
            s = xyY_to_XYZ([*source_gamut[color], 100])
            t = xyY_to_XYZ([*target_gamut[color], 100])
            source_points.append(s)
            target_points.append(t)

        return source_points, target_points

    def get_selected_pnp_device_id(self):
        monitor = self.monitor_var.get()
        return self.human_display_config_map[monitor]["pnp_device_id"]

    def dynamic_load_icc(self):
        if time.time() - self.dynamic_last_call < 0.1:
            return

        self.dynamic_last_call = time.time()
        name = self.config_name_var.get().strip()
        name0 = name + "_0"
        name1 = name + "_1"
        if self.dynamic_loading_name is None:
            self.dynamic_loading_name = name0
        if self.dynamic_loading_name == name0:
            self.config_name_var.set(name1)
            self.on_generate()
            self.config_name_var.set(name0)
            self.on_cancel_load()
            self.config_name_var.set(name)
            self.dynamic_loading_name = name1
            return
        elif self.dynamic_loading_name == name1:
            self.config_name_var.set(name0)
            self.on_generate()
            self.config_name_var.set(name1)
            self.on_cancel_load()
            self.config_name_var.set(name)
            self.dynamic_loading_name = name0
            return
        
    def on_generate(self):
        self.init_base_icc()
        monitor = self.monitor_var.get()
        display_config = self.human_display_config_map.get(monitor)
        saturation = float(self.saturation_var.get())
        print(saturation)
        if display_config["color_work_status"] != "hdr":
            messagebox.showinfo(_("Info"), _("HDR is currently off. Please enable HDR in system settings and restart this app."))
            return
        if self.icc_path == "hdr_empty.icc":
            edid_info = get_edid_info(self.get_selected_pnp_device_id())
            self.icc_handle.write_XYZType('rXYZ', [l2_normalize_XYZ(xyY_to_XYZ([*edid_info["red"], 100]))])
            self.icc_handle.write_XYZType('gXYZ', [l2_normalize_XYZ(xyY_to_XYZ([*edid_info["green"], 100]))])
            self.icc_handle.write_XYZType('bXYZ', [l2_normalize_XYZ(xyY_to_XYZ([*edid_info["blue"], 100]))])
            self.icc_handle.write_XYZType('wtpt', [l2_normalize_XYZ(xyY_to_XYZ([*edid_info["white"], 100]))])

        source_points, target_points = self.get_convert_suit(saturation)
        print(source_points)
        print(target_points)
        monitor_max = float(self.monitor_max_var.get())
        d65_xyz = xyY_to_XYZ([*D65_WHITE_POINT, monitor_max*0.8])
        source_points.append(d65_xyz)
        target_points.append(d65_xyz)
        matrix = fit_XYZ2XYZ(source_points, target_points)
        # matrix = fit_xyz2xyz_with_white_lock(source_points, target_points, d65_xyz, d65_xyz)
        matrix[np.abs(matrix) < 1e-9] = 0.0
        ori_matrix = np.array(self.MHC2["matrix"]).reshape(3, 3)
        matrix2 = ori_matrix @ matrix
        self.MHC2['matrix'] = matrix2.flatten().tolist()
        
        eetf_args = self.get_eetf_args()
        red_lut = eetf_from_lut(self.MHC2["red_lut"], eetf_args)
        blue_lut = eetf_from_lut(self.MHC2["blue_lut"], eetf_args)
        green_lut = eetf_from_lut(self.MHC2["green_lut"], eetf_args)
        self.MHC2["red_lut"] = red_lut.tolist()
        self.MHC2["blue_lut"] = blue_lut.tolist()
        self.MHC2["green_lut"] = green_lut.tolist()
        self.MHC2["entry_count"] = len(red_lut)
        
        self.icc_handle.write_MHC2(self.MHC2)

        name = self.config_name_var.get().strip()
        temp_dir = tempfile.gettempdir()
        icc_file_name = name + ".icc"
        path = os.path.join(temp_dir, icc_file_name)
        desc = [{'lang': 'en', 'country': 'US', 'text': name}]
        self.icc_handle.write_desc(desc)
        self.icc_handle.rebuild()
        self.icc_handle.save(path)
        self.set_icc(path)
        os.remove(path)

    def on_cancel_load(self):
        name = self.config_name_var.get().strip()
        try:
            self.clean_icc(name)
        except Exception as e:
            print(f"Error cleaning ICC: {e}")

if __name__ == "__main__":
    app = CyberFixerApp()
    app.mainloop()