import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
# --- ensure project root in sys.path ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from color_rw import ColorWriter
import atexit

class VisualCheckApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Visual Check - RGBW Grayscale")
        self.resizable(False, False)

        # Writer instance (created per selected mode)
        self.writer = None
        self.current_mode = tk.StringVar(value="hdr_10")
        atexit.register(self._cleanup)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        # Mode selector
        ttk.Label(frm, text="Output mode:").grid(row=0, column=0, sticky="w")
        modes = ["hdr_10", "hdr_8", "sdr_10", "sdr_8"]
        mode_cb = ttk.Combobox(frm, textvariable=self.current_mode, state="readonly", values=modes, width=12)
        mode_cb.grid(row=0, column=1, sticky="w", padx=(8,0))
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())

        # Channel selector (only red/green/blue/white)
        ttk.Label(frm, text="Channel:").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.channel_var = tk.StringVar(value="white")
        cb = ttk.Combobox(frm, textvariable=self.channel_var, state="readonly",
                          values=["white", "red", "green", "blue"], width=10)
        cb.grid(row=1, column=1, sticky="w", padx=(8,0), pady=(8,0))

        # Single Show button (level and other buttons removed)
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=(12,0))
        ttk.Button(btn_frame, text="Show", command=self.show_patch).pack(side="left")

        ttk.Label(frm, text="Only RGB/W channels selectable. Mode controls numeric range.").grid(
            row=3, column=0, columnspan=3, pady=(12,0), sticky="w"
        )

        # create initial writer
        self._create_writer(self.current_mode.get())

    # removed: level handling and helper methods

    def _create_writer(self, mode):
        # recreate writer for new mode
        try:
            if self.writer:
                self.writer.terminate()
        except Exception:
            pass
        try:
            self.writer = ColorWriter(mode=mode)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start ColorWriter: {e}")
            self.writer = None

    def _on_mode_change(self):
        self._create_writer(self.current_mode.get())

    def show_patch(self):
        ch = self.channel_var.get()
        if not self.writer:
            messagebox.showerror("Error", "ColorWriter not initialized for selected mode")
            return
        try:
            # Call write_grayscale with channel only (full 100%)
            try:
                # prefer passing level if implementation supports it
                self.writer.write_grayscale(ch, 100)
            except TypeError:
                self.writer.write_grayscale(ch)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send command: {e}")

    def _cleanup(self):
        try:
            if hasattr(self, "writer") and self.writer:
                self.writer.terminate()
        except Exception:
            pass

    def _on_exit(self):
        self._cleanup()
        self.destroy()

if __name__ == "__main__":
    app = VisualCheckApp()
    app.mainloop()