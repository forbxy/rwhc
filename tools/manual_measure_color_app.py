import tkinter as tk
from tkinter import ttk, messagebox
import traceback
import threading
import queue
import time
import os
import sys
import json
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False

# --- ensure project root in sys.path ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from color_rw import ColorReader, ColorWriter
from convert_utils import *
from i18n.i18n_loader import _

class ColorMeasureApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(_("Color Measurement Tool"))
        self.resizable(False, False)

        # State
        self.reader = None
        self.writer = None
        self.read_queue = queue.Queue()
        self._build_ui()
        self._center_window(520, 400)

    def _center_window(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry("{}x{}+{}+{}".format(w, h, x, y))

    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, **pad)

        # Row 0: ColorReader args + ColorWriter mode
        row0 = ttk.Frame(root)
        row0.pack(fill="x", pady=(0, 4))
        ttk.Label(row0, text=_("spotread arguments:"), width=12).pack(side="left")
        self.args_var = tk.StringVar(value="-x -y e")  # Adjust to your needs
        ttk.Entry(row0, textvariable=self.args_var, width=42).pack(side="left", padx=(0, 0))

        ttk.Label(row0, text=_("Output mode:")).pack(side="left")
        self.mode_var = tk.StringVar(value="hdr_10")
        ttk.Combobox(
            row0, textvariable=self.mode_var,
            width=18,                      # Broaden dropdown to avoid clipping
            values=["hdr_10","hdr_8", "sdr_8", "sdr_10"], state="readonly"
        ).pack(side="left", padx=(4, 0))

        # Row 1: buttons
        row1 = ttk.Frame(root)
        row1.pack(fill="x", pady=(0, 6))
        ttk.Button(row1, text=_("Initialize"), width=14, command=self.on_init).pack(side="left")
        ttk.Button(row1, text=_("Close Connection"), width=12, command=self.on_close_conn).pack(side="left", padx=(8, 0))

        # Row 2: RGB input
        row2 = ttk.Frame(root)
        row2.pack(fill="x", pady=(0, 4))
        ttk.Label(row2, text=_("RGB(0-1023):"), width=14).pack(side="left")
        self.r_var = tk.IntVar(value=1023)
        self.g_var = tk.IntVar(value=1023)
        self.b_var = tk.IntVar(value=1023)
        ttk.Spinbox(row2, from_=0, to=1023, textvariable=self.r_var, width=6).pack(side="left")
        ttk.Spinbox(row2, from_=0, to=1023, textvariable=self.g_var, width=6).pack(side="left", padx=(6, 0))
        ttk.Spinbox(row2, from_=0, to=1023, textvariable=self.b_var, width=6).pack(side="left", padx=(6, 0))
        ttk.Button(row2, text=_("Send RGB"), width=10, command=self.on_send_rgb).pack(side="left", padx=(12, 0))
        ttk.Button(row2, text=_("Write and Measure"), width=12, command=self.on_send_and_measure).pack(side="left", padx=(6, 0))

         # Row 3: measurements
        row3 = ttk.Frame(root)
        row3.pack(fill="x", pady=(0, 4))
        ttk.Button(row3, text=_("Read XYZ"), width=12, command=self.on_measure_once).pack(side="left")
        ttk.Button(row3, text=_("Measure RGBW"), width=14, command=self.on_measure_rgbw).pack(side="left", padx=(6,0))
        ttk.Button(row3, text=_("Measure Luma Curve"), width=14, command=self.on_measure_luma_curve).pack(side="left", padx=(6,0))
        self.xyz_label = ttk.Label(row3, text="XYZ: -/-/-")
        self.xyz_label.pack(side="left", padx=(12, 0))
        self.xyy_var = tk.StringVar(value=_("xyY: -/-/-"))
        self.xyy_entry = ttk.Entry(row3, textvariable=self.xyy_var, width=36, state="readonly")
        self.xyy_entry.pack(side="left", padx=(10, 0))
        self._enable_select_copy(self.xyy_entry)
        ttk.Button(row3, text=_("Copy"), width=6, command=lambda: self._copy_to_clipboard(self.xyy_var.get())).pack(side="left", padx=(6, 0))

        # Log area
        frm_log = ttk.LabelFrame(root, text=_("Log"))
        frm_log.pack(fill="both", expand=True, pady=(6, 0))
        self.log_txt = tk.Text(frm_log, height=10, width=64)
        self.log_txt.pack(fill="both", expand=True, padx=6, pady=6)

        # Close handler
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

    # Connection handlers
    def on_init(self):
        try:
            self._ensure_writer(recreate=True)
            self._ensure_reader(recreate=True)
            self._log(_("Initialized ColorWriter and ColorReader"))
        except Exception as e:
            messagebox.showerror(_("Error"), _("Initialization failed: {}" ).format(e))

    def on_close_conn(self):
        self._terminate_reader()
        self._terminate_writer()
        self._log(_("Connections closed"))

    # Send and measure
    def on_send_rgb(self):
        try:
            self._ensure_writer()
            rgb = self._get_rgb()
            self.writer.write_rgb(rgb, delay=0.1)
            self._log(_("RGB sent: {}" ).format(rgb))
        except Exception as e:
            messagebox.showerror(_("Error"), _("Send failed: {}" ).format(e))

    def on_measure_once(self):
        """Read XYZ once synchronously."""
        try:
            self._ensure_reader()
            xyz = self.reader.read_XYZ()
            self._apply_xyz(xyz)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror(_("Error"), _("Read failed: {}" ).format(e))

    def on_send_and_measure(self):
        """Send current RGB and measure synchronously."""
        try:
            self._ensure_writer()
            self._ensure_reader()
            rgb = self._get_rgb()
            self.writer.write_rgb(rgb)
            self._log(_("RGB sent: {}" ).format(rgb))
            xyz = self.reader.read_XYZ()
            self._apply_xyz(xyz)
        except Exception as e:
            messagebox.showerror(_("Error"), _("Write/read failed: {}" ).format(e))

    def on_measure_rgbw(self):
        """Synchronously measure R/G/B/W (may block UI; thread if needed)."""
        try:
            self._ensure_writer()
            self._ensure_reader()
        except Exception as e:
            messagebox.showerror(_("Error"), _("Initialization failed: {}" ).format(e))
            return
        m = self.writer.mode.split("_")[1]  # 8 or 10
        max = 255 if m == "8" else 1023
        samples = [
            ("R", [max, 0, 0]),
            ("G", [0, max, 0]),
            ("B", [0, 0, max]),
            ("W", [max, max, max]),
        ]
        lines = []
        for name, rgb in samples:
            try:
                self.writer.write_rgb(rgb, delay=0.1)
                time.sleep(0.12)
                xyz = self.reader.read_XYZ()
                print(xyz)
                if xyz.size == 3 and np.isfinite(xyz[:3]).all():
                    X, Y, Z = map(float, xyz[:3])
                    x, y = XYZ_to_xy([X, Y, Z])
                    self._log(_("{}: XYZ {:.4f},{:.4f},{:.4f} xy {:.4f},{:.4f}" ).format(name, X, Y, Z, x, y))
                    lines.append("{:.4f},{:.4f}".format(x, y))
                else:
                    self._log(_("{}: read failed").format(name))
                    lines.append("{}:failed".format(name))
            except Exception as e:
                self._log(_("{} measurement error: {}" ).format(name, e))
                lines.append("{}:error".format(name))
        self._log(_("RGBW summary:\n{}" ).format("\n".join(lines)))
    
    def on_measure_luma_curve(self):
        """Start a 128-point luma curve measurement."""
        try:
            self._ensure_writer()
            self._ensure_reader()
        except Exception as e:
            messagebox.showerror(_("Error"), _("Initialization failed: {}" ).format(e))
            return
        threading.Thread(target=self._measure_luma_curve_worker, daemon=True).start()

    def _measure_luma_curve_worker(self):
        try:
            mode = (self.writer.mode or "").lower()
            is_hdr = mode.startswith("hdr")
            bits = 10 if mode.endswith("10") else 8
            max_code = 1023 if bits == 10 else 255

            # 1) Measure peak white
            self.writer.write_rgb([max_code]*3, delay=0.1)
            xyz_white = self.reader.read_XYZ()
            if xyz_white.size != 3:
                self._log(_("White measurement failed"))
                return
            Y_white = float(xyz_white[1])
            if Y_white <= 0:
                self._log(_("White luminance invalid"))
                return
            self._log(_("Peak luminance (white): {:.2f} nits" ).format(Y_white))

            # 2) Prepare 128 gray codes
            NUM = 64
            codes = np.linspace(0, max_code, NUM).round().astype(int)
            meas_Y = []
            l = len(codes)
            for idx, c in enumerate(codes):
                self.writer.write_rgb([int(c)]*3, delay=0.1)
                xyz = self.reader.read_XYZ()
                xy = XYZ_to_xy(xyz)
                self._log(_("({}/{}) Gray {}: XYZ {} xy {}" ).format(idx + 1, l, c, xyz, xy))
                # Log normalized gray measurement progress
                if xyz.size == 3:
                    meas_Y.append(float(xyz[1]))
                else:
                    meas_Y.append(np.nan)
            meas_Y = np.array(meas_Y, dtype=float)
            print(meas_Y)
            

            # 3) Generate target curve (t is normalized input)
            t = np.linspace(0, 1, NUM)
            if is_hdr:
                # HDR: map measured peak to absolute nits
                linear_target = t
                encoded_measured = np.clip(meas_Y / 10000, 0, None)
                linear_measured = pq_oetf(np.clip(meas_Y, 0, None))
                encoded_target = pq_eotf(t)/10000
                encoded_sRGB = srgb_encode(t)
            else:
                linear_target = t
                encoded_measured = np.clip(meas_Y / Y_white, 0, None)  # Relative linear luminance (EOTF output)
                print("encoded_measured json type:\n", json.dumps(encoded_measured.astype(float).tolist()))
                linear_measured = gamma_decode(np.clip(encoded_measured, 0, 1), 2.2)
                encoded_target = gamma_encode(t, 2.2)
                encoded_sRGB = srgb_encode(t)

            # Example breaks for segmented axis visualization
            # Example: display segments evenly to observe low luminance differences
            custom_breaks_gamma22 = [0.0, 0.029, 0.133, 0.325, 0.61, 1.0]
            custom_breaks_pq = [0.0, 0.0002429, 0.0032448, 0.0244005, 0.1555178, 1.0]  
            self.after(0, lambda: self._show_luma_curve_plots(
                t, linear_target, linear_measured,
                encoded_target, encoded_measured, encoded_sRGB,
                is_hdr, bits, Y_white,
                custom_breaks_pq if is_hdr else custom_breaks_gamma22
            ))
        except Exception as e:
            traceback.print_exc()
            self._log(_("Luma curve measurement error: {}" ).format(e))

    # --- Segmented axis conversion ---
    def _segment_equal_transform(self, y, breaks):
        b = np.asarray(breaks, float)
        y = np.asarray(y, float)
        y_clip = np.clip(y, b[0], b[-1])
        idx = np.searchsorted(b, y_clip, side="right") - 1
        idx = np.clip(idx, 0, b.size - 2)
        seg_span = b[idx+1] - b[idx]
        seg_span = np.where(seg_span == 0, 1, seg_span)
        frac = (y_clip - b[idx]) / seg_span
        seg_len = 1.0 / (b.size - 1)
        return (idx + frac) * seg_len

    def _show_luma_curve_plots(self, t, linear_target, linear_measured,
                               encoded_target, encoded_measured, encoded_sRGB,
                               is_hdr, bits, Y_white,
                               encoded_axis_breaks=None):
        try:
            import matplotlib
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.pyplot as plt
        except Exception:
            messagebox.showerror(_("Missing dependency"), _("matplotlib is required\npip install matplotlib"))
            return

        win = tk.Toplevel(self)
        win.title(_("Luma Curve ({}/{:d}bit)" ).format("HDR" if is_hdr else "SDR", bits))
        win.geometry("900x620")

        nb = ttk.Notebook(win); nb.pack(fill="both", expand=True)

        # Linear view tab
        frm_o = ttk.Frame(nb); nb.add(frm_o, text=_("linear"))
        fig_o, ax_o = plt.subplots(figsize=(7.5,4.6), dpi=100)
        ax_o.plot(t, linear_target, label=_("target"), linewidth=2)
        ax_o.plot(t, linear_measured, label=_("measured"), linestyle="--")
        ax_o.set_xlabel(_("input")); ax_o.set_ylabel(_("linear"))
        ax_o.set_title(_("linear ({})" ).format("PQ" if is_hdr else "Gamma2.2"))
        ax_o.grid(alpha=0.3)
        ax_o.legend(loc="lower right")
        FigureCanvasTkAgg(fig_o, master=frm_o).get_tk_widget().pack(fill="both", expand=True)

        # Encoded view tab
        frm_e = ttk.Frame(nb); nb.add(frm_e, text=_("encoded"))
        fig_e, ax_e = plt.subplots(figsize=(7.5,4.6), dpi=100)

        # Custom curve input area (top controls)
        control_bar = ttk.Frame(frm_e)
        control_bar.pack(fill="x", pady=(2, 2))
        ttk.Label(control_bar, text=_("Custom curve (JSON array):")).pack(side="left")
        custom_json_var = tk.StringVar()
        entry_custom = ttk.Entry(control_bar, textvariable=custom_json_var, width=46)
        entry_custom.pack(side="left", padx=(4, 4))

        # Format help dialog
        def show_format_help():
            msg = "\n".join([
                "Input examples:",
                "1) Single curve: [0,0.1,0.2,...]",
                "2) Multiple curves: [[...],[...]]",
                "3) Named curves: [{{\"name\":\"curveA\",\"values\":[...]}}, {{\"name\":\"B\",\"values\":[...]}}]",
                "Length must match sample count (current: {}). Supports values 0-1.",
                "Custom curves apply current segmented axis transform if enabled.",
            ]).format(len(t))
            messagebox.showinfo(_("Format"), msg)
        ttk.Button(control_bar, text=_("Format"), width=5, command=show_format_help).pack(side="left", padx=(0,4))

        # Placeholder: add-curve button packs after base plots
        btn_add_curve = ttk.Button(control_bar, text=_("Add curve"))
        btn_add_curve.pack(side="left")

        custom_axis = (encoded_axis_breaks is not None
                       and len(encoded_axis_breaks) >= 2)

        # Store added lines for future operations
        added_lines = []

        def _transform_if_needed(y_arr):
            if custom_axis:
                return self._segment_equal_transform(y_arr, encoded_axis_breaks)
            return y_arr

        # Custom curve handler
        def on_add_curve():
            txt = custom_json_var.get().strip()
            if not txt:
                return
            try:
                data = json.loads(txt)
            except Exception as e:
                messagebox.showerror(_("JSON error"), _("Parse failed: {}" ).format(e))
                return

            curves = []

            def ensure_list_numbers(arr):
                arr_np = np.asarray(arr, dtype=float)
                if arr_np.shape != (len(t),):
                    raise ValueError("Curve length must be {} (got {})".format(len(t), arr_np.shape))
                arr_np = np.clip(arr_np, 0.0, 10.0)  # Allow >1 values (PQ encoded handled earlier)
                return arr_np

            # Structure detection
            if isinstance(data, list):
                if len(data) == 0:
                    messagebox.showwarning(_("Notice"), _("Empty array"))
                    return
                # case A: list of numbers
                if all(isinstance(x, (int, float)) for x in data):
                    curves.append(("curve1", ensure_list_numbers(data)))
                # case B: list of list numbers
                elif all(isinstance(x, list) and len(x) > 0 and all(isinstance(v, (int,float)) for v in x) for x in data):
                    for i, arr in enumerate(data, 1):
                        curves.append(("curve{}".format(i), ensure_list_numbers(arr)))
                # case C: list of dicts
                elif all(isinstance(x, dict) for x in data):
                    for i, obj in enumerate(data, 1):
                        if "values" not in obj:
                            raise ValueError("Object must include 'values'")
                        name = str(obj.get("name", "curve{}".format(i)))
                        vals = ensure_list_numbers(obj["values"])
                        curves.append((name, vals))
                else:
                    raise ValueError("Unsupported array structure")
            else:
                raise ValueError("Root must be an array")

            # Plot the curves
            for name, arr in curves:
                y_plot = _transform_if_needed(arr)
                ln, = ax_e.plot(t, y_plot, label=name, linewidth=1.2)
                added_lines.append(ln)

            # Place legend bottom-right after updates
            ax_e.legend(loc="lower right")
            canvas_e.draw()
            self._log(_("Added {} custom curve(s)" ).format(len(curves)))
            # Clear input if desired
            # custom_json_var.set("")  # Uncomment to reset after each add

        btn_add_curve.config(command=on_add_curve)

        # Original plotting logic
        if custom_axis:
            brks = encoded_axis_breaks
            enc_t_plot = self._segment_equal_transform(encoded_target, brks)
            enc_m_plot = self._segment_equal_transform(encoded_measured, brks)
            ax_e.plot(t, enc_t_plot, label=_("target"), linewidth=2)
            ax_e.plot(t, enc_m_plot, label=_("measured"), linestyle="--")
            if encoded_sRGB is not None:
                enc_srgb_plot = self._segment_equal_transform(encoded_sRGB, brks)
                ax_e.plot(t, enc_srgb_plot, label=_("sRGB"), linestyle=":")
            tick_pos = self._segment_equal_transform(brks, brks)
            ax_e.set_yticks(tick_pos)
            ax_e.set_yticklabels([f"{v:g}" for v in brks])
            ax_e.set_ylim(0, 1)
            ax_e.set_ylabel(_("encoded (segmented)"))
            ax_e.set_title(_("{} segmented axis" ).format("PQ" if is_hdr else "Gamma2.2"))
            ax_e.grid(alpha=0.3, which="both")
            ax_e.legend(loc="lower right")
            ax_e.text(0.02, 0.97,
                      _("segments: {}" ).format(brks),
                      transform=ax_e.transAxes,
                      fontsize=8, va="top", ha="left",
                      bbox=dict(boxstyle="round", fc="white", ec="#888", alpha=0.7))
        else:
            ax_e.plot(t, encoded_target, label=_("target"), linewidth=2)
            ax_e.plot(t, encoded_measured, label=_("measured"), linestyle="--")
            if encoded_sRGB is not None:
                ax_e.plot(t, encoded_sRGB, label=_("sRGB"), linestyle=":")
            ax_e.set_ylim(0,1)
            ax_e.set_ylabel(_("encoded"))
            ax_e.set_title(_("{} (Peak {:.1f} nits)" ).format("PQ" if is_hdr else "Gamma2.2", Y_white))
            if not is_hdr:
                def toggle_zoom():
                    cur = getattr(ax_e, "_zoom_low", False)
                    if not cur:
                        ax_e.set_ylim(0,0.3)
                        btn_zoom.config(text=_("Full range"))
                        ax_e._zoom_low = True
                    else:
                        ax_e.set_ylim(0,1)
                        btn_zoom.config(text=_("Zoom low"))
                        ax_e._zoom_low = False
                    canvas_e.draw()
                zoom_bar = ttk.Frame(frm_e); zoom_bar.pack(fill="x", pady=(0,2))
                btn_zoom = ttk.Button(zoom_bar, text=_("Zoom low"), width=10, command=toggle_zoom)
                btn_zoom.pack(side="left", padx=6)
                ax_e.set_yticks([0,0.01,0.02,0.05,0.1,0.2,0.3,0.5,0.7,1.0])
            ax_e.legend(loc="lower right")

        ax_e.set_xlabel(_("input"))
        canvas_e = FigureCanvasTkAgg(fig_e, master=frm_e)
        canvas_e.get_tk_widget().pack(fill="both", expand=True)
        canvas_e.draw()

        self._log(_("Luma curve measurement complete: curves displayed"))

    # Helpers
    def _get_rgb(self):
        r = max(0, min(1023, int(self.r_var.get())))
        g = max(0, min(1023, int(self.g_var.get())))
        b = max(0, min(1023, int(self.b_var.get())))
        return [r, g, b]

    def _ensure_writer(self, recreate=False):
        if recreate and self.writer:
            self._terminate_writer()
        if self.writer is None:
            print(self.mode_var.get())
            self.writer = ColorWriter(mode=self.mode_var.get())
            time.sleep(0.05)

    def _ensure_reader(self, recreate=False):
        if recreate and self.reader:
            self._terminate_reader()
        if self.reader is None:
            # Note: color_rw.ColorReader expects the args object as a single param
            args_str = self.args_var.get().strip()
            self.reader = ColorReader(args=args_str)
            time.sleep(0.05)

    def _terminate_writer(self):
        try:
            if self.writer:
                # If there is a child process, add terminate() in ColorWriter
                self.writer.terminate()
                # Optional: getattr(self.writer,'proc',None) and self.writer.proc.kill()
        except Exception as e:
            self._log(_("Terminate writer error: {}" ).format(e))
        finally:
            self.writer = None

    def _terminate_reader(self):
        try:
            if self.reader:
                self.reader.terminate()
                # Similarly kill child process if needed
        except Exception as e:
            self._log(_("Terminate reader error: {}" ).format(e))
        finally:
            self.reader = None

    def _apply_xyz(self, xyz):
        if xyz.size < 3 or not np.isfinite(xyz[:3]).all():
            self._log(_("Read failed: insufficient data"))
            return

        X, Y, Z = xyz[:3]
        self.xyz_label.config(text="XYZ: {:.4f} , {:.4f} , {:.4f}" .format(X, Y, Z))
        x, y, capY = XYZ_to_xyY([X, Y, Z])
        self.xyy_var.set("xyY: {:.4f} , {:.4f} , {:.4f}" .format(x, y, capY))
        self._log(_("Read success XYZ: {:.4f},{:.4f},{:.4f} xy: {:.4f},{:.4f}" ).format(X, Y, Z, x, y))

    # Enable select/copy bindings for read-only entries
    def _enable_select_copy(self, entry: ttk.Entry):
        entry.bind("<Control-a>", lambda e: (entry.select_range(0, 'end'), 'break'))
        entry.bind("<Button-1>", lambda e: entry.focus_set())
        entry.bind("<FocusIn>", lambda e: entry.select_range(0, 'end'))

    def _copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._log(_("Copied xyY to clipboard"))
        except Exception as e:
            self._log(_("Copy failed: {}" ).format(e))
    

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_txt.insert("end", "[{}] {}\n".format(ts, msg))
        self.log_txt.see("end")

    def on_exit(self):
        # Prevent double execution
        if getattr(self, "_exiting", False):
            return
        self._exiting = True
        self._log(_("Exiting and cleaning up..."))
        try:
            self._terminate_reader()
            self._terminate_writer()
            # Close matplotlib windows if imported
            try:
                import matplotlib.pyplot as plt
                plt.close('all')
            except Exception:
                pass
            # Log alive threads for debugging (optional)
            alive = [t.name for t in threading.enumerate() if t is not threading.current_thread()]
            if alive:
                self._log(_("Remaining threads: {}" ).format(alive))
            # Quit Tk
            try:
                self.quit()
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                pass
        finally:
            # Force exit as a fallback
            sys.exit(0)

if __name__ == "__main__":
    app = ColorMeasureApp()
    app.mainloop()