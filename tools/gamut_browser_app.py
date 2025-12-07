from tkinter import ttk, filedialog,messagebox
from matplotlib.path import Path
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from colour import SpectralDistribution, SpectralShape, sd_to_XYZ, SDS_ILLUMINANTS, MSDS_CMFS
import matplotlib
import tkinter.font as tkfont
import tkinter as tk
import matplotlib.pyplot as plt
import numpy as np
import struct
import traceback
import os
import sys
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from i18n.i18n_loader import _

def create_single_wavelength_sd(wavelength, shape):
    data = {wavelength: 1.0}
    full_domain = np.arange(shape.start, shape.end + shape.interval, shape.interval)
    for wl in full_domain:
        if wl not in data:
            data[wl] = 0.0
    sd = SpectralDistribution(data, name=f"{wavelength}nm")
    sd = sd.align(shape)
    return sd

def wavelength_to_XYZ(wavelength):
    cmfs = MSDS_CMFS['CIE 1931 2 Degree Standard Observer']
    illuminant = SDS_ILLUMINANTS['D65']
    shape = cmfs.shape
    sd = create_single_wavelength_sd(wavelength, shape)
    return sd_to_XYZ(sd, cmfs, illuminant)

def xyz_to_xy(xyz):
    x, y, z = xyz
    total = x + y + z
    return [x / total, y / total] if total else [0, 0]

# XYZ to linear sRGB conversion matrix (D65 white, standard RGB primaries)
M = np.array([[ 3.2406, -1.5372, -0.4986],
              [-0.9689,  1.8758,  0.0415],
              [ 0.0557, -0.2040,  1.0570]])
def XYZ_to_sRGB(xyz):
    """Convert an XYZ color to linear sRGB."""
    return np.dot(M, xyz)

def linear_to_srgb(linear):
    """Apply standard sRGB companding to linear RGB array (shape (...,3))."""
    a = 0.055
    thr = 0.0031308
    out = np.empty_like(linear)
    low = linear <= thr
    out[low] = linear[low] * 12.92
    out[~low] = (1 + a) * np.power(np.clip(linear[~low], 0.0, None), 1.0 / 2.4) - a
    return np.clip(out, 0.0, 1.0)

def generate_chromaticity_diagram_image(res=400):
    """
    Generate a chromaticity horseshoe image with approximate display colors.
    - Masks to the spectral locus polygon.
    - Converts xy -> XYZ -> linear RGB, handles out-of-gamut by clipping and per-pixel normalization
      (to preserve saturation), applies a modest exposure and sRGB companding.
    - Returns an (res, res, 3) float image in 0..1.
    Outside the spectral locus the background is white.
    """
    cache_file = "horseshoe_cache.npy"
    if os.path.exists(cache_file):
        try:
            img = np.load(cache_file)
            if img.shape[0] == res and img.shape[1] == res:
                return img
        except Exception:
            pass

    # spectral locus xy (380..780 nm)
    wl = np.arange(380, 781, 1)
    locus_xy = np.array([xyz_to_xy(wavelength_to_XYZ(w)) for w in wl])

    # polygon for masking
    poly = Path(locus_xy)

    xs = np.linspace(0.0, 0.8, res)
    ys = np.linspace(0.0, 0.9, res)
    xv, yv = np.meshgrid(xs, ys)
    pts = np.column_stack((xv.ravel(), yv.ravel()))
    mask = poly.contains_points(pts).reshape((res, res))

    # image default background: white (outside horseshoe)
    img = np.ones((res, res, 3), dtype=float)

    # compute colors only for masked points
    idxs = np.where(mask.ravel())[0]
    if idxs.size:
        xy_pts = pts[idxs]
        x = xy_pts[:, 0]
        y = xy_pts[:, 1]
        z = 1.0 - x - y
        valid = (y > 1e-12) & (z >= -1e-12)
        if np.any(valid):
            X = x[valid] / y[valid]
            Y = np.ones_like(X)
            Z = z[valid] / y[valid]
            xyz = np.stack([X, Y, Z], axis=1)  # (n,3)

            # convert to linear sRGB using existing matrix M (XYZ->linear sRGB defined above)
            rgb_linear = np.dot(xyz, M.T)  # (n,3)

            # handle negatives and out-of-gamut:
            tmp = np.clip(rgb_linear, 0.0, None)
            maxv = tmp.max(axis=1, keepdims=True)
            maxv_safe = np.where(maxv <= 0, 1.0, maxv)
            rgb_norm = tmp / maxv_safe  # normalize to keep saturation where possible

            # modest exposure to make colors vivid but avoid clipping
            exposure = 0.95
            rgb_norm = np.clip(rgb_norm * exposure, 0.0, 1.0)

            # sRGB companding
            rgb = linear_to_srgb(rgb_norm)

            flat = img.reshape(-1, 3)
            flat[idxs[valid]] = rgb

    # optional slight blur for nicer blending (if scipy available)
    try:
        from scipy.ndimage import gaussian_filter
        img = gaussian_filter(img, sigma=(1.0, 1.0, 0.0))
    except Exception:
        pass

    # cache result
    try:
        np.save(cache_file, img)
    except Exception:
        pass

    return img

def read_icc_rgb_wtpt(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
        tag_count = struct.unpack('>I', data[128:132])[0]
        tags = {}
        for i in range(tag_count):
            sig = data[132 + i*12:136 + i*12].decode('ascii', errors='ignore')
            offset = struct.unpack('>I', data[136 + i*12:140 + i*12])[0]
            size = struct.unpack('>I', data[140 + i*12:144 + i*12])[0]
            tags[sig.strip()] = data[offset:offset+size]

        def parse_xyz(tag):
            return [struct.unpack('>i', tag[8:12])[0] / 65536,
                    struct.unpack('>i', tag[12:16])[0] / 65536,
                    struct.unpack('>i', tag[16:20])[0] / 65536]

        try:
            r = parse_xyz(tags['rXYZ'])
            g = parse_xyz(tags['gXYZ'])
            b = parse_xyz(tags['bXYZ'])
            w = parse_xyz(tags['wtpt'])
            return {
                "red": xyz_to_xy(r),
                "green": xyz_to_xy(g),
                "blue": xyz_to_xy(b),
                "white": xyz_to_xy(w)
            }
        except KeyError:
            return None

default_spaces = {
    "sRGB": {
        "color": "blue",
        "gamut": {
            "red": [0.64, 0.33], "green": [0.30, 0.60],
            "blue": [0.15, 0.06], "white": [0.3127, 0.3290]
        }
    },
    "Display P3": {
        "color": "green",
        "gamut": {
            "red": [0.68, 0.32], "green": [0.265, 0.69],
            "blue": [0.15, 0.06], "white": [0.3127, 0.3290]
        }
    },
    "BT.2020": {
        "color": "red",
        "gamut": {
            "red": [0.708, 0.292], "green": [0.170, 0.797],
            "blue": [0.131, 0.046], "white": [0.3127, 0.3290]
        }
    }
}

class ColorGamutApp:
    def __init__(self, root):
        self.root = root
        self.root.title(_("CIE 1931 Gamut Plot"))
        self.root.geometry("1000x700")
        self.color_spaces = dict(default_spaces)
        self.check_vars = {}
        
        self.control_frame = ttk.Frame(root)
        self.control_frame.grid(row=0, column=0, sticky="ns")
        self.load_button = ttk.Button(self.control_frame, text=_("Load ICC Profiles"), command=self.load_icc)
        self.load_button.grid(row=0, column=0, pady=10, sticky="w")
        self.add_button = ttk.Button(self.control_frame, text=_("Add Custom Gamut"), command=self.add_custom_space)
        self.add_button.grid(row=1, column=0, pady=10, sticky="w")
        
        self.canvas_frame = ttk.Frame(root)
        self.canvas_frame.grid(row=0, column=1, sticky="nsew")
        self.fig, self.ax = plt.subplots(figsize=(6, 6))
        self.fig.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.canvas_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        
        self.horseshoe_img = generate_chromaticity_diagram_image()
        
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        self.canvas_frame.bind("<Configure>", self.on_resize)
        self._drag_start = None
        self._dragging = False
        self._last_mouse_xy = None
        self.canvas.mpl_connect("button_press_event", self.on_mouse_press)
        self.canvas.mpl_connect("button_release_event", self.on_mouse_release)
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_drag)
        

        self.setup_checkboxes()
        
        # ---------- coordinate status placed in a bottom status bar ----------
        # Use a slightly taller fixed-height status frame so two lines (x / y) fit,
        # and keep the display persistent (show "None" when pointer is outside).
        STATUS_HEIGHT_PX = 36  # increased to fit two lines
        self.status_frame = ttk.Frame(root, height=STATUS_HEIGHT_PX)
        self.status_frame.grid(row=1, column=0, columnspan=2, sticky="we")
        # prevent the frame from resizing to its children
        try:
            self.status_frame.grid_propagate(False)
        except Exception:
            pass

        # coordinate text variable initialized to persistent "None" values (two lines)
        self.coord_var = tk.StringVar(value="x=None\ny=None")
        coord_lbl = ttk.Label(
            self.status_frame,
            textvariable=self.coord_var,
            foreground="blue",
            anchor="w",
            justify="left"
        )
        # place label with a small top offset so both lines are visible
        coord_lbl.place(x=8, y=6)

        # ensure row 1 has at least the fixed height (defensive)
        try:
            root.rowconfigure(1, weight=0, minsize=STATUS_HEIGHT_PX)
        except Exception:
            pass
        # ---------- end status bar ----------
        
        self.draw_plot()
        self.root.after(100, lambda: self.on_resize_initial())
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
    
    def setup_checkboxes(self):
        for idx, name in enumerate(self.color_spaces.keys()):
            self.add_checkbox(name, idx + 2)
    def add_checkbox(self, name, row):
        var = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(self.control_frame, text=name, variable=var, command=self.draw_plot)
        chk.grid(row=row, column=0, sticky='w')
        self.check_vars[name] = var
    
    def load_icc(self):
        paths = filedialog.askopenfilenames(filetypes=[("ICC profiles", "*.icc *.icm")])
        for path in paths:
            gamut = read_icc_rgb_wtpt(path)
            if gamut:
                name = _("ICC: {}" ).format(os.path.basename(path))
                self.color_spaces[name] = {"color": np.random.rand(3,), "gamut": gamut}
                self.add_checkbox(name, len(self.check_vars) + 2)
        self.draw_plot()
    
    def add_custom_space(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(_("Add Custom Gamut"))
        dialog.geometry("400x500")

        entries = {}
        ttk.Label(dialog, text=_("Gamut name:")).grid(row=0, column=0, padx=5, pady=6, sticky="e")
        entries["name"] = ttk.Entry(dialog, width=22)
        entries["name"].grid(row=0, column=1, padx=5, pady=6, sticky="w")

        ttk.Label(dialog, text=_("RGBW xy (each line x,y; lines R\\nG\\nB\\nW):")).grid(
            row=1, column=0, columnspan=2, padx=5, pady=(8,2), sticky="w"
        )
        txt = tk.Text(dialog, width=28, height=6)
        txt.grid(row=2, column=0, columnspan=2, padx=8, pady=4)
        hint = _("Example:\n0.6400,0.3300\n0.3000,0.6000\n0.1500,0.0600\n0.3127,0.3290")
        ttk.Label(dialog, text=hint, foreground="gray").grid(row=3, column=0, columnspan=2, padx=8, pady=(0,8), sticky="w")
        entries["rgbw_text"] = txt

        def on_confirm():
            try:
                name = entries["name"].get().strip()
                if not name:
                    messagebox.showerror(_("Error"), _("Please enter a gamut name"))
                    return
                text = entries["rgbw_text"].get("1.0", "end").strip()
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) != 4:
                    messagebox.showerror(_("Error"), _("Provide 4 lines of RGBW xy values (each line x,y)"))
                    return
                cols = []
                for ln in lines:
                    parts = [p.strip() for p in ln.split(",")]
                    if len(parts) != 2:
                        raise ValueError(_("Line format error: {}" ).format(ln))
                    x = float(parts[0]); y = float(parts[1])
                    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                        raise ValueError(_("Coordinates must be between 0 and 1: {}" ).format(ln))
                    cols.append([x, y])
                red, green, blue, white = cols

                new_name = name
                idx = 1
                while new_name in self.color_spaces:
                    new_name = "{}_{}".format(name, idx)
                    idx += 1

                self.color_spaces[new_name] = {
                    "color": np.random.rand(3,),
                    "gamut": {
                        "red": red,
                        "green": green,
                        "blue": blue,
                        "white": white,
                    }
                }
                self.add_checkbox(new_name, len(self.check_vars) + 2)
                self.draw_plot()
                dialog.destroy()
            except Exception as e:
                print(traceback.format_exc())
                messagebox.showerror(_("Error"), _("Input error: {}" ).format(e))

        def on_cancel():
            dialog.destroy()
        

        ttk.Button(dialog, text=_("OK"), command=on_confirm).grid(row=9, column=0, pady=10, padx=8)
        ttk.Button(dialog, text=_("Cancel"), command=on_cancel).grid(row=9, column=1, pady=10, padx=8)

    def draw_plot(self):
        self.ax.clear()
        self.ax.imshow(self.horseshoe_img, extent=(0, 0.8, 0, 0.9), origin='lower')

        for name, var in self.check_vars.items():
            if var.get():
                entry = self.color_spaces[name]
                cs = entry["gamut"]
                color = entry["color"]
                pts = np.array([cs['red'], cs['green'], cs['blue'], cs['red']])
                self.ax.plot(pts[:, 0], pts[:, 1], label=name, color=color)
                self.ax.scatter(*cs['white'], color='black', marker='x')
                self.ax.text(cs['white'][0] + 0.01, cs['white'][1] + 0.01, name, fontsize=8)

        self.ax.set_xlim(0, 0.8)
        self.ax.set_ylim(0, 0.9)
        self.ax.set_title(_("CIE 1931 xy Chromaticity (background)"))
        self.ax.set_xlabel("x")
        self.ax.set_ylabel("y")
        self.ax.grid(True)
        self.ax.legend(fontsize=8, loc='lower right')
        self.canvas.draw()
    
    def on_scroll(self, event):
        x = event.xdata
        y = event.ydata
        if x is None or y is None:
            return  

        ax = self.ax
        cur_xlim = ax.get_xlim()
        cur_ylim = ax.get_ylim()

        scale_factor = 1 / 1.2 if event.button == 'up' else 1.2

        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

        relx = (x - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0])
        rely = (y - cur_ylim[0]) / (cur_ylim[1] - cur_ylim[0])

        ax.set_xlim([x - new_width * relx, x + new_width * (1 - relx)])
        ax.set_ylim([y - new_height * rely, y + new_height * (1 - rely)])
        self.canvas.draw()

    def on_resize(self, event):
        width = event.width / self.fig.dpi
        height = event.height / self.fig.dpi
        self.fig.set_size_inches(width, height, forward=True)
        self.canvas.draw()
    
    def on_mouse_press(self, event):
        if event.button == 1 and event.xdata is not None and event.ydata is not None:
            self._dragging = True
            self._last_mouse_xy = (event.xdata, event.ydata)

    def on_mouse_release(self, event):
        if event.button == 1:
            self._dragging = False
            self._last_mouse_xy = None

    def on_mouse_drag(self, event):
        if not self._dragging or event.xdata is None or event.ydata is None or self._last_mouse_xy is None:
            return

        x_prev, y_prev = self._last_mouse_xy
        dx = event.xdata - x_prev
        dy = event.ydata - y_prev

        factor = 0.8  
        dx *= factor
        dy *= factor

        cur_xlim = self.ax.get_xlim()
        cur_ylim = self.ax.get_ylim()
        self.ax.set_xlim(cur_xlim[0] - dx, cur_xlim[1] - dx)
        self.ax.set_ylim(cur_ylim[0] - dy, cur_ylim[1] - dy)
        self.canvas.draw()

        self._last_mouse_xy = (event.xdata, event.ydata)
    
    def on_mouse_move(self, event):
        """Update coord label with data coordinates when the pointer is over the axes."""
        # show persistent "None" when not over the axes
        if event.xdata is None or event.ydata is None:
            self.coord_var.set(_("x=None y=None"))
            return
        # format to 4 decimal places, clamp to current axis limits for nicer display
        try:
            x, y = float(event.xdata), float(event.ydata)
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            if x < min(xlim) or x > max(xlim) or y < min(ylim) or y > max(ylim):
                self.coord_var.set("x=None y=None")
            else:
                # split x and y into two lines
                self.coord_var.set("x={:.4f} y={:.4f}".format(x, y))
        except Exception:
            self.coord_var.set("")
            self.coord_var.set("x=None y=None")
    
    def on_resize_initial(self):
        width = self.canvas.get_tk_widget().winfo_width() / self.fig.dpi
        height = self.canvas.get_tk_widget().winfo_height() / self.fig.dpi
        self.fig.set_size_inches(width, height, forward=True)
        self.canvas.draw()

if __name__ == "__main__":
    matplotlib.rcParams['font.family'] = 'Microsoft YaHei'
    root = tk.Tk()

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(family="Microsoft YaHei", size=10)
    root.option_add("*Font", default_font)
    root.protocol("WM_DELETE_WINDOW", root.quit)

    app = ColorGamutApp(root)
    root.mainloop()
