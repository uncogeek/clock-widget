#!/usr/bin/env python3
"""
Two Analog Clocks — Iran & US (tkinter + Pillow for smooth rendering)

Right-click a clock -> "Settings..." to open a settings dialog for that
clock. You can change:
  - Clock size: tiny / small / medium (default) / large / xlarge. Every
    element (face, ticks, numerals, hands, flag, icon) is redrawn scaled
    to fit the new size — nothing gets clipped or stays the old size.
  - Numeral size: normally scales automatically with clock size, but you
    can turn on "Force custom number size" and pick an exact pixel size.
  - Colors & sessions: each day/night period (its start hour, its icon,
    and its 5 colors: face, outline, ticks, numerals, hands) is fully
    editable per clock.

Settings are saved to ~/.analog_clocks_settings.json and reloaded next
time you start the app.

How the smoothing/low-CPU rendering works:
- Each clock is rendered with Pillow: the static face (circle, ticks,
  numbers, flag, day/night icon) is drawn ONCE at 4x resolution and
  cached as a base image. Every second, a cheap copy of that cached base
  image has the 3 hands drawn on it (also at 4x), then the whole frame is
  downscaled to the real display size with a high-quality filter
  (LANCZOS) for anti-aliasing.
- The static face is only *redrawn* when the active day/night period
  changes (a handful of times per day) or when you change settings —
  never on every tick — so CPU/GPU usage stays low.
- If Pillow isn't installed, the app falls back to a plain-Canvas
  renderer (functional, less smooth, still theme/size aware).

Requirements:
    pip install pillow
    pip install pystray      (optional, for the system tray icon)
(tkinter and zoneinfo ship with standard Python 3.9+.)
"""

import io
import os
import sys
import webbrowser
import copy
import json
import math
import time
import base64
import threading
import tkinter as tk
from tkinter import ttk, colorchooser
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ---------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------
# Base/reference design size. All other pixel constants below (flag size,
# icon size, tick lengths, font size, hand widths, etc.) were designed
# for a 200x200 face; when a clock uses a different preset, everything is
# multiplied by (preset_size / BASE_SIZE) so the whole face scales
# together instead of some elements staying a fixed size.
BASE_SIZE = 200

SIZE_PRESETS = {
    "tiny":   120,
    "small":  160,
    "medium": 200,   # default / previous fixed size
    "large":  260,
    "xlarge": 320,
}
SIZE_ORDER = ["tiny", "small", "medium", "large", "xlarge"]

SUPERSAMPLE = 4                # internal render scale for anti-aliasing

# --- Flag size config (at BASE_SIZE=200; scales with clock size) ------
FLAG_SIZE_PX = 24

# Size (at BASE_SIZE=200) of the day/night indicator icon (sun / moon /
# "PM" / "Zzz") drawn above the center, between the 12 numeral and the
# center dot (mirrors the flag, which sits below center, between center
# and the 6 numeral).
ICON_SIZE_PX = 26
# ------------------------------------------------------------------------

TRANSPARENT_KEY = "#123456"

DEFAULT_SEC_COLOR = "#e74c3c"   # second hand + center dot accent color

# ---------------------------------------------------------------------
# Day/Night "periods" — the editable color-palette + time-session system
# ---------------------------------------------------------------------
# Each clock has its own ordered list of periods. A period is a plain
# dict: {"start_hour": 0-23, "icon": "sun"/"moon"/"pm"/"zzz"/"none",
# "face", "outline", "tick", "num", "hand": "#rrggbb", ...}. The clock's
# theme at any moment is whichever period has the greatest start_hour
# that is <= the current local hour (wrapping around midnight if none
# do). This is all fully editable from the Settings dialog, including
# adding/adjusting the start hours themselves.

def _default_periods_ny():
    return [
        {"start_hour": 0, "icon": "zzz", "face": "#2b2b2b", "outline": "#555555",
         "tick": "#888888", "num": "#dddddd", "hand": "#f2f2f2"},
        {"start_hour": 6, "icon": "sun", "face": "#ffffff", "outline": "#c8c8c8",
         "tick": "#282828", "num": "#141414", "hand": "#000000"},
        {"start_hour": 12, "icon": "pm", "face": "#aaaaaa", "outline": "#6e6e6e",
         "tick": "#1e1e1e", "num": "#0a0a0a", "hand": "#000000"},
        {"start_hour": 18, "icon": "moon", "face": "#192131", "outline": "#3c465f",
         "tick": "#c8cdd7", "num": "#ebeef2", "hand": "#ffffff"},
    ]


def _default_periods_ir():
    return [
        {"start_hour": 0, "icon": "zzz", "face": "#2b2b2b", "outline": "#555555",
         "tick": "#888888", "num": "#dddddd", "hand": "#f2f2f2"},
        {"start_hour": 6, "icon": "sun", "face": "#ffffff", "outline": "#c8c8c8",
         "tick": "#282828", "num": "#141414", "hand": "#000000"},
        {"start_hour": 18, "icon": "moon", "face": "#192131", "outline": "#3c465f",
         "tick": "#c8cdd7", "num": "#ebeef2", "hand": "#ffffff"},
    ]


def default_settings(flag_code):
    periods = _default_periods_ny() if flag_code == "US" else _default_periods_ir()
    return {
        "size": "medium",
        "force_number_size": False,
        "number_px": 9,
        "sec_color": DEFAULT_SEC_COLOR,
        "periods": periods,
    }


def resolve_period(hour, periods):
    """Pick the active period for `hour` (0-23) from a list of periods.

    Works for any number of periods in any order: it's whichever period
    has the greatest start_hour <= hour, wrapping around midnight to the
    last (by start_hour) period if none qualify.
    """
    periods_sorted = sorted(periods, key=lambda p: p["start_hour"])
    active = periods_sorted[-1]
    for p in periods_sorted:
        if p["start_hour"] <= hour:
            active = p
        else:
            break
    return active


def hex_to_rgba(hex_str, alpha=255):
    hex_str = (hex_str or "#000000").lstrip("#")
    if len(hex_str) < 6:
        hex_str = "000000"
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return (r, g, b, alpha)


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


# ---------------------------------------------------------------------
# Settings persistence (~/.analog_clocks_settings.json)
# ---------------------------------------------------------------------
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".analog_clocks_settings.json")


def _load_settings_file():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings_for(flag_code, settings):
    data = _load_settings_file()
    data[flag_code] = settings
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # never let a settings-save failure crash the app


def get_settings_for(flag_code):
    data = _load_settings_file()
    saved = data.get(flag_code)
    d = default_settings(flag_code)
    if isinstance(saved, dict):
        for key in ("size", "force_number_size", "number_px", "sec_color"):
            if key in saved:
                d[key] = saved[key]
        if isinstance(saved.get("periods"), list) and saved["periods"]:
            # Basic shape-check so a corrupt/old file can't crash rendering.
            ok = all(isinstance(p, dict) and "start_hour" in p for p in saved["periods"])
            if ok:
                d["periods"] = saved["periods"]
    if d["size"] not in SIZE_PRESETS:
        d["size"] = "medium"
    return d


# ---------------------------------------------------------------------
# Embedded flag icons (28x28 PNG, base64) — verified original bytes.
# ---------------------------------------------------------------------
FLAG_B64 = {
    "IR": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAACPklEQVRIie2WTWsTQRyHn5ndZde8tE2jFWtspS/YXgoVX6BeFGztJYge/AIK3v0Y+gkEPXoRfMFcWvBQ0N6kllp6sPFQTFNM05c0TTabzO540ErwIFlMbn1Oc/n9nv8MwzBwTJsRR4v003Skul++owNGtRDiX6GWy7XWQrIe6Ym/yTzMVP8Ipx9PjwZazSUTySHHdprG+E80uDWX3f2db6bF7PyjhawJ4Kv688GB80PKaOCpWptsgACny2YgOji8sbnxDLguZp7MRKWkFDsVNTzltU/WhGM6lLcP/bKqJKQw6meQumMygJqqgdRGzLJOSwA/8DsmO+LIIceS45GO234zlhyPmNcu3LAGT47Q25foqGy3sEcqec4S2Wx2xLbt9VQq1VJQlQ+ofFkGIDYxiRGLt5TL5XJ4njdqhplyJ/MaYVpoXwFQ+rCAVg2S6bstd8gwwsraKvXiNggBQlAvblNZWw1TEU5odndTz+eQto20ber57xhdXaGEoY40fmWKRrHA7vt5ABI3Z7F6kx0UXryMOijhrn8FKei+OoURD7lDb3ExXipsYiR6Wg5JxwGg8PJFy5nC3j5O39m4ufXule+ufEJZRqhJw1Jo+JyYuOTLyvJStaOmJirLS9VQt7QdSCfa2FJad/z1Vlr70g3y8tbKj4oPi26gOyZzA00AH9P5fNUEsLRxv6jUXEzKYUu263/xi0agOQyCrKXNB9D0e8n090eUw20tmARtt0cnPKH53KjLt/dyObc9ncf8xU80o9k517uvxQAAAABJRU5ErkJggg==",
    "US": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAADr0lEQVRIie3Ue0iddRzH8ffznEfPZWcePd4oL5TllslY1GR1snJ0YbHMCTGwVuufbETMCNe6THFthdQuULBVDv/YVnRhsdj+0LUwB46WDBdLZV7nPN49evSc8zzn8TyX/tCJBNJxaH/tAz/48eXh++L5wu8Ld7LMEW5dDr17IKOne6TGpyj3LSgvmpIs941oAJvN3h1Rwx+8cKx6ch6s3PH+K981d54kwS1YbVaE//bYq41E4xFWFFQRNWX9g08Wf/XZnwKAp7DMH1RxxVptjIz7AXCtdjAVkFnttBOSwxiGOV8DaP+pKioQQSAcVhkYGTy33vNYofjpFz8m9/SPuXxTMuVvFJKW6iY10UXVO9uQZZVtWzw87VmHrhscqXgdgEBQIXBzMLrTN4A2NsHMsO/5hoNfJwnl+2sKar+/0GCIViyiiOeRtUQ0jb/a+ijevJH6iy3ErXLw8LosfjnfjG4YmKbJ0Yg3uj+ci9/UyCkp3CQBaLqOKILFIiIrKoZpohsGMZIFRYngsBsEQgqiKKDpJgCPH6lcEjg0PkZMnHNCulUQRYHPP3qNwzVn0Q2DQ3t3ULavlrde3UxH7yAXL7dz7JNSyvbVEgyFSSt4dEmgOTCAPqMqQvn+moJvvq1vEGMcuOOdJCbEoWkaoVCY1JR4hkYmEUWRlCQXE/4gQ6OTtzXSCU0ld/vWTdLC4uRUiCfyctB0g7rGFnbvLOLAl6e5Jz2R/LwHOHqyHtOcHWn2y0VLAken/Tgy0oPzoCAIvLeziBOnGzFMk92lReypPkXJi/l03hjm+A+/UbnrJQ7WnCUkh9lQsWtJoNfrRVVV/zxomiZ1v18lOPfm6hpbMAyTS1euo85oqGqEC03XkBUVgLriN5cEjishMp/zpEhxTntkbUYy+qRMoKeP5LkPprv7yLIKMDqGDciyCgxdu869sRDN6lssQldX1/1Wq7UzPT39tptEk7mRZku+xub48fYOhuPiVxQcnfaTlLMmXpL7vc7eM+eZkqwrCk5oKg6nwyl0t7VlW2KtHelpaSsKemcf/hrJ39lnj0wHEZL6VxQcnl1tdmm65W9366kzuP+HkeZu3+oWLh0+7rZkpoxm3p1mWUnw5tCgrveNpAgAV5v+OHdXYtIWh8OxIpgsy4wH/E25eRvyJYDe2p8/vtza+ozpm7JKgrismGYaiEnuSNazT1XAgpXxa+kel7nKVq0E5IdMXZMWb7GEiJaIzWm/kpCaWrXxw7d9y9LzTv6dfwBIGbZTuS/R9QAAAABJRU5ErkJggg==",
}


def _find_font(size):
    if not PIL_AVAILABLE:
        return None
    size = max(6, int(size))
    candidates = []
    if IS_WINDOWS:
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        candidates += [os.path.join(fonts_dir, n)
                       for n in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf")]
    elif IS_MAC:
        candidates += [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _draw_theme_icon(d, cx, cy, icon_type, size, color, bg_color):
    """Draw a small day/night icon centered at (cx, cy).

    icon_type: "sun", "moon", "pm", "zzz", or "none". `size` is roughly
    the icon's diameter (already at the supersampled render scale).
    """
    if icon_type == "none" or size <= 0:
        return

    if icon_type == "sun":
        r0 = size * 0.28
        d.ellipse((cx - r0, cy - r0, cx + r0, cy + r0), fill=color)
        ray_w = max(1, int(size * 0.09))
        for i in range(8):
            ang = math.radians(i * 45)
            x1 = cx + r0 * 1.35 * math.cos(ang)
            y1 = cy + r0 * 1.35 * math.sin(ang)
            x2 = cx + r0 * 2.05 * math.cos(ang)
            y2 = cy + r0 * 2.05 * math.sin(ang)
            d.line((x1, y1, x2, y2), fill=color, width=ray_w)

    elif icon_type == "moon":
        r0 = size * 0.38
        d.ellipse((cx - r0, cy - r0, cx + r0, cy + r0), fill=color)
        off = r0 * 0.55
        d.ellipse((cx - r0 + off, cy - r0 - off * 0.1,
                   cx + r0 + off, cy + r0 - off * 0.1), fill=bg_color)

    elif icon_type == "pm":
        font = _find_font(size * 0.62)
        text = "PM"
        if font is not None:
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text,
                   fill=color, font=font)
        else:
            d.text((cx - size * 0.4, cy - size * 0.3), text, fill=color)

    elif icon_type == "zzz":
        font = _find_font(size * 0.55)
        text = "Zz"
        if font is not None:
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text,
                   fill=color, font=font)
        else:
            d.text((cx - size * 0.4, cy - size * 0.3), text, fill=color)


ICON_CHOICES = ["sun", "moon", "pm", "zzz", "none"]


# =======================================================================
# Pillow-based clock (smooth, anti-aliased, primary implementation)
# =======================================================================
class AnalogClockPIL(tk.Toplevel):
    """Anti-aliased analog clock, rendered with Pillow and shown via a Label."""

    def __init__(self, master, tz_name, flag_code, x, y):
        super().__init__(master)
        self.tzinfo = ZoneInfo(tz_name)
        self.flag_code = flag_code
        self.settings = get_settings_for(flag_code)

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        if IS_WINDOWS:
            self.configure(bg=TRANSPARENT_KEY)
            self.attributes("-transparentcolor", TRANSPARENT_KEY)
        elif IS_MAC:
            self.configure(bg="systemTransparent")
            self.attributes("-alpha", 1.0)
            self.attributes("-transparent", True)
        else:
            self.configure(bg="#1e1e1e")

        self._recompute_geometry()
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

        self.label = tk.Label(self, bd=0, highlightthickness=0, bg=self["bg"])
        self.label.pack()

        self._photo = None
        self._base_img = None
        self._current_period = None   # forces a base rebuild on first frame
        self._make_draggable()
        self._tick()

    # ---------- geometry / settings ----------

    def _recompute_geometry(self):
        self.width = self.height = SIZE_PRESETS[self.settings.get("size", "medium")]
        self.center = self.width // 2
        self.scale = self.width / BASE_SIZE
        margin = max(4, round(7 * self.scale))
        self.radius = self.center - margin

    def apply_settings(self, new_settings):
        """Called by the Settings dialog. Rebuilds geometry + the cached
        face image, keeping the clock's on-screen center point fixed."""
        old_cx = self.winfo_x() + self.width // 2
        old_cy = self.winfo_y() + self.height // 2

        self.settings = new_settings
        save_settings_for(self.flag_code, new_settings)

        self._recompute_geometry()
        new_x = old_cx - self.width // 2
        new_y = old_cy - self.height // 2
        self.geometry(f"{self.width}x{self.height}+{new_x}+{new_y}")

        self._current_period = None  # force a full rebuild
        self._render_frame()

    # ---------- static face (drawn once per period/size, cached) ----------

    def _build_static_base(self, period):
        hr = self.width * SUPERSAMPLE
        c = hr // 2
        r = int(self.radius * SUPERSAMPLE)
        s = self.scale

        face = hex_to_rgba(period["face"])
        outline = hex_to_rgba(period["outline"])
        tick_color = hex_to_rgba(period["tick"])
        num_color = hex_to_rgba(period["num"])
        hand_color = hex_to_rgba(period["hand"])

        img = Image.new("RGBA", (hr, hr), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        d.ellipse((c - r, c - r, c + r, c + r), fill=face, outline=outline,
                  width=max(1, int(2 * s * SUPERSAMPLE)))

        for i in range(60):
            angle = math.radians(i * 6 - 90)
            is_hour = i % 5 == 0
            outer = r - int(3 * s * SUPERSAMPLE)
            inner = r - int((10 if is_hour else 5) * s * SUPERSAMPLE)
            x1 = c + outer * math.cos(angle)
            y1 = c + outer * math.sin(angle)
            x2 = c + inner * math.cos(angle)
            y2 = c + inner * math.sin(angle)
            d.line((x1, y1, x2, y2), fill=tick_color,
                   width=max(1, int((2 if is_hour else 1) * s * SUPERSAMPLE)))

        if self.settings.get("force_number_size"):
            font_px = self.settings.get("number_px", 9)
        else:
            font_px = 9 * s
        font = _find_font(font_px * SUPERSAMPLE)

        numeral_radius = r - int(19 * s * SUPERSAMPLE)
        for h in range(1, 13):
            angle = math.radians(h * 30 - 90)
            x = c + numeral_radius * math.cos(angle)
            y = c + numeral_radius * math.sin(angle)
            text = str(h)
            if font is not None:
                bbox = d.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                d.text((x - tw / 2 - bbox[0], y - th / 2 - bbox[1]), text,
                       fill=num_color, font=font)
            else:
                d.text((x - 5, y - 6), text, fill=num_color)

        six_y = c + numeral_radius

        # Flag, between the "6" numeral and the center dot.
        try:
            data = base64.b64decode(FLAG_B64[self.flag_code])
            flag_img = Image.open(io.BytesIO(data)).convert("RGBA")
            disp_px = max(1, int(FLAG_SIZE_PX * s * SUPERSAMPLE))
            flag_img = flag_img.resize((disp_px, disp_px), Image.LANCZOS)
            flag_y = c + (six_y - c) * 0.5
            pos = (int(c - disp_px / 2), int(flag_y - disp_px / 2))
            img.alpha_composite(flag_img, dest=pos)
        except Exception:
            pass  # never let a flag issue break the clock

        # Day/night icon, between the "12" numeral and the center dot
        # (mirror of the flag's position below center).
        try:
            icon_y = c - (six_y - c) * 0.5
            icon_size = int(ICON_SIZE_PX * s * SUPERSAMPLE)
            _draw_theme_icon(d, c, icon_y, period.get("icon", "none"), icon_size,
                              color=hand_color, bg_color=face)
        except Exception:
            pass  # never let an icon issue break the clock

        return img

    # ---------- interaction ----------

    def _make_draggable(self):
        self._drag = {"x": 0, "y": 0}
        self.label.bind("<ButtonPress-1>", self._drag_start)
        self.label.bind("<B1-Motion>", self._drag_move)
        self.label.bind("<ButtonPress-3>", lambda e: self.master.show_context_menu(e, self))

    def _drag_start(self, event):
        self._drag["x"] = event.x
        self._drag["y"] = event.y

    def _drag_move(self, event):
        dx = event.x - self._drag["x"]
        dy = event.y - self._drag["y"]
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.geometry(f"+{x}+{y}")

    # ---------- clock tick ----------

    def _hand_end(self, cx, length, angle_deg):
        angle = math.radians(angle_deg - 90)
        return cx + length * math.cos(angle), cx + length * math.sin(angle)

    def _render_frame(self):
        now = datetime.now(self.tzinfo)
        period = resolve_period(now.hour, self.settings["periods"])
        if period is not self._current_period:
            self._current_period = period
            self._base_img = self._build_static_base(period)

        h, m, sec = now.hour % 12, now.minute, now.second

        frame = self._base_img.copy()
        d = ImageDraw.Draw(frame)

        hr = self.width * SUPERSAMPLE
        c = hr // 2
        r = int(self.radius * SUPERSAMPLE)
        s = self.scale

        sec_angle = sec * 6
        min_angle = m * 6 + sec * 0.1
        hour_angle = h * 30 + m * 0.5

        hx, hy = self._hand_end(c, r * 0.5, hour_angle)
        mx, my = self._hand_end(c, r * 0.72, min_angle)
        sx, sy = self._hand_end(c, r * 0.82, sec_angle)

        hand_color = hex_to_rgba(period["hand"])
        sec_color = hex_to_rgba(self.settings.get("sec_color", DEFAULT_SEC_COLOR))

        def rounded_line(x1, y1, x2, y2, width, color):
            d.line((x1, y1, x2, y2), fill=color, width=width)
            rad = width / 2
            for px, py in ((x1, y1), (x2, y2)):
                d.ellipse((px - rad, py - rad, px + rad, py + rad), fill=color)

        rounded_line(c, c, hx, hy, max(1, int(4 * s * SUPERSAMPLE)), hand_color)
        rounded_line(c, c, mx, my, max(1, int(2 * s * SUPERSAMPLE)), hand_color)
        rounded_line(c, c, sx, sy, max(1, int(1 * s * SUPERSAMPLE)), sec_color)

        dot_r = max(1, int(3 * s * SUPERSAMPLE))
        d.ellipse((c - dot_r, c - dot_r, c + dot_r, c + dot_r), fill=sec_color)

        small = frame.resize((self.width, self.height), Image.LANCZOS)

        if IS_WINDOWS:
            # Windows' -transparentcolor can only key out an *exact* color
            # match; it can't render partial transparency. The LANCZOS
            # downscale leaves a ring of partially-transparent edge pixels
            # around the circle, and those show up as a solid, oddly
            # blended fringe/ring instead of disappearing. Fix: flatten
            # onto the transparent-key color, then hard-threshold alpha so
            # every pixel is either "fully the key color" (-> invisible)
            # or fully opaque artwork. No more halo/extra ring.
            key_rgb = tuple(int(TRANSPARENT_KEY[i:i + 2], 16) for i in (1, 3, 5))
            bg = Image.new("RGBA", small.size, key_rgb + (255,))
            alpha = small.split()[3].point(lambda a: 255 if a >= 128 else 0)
            small = small.copy()
            small.putalpha(alpha)
            bg.paste(small, (0, 0), small)
            small = bg

        self._photo = ImageTk.PhotoImage(small)
        self.label.configure(image=self._photo)

    def _tick(self):
        self._render_frame()
        delay_ms = int((1.0 - (time.time() % 1.0)) * 1000)
        self.after(max(delay_ms, 50), self._tick)


# =======================================================================
# Canvas fallback (no Pillow) — functional, size/theme aware, less smooth
# =======================================================================
class AnalogClockCanvas(tk.Toplevel):
    """Fallback (no Pillow): plain Canvas rendering, not anti-aliased."""

    _ICON_TEXT = {"sun": "\u2600", "moon": "\u263D", "pm": "PM", "zzz": "Zz", "none": ""}

    def __init__(self, master, tz_name, flag_code, x, y):
        super().__init__(master)
        self.tzinfo = ZoneInfo(tz_name)
        self.flag_code = flag_code
        self.settings = get_settings_for(flag_code)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        if IS_WINDOWS:
            self.configure(bg=TRANSPARENT_KEY)
            self.attributes("-transparentcolor", TRANSPARENT_KEY)
        else:
            self.configure(bg="#1e1e1e")

        self._recompute_geometry()
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

        self.canvas = tk.Canvas(self, width=self.width, height=self.height,
                                 bg=self["bg"], highlightthickness=0)
        self.canvas.pack()

        self._flag_photo = None
        self._current_period = None
        self._full_redraw()
        self._make_draggable()
        self._tick()

    def _recompute_geometry(self):
        self.width = self.height = SIZE_PRESETS[self.settings.get("size", "medium")]
        self.center = self.width // 2
        self.scale = self.width / BASE_SIZE
        margin = max(4, round(7 * self.scale))
        self.radius = self.center - margin

    def apply_settings(self, new_settings):
        old_cx = self.winfo_x() + self.width // 2
        old_cy = self.winfo_y() + self.height // 2

        self.settings = new_settings
        save_settings_for(self.flag_code, new_settings)

        self._recompute_geometry()
        new_x = old_cx - self.width // 2
        new_y = old_cy - self.height // 2
        self.geometry(f"{self.width}x{self.height}+{new_x}+{new_y}")
        self.canvas.configure(width=self.width, height=self.height)

        self._current_period = None
        self._full_redraw()

    def _full_redraw(self):
        """Clears and redraws everything — used on start and whenever
        size/colors/periods change (infrequent, so cost is fine)."""
        self.canvas.delete("all")
        c, r, s = self.center, self.radius, self.scale

        now = datetime.now(self.tzinfo)
        period = resolve_period(now.hour, self.settings["periods"])
        self._current_period = period

        self._face_oval = self.canvas.create_oval(
            c - r, c - r, c + r, c + r,
            fill=period["face"], outline=period["outline"], width=2)

        self._tick_ids = []
        for i in range(60):
            angle = math.radians(i * 6 - 90)
            is_hour = i % 5 == 0
            outer, inner = r - 3 * s, r - (10 if is_hour else 5) * s
            x1, y1 = c + outer * math.cos(angle), c + outer * math.sin(angle)
            x2, y2 = c + inner * math.cos(angle), c + inner * math.sin(angle)
            tid = self.canvas.create_line(x1, y1, x2, y2, fill=period["tick"],
                                           width=max(1, round((2 if is_hour else 1) * s)))
            self._tick_ids.append(tid)

        if self.settings.get("force_number_size"):
            font_px = self.settings.get("number_px", 9)
        else:
            font_px = 9 * s
        font_px = max(6, round(font_px))

        self._num_ids = []
        numeral_radius = r - 19 * s
        for h in range(1, 13):
            angle = math.radians(h * 30 - 90)
            x, y = c + numeral_radius * math.cos(angle), c + numeral_radius * math.sin(angle)
            nid = self.canvas.create_text(x, y, text=str(h), fill=period["num"],
                                           font=("Helvetica", font_px, "bold"))
            self._num_ids.append(nid)

        six_y = c + numeral_radius
        try:
            data = base64.b64decode(FLAG_B64[self.flag_code])
            photo = tk.PhotoImage(data=data)
            target = max(4, round(FLAG_SIZE_PX * s))
            if target > 28:
                photo = photo.zoom(max(1, round(target / 28)))
            else:
                photo = photo.subsample(max(1, round(28 / target)))
            self._flag_photo = photo
            flag_y = c + (six_y - c) * 0.5
            self.canvas.create_image(c, flag_y, image=photo)
        except Exception:
            pass

        icon_y = c - (six_y - c) * 0.5
        icon_font_px = max(6, round(font_px * 1.1))
        self._icon_id = self.canvas.create_text(
            c, icon_y, text=self._ICON_TEXT.get(period.get("icon", "none"), ""),
            fill=period["hand"], font=("Helvetica", icon_font_px, "bold"))

        self.hour_hand = self.canvas.create_line(c, c, c, c, fill=period["hand"],
                                                   width=max(1, round(4 * s)), capstyle=tk.ROUND)
        self.min_hand = self.canvas.create_line(c, c, c, c, fill=period["hand"],
                                                  width=max(1, round(2 * s)), capstyle=tk.ROUND)
        sec_color = self.settings.get("sec_color", DEFAULT_SEC_COLOR)
        self.sec_hand = self.canvas.create_line(c, c, c, c, fill=sec_color,
                                                  width=max(1, round(1 * s)), capstyle=tk.ROUND)
        dot_r = max(2, round(3 * s))
        self.canvas.create_oval(c - dot_r, c - dot_r, c + dot_r, c + dot_r,
                                 fill=sec_color, outline="")

    def _make_draggable(self):
        self._drag = {"x": 0, "y": 0}
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.master.show_context_menu(e, self))

    def _drag_start(self, event):
        self._drag["x"], self._drag["y"] = event.x, event.y

    def _drag_move(self, event):
        dx, dy = event.x - self._drag["x"], event.y - self._drag["y"]
        self.geometry(f"+{self.winfo_x() + dx}+{self.winfo_y() + dy}")

    def _hand_end(self, length, angle_deg):
        angle = math.radians(angle_deg - 90)
        return self.center + length * math.cos(angle), self.center + length * math.sin(angle)

    def _tick(self):
        now = datetime.now(self.tzinfo)
        period = resolve_period(now.hour, self.settings["periods"])
        if period is not self._current_period:
            self._full_redraw()  # cheap enough; happens a few times/day

        h, m, sec = now.hour % 12, now.minute, now.second
        sec_angle, min_angle, hour_angle = sec * 6, m * 6 + sec * 0.1, h * 30 + m * 0.5
        hx, hy = self._hand_end(self.radius * 0.5, hour_angle)
        mx, my = self._hand_end(self.radius * 0.72, min_angle)
        sx, sy = self._hand_end(self.radius * 0.82, sec_angle)
        self.canvas.coords(self.hour_hand, self.center, self.center, hx, hy)
        self.canvas.coords(self.min_hand, self.center, self.center, mx, my)
        self.canvas.coords(self.sec_hand, self.center, self.center, sx, sy)
        delay_ms = int((1.0 - (time.time() % 1.0)) * 1000)
        self.after(max(delay_ms, 50), self._tick)


ClockClass = AnalogClockPIL if PIL_AVAILABLE else AnalogClockCanvas


# =======================================================================
# Settings dialog
# =======================================================================
class _ColorSwatchButton(tk.Button):
    """A small button that shows a color and opens a color-picker on click."""

    def __init__(self, master, initial_hex, on_change, **kw):
        self._hex = initial_hex
        self._on_change = on_change
        super().__init__(master, text="", width=4, relief="groove",
                          command=self._pick, bg=initial_hex,
                          activebackground=initial_hex, **kw)

    def _pick(self):
        rgb, hex_code = colorchooser.askcolor(color=self._hex, parent=self)
        if hex_code:
            self.set(hex_code)

    def set(self, hex_code):
        self._hex = hex_code
        try:
            self.configure(bg=hex_code, activebackground=hex_code)
        except Exception:
            pass
        if self._on_change:
            self._on_change(hex_code)

    def get(self):
        return self._hex


class SettingsDialog(tk.Toplevel):
    """Per-clock settings: size, numeral size, and color/session editor."""

    def __init__(self, master, clock):
        super().__init__(master)
        self.clock = clock
        self.title(f"Clock settings — {clock.flag_code}")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        # NOTE: `master` (the App root) is permanently withdrawn, so making
        # this dialog transient to it can leave the dialog drawn on screen
        # but unable to reliably receive mouse/keyboard input on some
        # platforms (clicks silently do nothing). Use the actual visible
        # clock window as the transient parent instead.
        self.transient(clock)

        # Work on a deep copy so Cancel doesn't affect the live clock.
        self.local = copy.deepcopy(clock.settings)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_size_tab(nb)
        self._build_numbers_tab(nb)
        self._build_colors_tab(nb)
        self._build_about_tab(nb)

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btns, text="Reset to Defaults", command=self._reset_defaults).pack(side="left")
        tk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        tk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="Apply", command=self._apply).pack(side="right")

        self.update_idletasks()
        self.lift()
        self.focus_force()
        self.grab_set()

    # ---------- Size tab ----------

    def _build_size_tab(self, nb):
        frame = tk.Frame(nb, padx=10, pady=10)
        nb.add(frame, text="Size")

        tk.Label(frame, text="Clock size:").grid(row=0, column=0, sticky="w", pady=4)
        self.size_var = tk.StringVar(value=self.local.get("size", "medium"))
        combo = ttk.Combobox(frame, textvariable=self.size_var, values=SIZE_ORDER,
                              state="readonly", width=12)
        combo.grid(row=0, column=1, sticky="w", padx=6)

        tk.Label(frame, text="(tiny < small < medium (default) < large < xlarge)\n"
                             "All elements — face, ticks, numerals, hands, flag,\n"
                             "icon — automatically rescale to fit the new size.",
                 justify="left", fg="#555555").grid(row=1, column=0, columnspan=2,
                                                     sticky="w", pady=(6, 0))

    # ---------- Numbers tab ----------

    def _build_numbers_tab(self, nb):
        frame = tk.Frame(nb, padx=10, pady=10)
        nb.add(frame, text="Numbers")

        self.force_var = tk.BooleanVar(value=self.local.get("force_number_size", False))
        cb = tk.Checkbutton(frame, text="Force custom number size", variable=self.force_var,
                             command=self._sync_number_state)
        cb.grid(row=0, column=0, columnspan=2, sticky="w")

        tk.Label(frame, text="Number size (px):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.number_px_var = tk.IntVar(value=self.local.get("number_px", 9))
        self.number_spin = tk.Spinbox(frame, from_=6, to=48, width=5,
                                       textvariable=self.number_px_var)
        self.number_spin.grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))

        tk.Label(frame, text="When off, number size scales automatically with clock size.",
                 fg="#555555").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self._sync_number_state()

    def _sync_number_state(self):
        state = "normal" if self.force_var.get() else "disabled"
        self.number_spin.configure(state=state)

    # ---------- Colors & sessions tab ----------

    def _build_colors_tab(self, nb):
        frame = tk.Frame(nb, padx=10, pady=10)
        nb.add(frame, text="Colors & Sessions")

        tk.Label(frame, text="Second hand color:").grid(row=0, column=0, sticky="w")
        self.sec_color_btn = _ColorSwatchButton(
            frame, self.local.get("sec_color", DEFAULT_SEC_COLOR), on_change=None)
        self.sec_color_btn.grid(row=0, column=1, sticky="w", padx=6, pady=(0, 8))

        header = tk.Frame(frame)
        header.grid(row=1, column=0, columnspan=8, sticky="w", pady=(4, 2))
        for i, label in enumerate(["Start hr", "Icon", "Face", "Outline",
                                    "Ticks", "Numbers", "Hands"]):
            tk.Label(header, text=label, font=("", 9, "bold")).grid(row=0, column=i, padx=4)

        self.period_rows = []
        periods_sorted = sorted(self.local["periods"], key=lambda p: p["start_hour"])
        for row_i, period in enumerate(periods_sorted):
            row = tk.Frame(frame)
            row.grid(row=2 + row_i, column=0, columnspan=8, sticky="w", pady=2)

            hour_var = tk.IntVar(value=period["start_hour"])
            tk.Spinbox(row, from_=0, to=23, width=3, textvariable=hour_var).grid(
                row=0, column=0, padx=4)

            icon_var = tk.StringVar(value=period.get("icon", "none"))
            ttk.Combobox(row, textvariable=icon_var, values=ICON_CHOICES,
                         state="readonly", width=6).grid(row=0, column=1, padx=4)

            face_btn = _ColorSwatchButton(row, period["face"], on_change=None)
            face_btn.grid(row=0, column=2, padx=4)
            outline_btn = _ColorSwatchButton(row, period["outline"], on_change=None)
            outline_btn.grid(row=0, column=3, padx=4)
            tick_btn = _ColorSwatchButton(row, period["tick"], on_change=None)
            tick_btn.grid(row=0, column=4, padx=4)
            num_btn = _ColorSwatchButton(row, period["num"], on_change=None)
            num_btn.grid(row=0, column=5, padx=4)
            hand_btn = _ColorSwatchButton(row, period["hand"], on_change=None)
            hand_btn.grid(row=0, column=6, padx=4)

            self.period_rows.append({
                "hour_var": hour_var, "icon_var": icon_var,
                "face_btn": face_btn, "outline_btn": outline_btn,
                "tick_btn": tick_btn, "num_btn": num_btn, "hand_btn": hand_btn,
            })

        tk.Label(frame, text="Each session's start hour (0-23, local time for this clock)\n"
                             "decides when its colors and icon become active.",
                 fg="#555555", justify="left").grid(
            row=2 + len(periods_sorted), column=0, columnspan=8, sticky="w", pady=(8, 0))

    # ---------- About tab ----------

    def _build_about_tab(self, nb):
        frame = tk.Frame(nb, padx=20, pady=20)
        nb.add(frame, text="About")
        tk.Label(frame, text="developed by: Senuvard_tools").pack(
            anchor="w", pady=(0, 10))
        channel = tk.Label(frame, text="Telegram channel: @Senuvard_tools",
                           fg="#0066cc", cursor="hand2",
                           font=("Segoe UI", 10, "underline"))
        channel.pack(anchor="w")
        channel.bind("<Button-1>", lambda event: webbrowser.open_new_tab(
            "https://t.me/Senuvard_tools"))

    # ---------- gather / apply ----------

    def _gather(self):
        result = copy.deepcopy(self.local)
        result["size"] = self.size_var.get()
        result["force_number_size"] = bool(self.force_var.get())
        try:
            result["number_px"] = max(6, min(48, int(self.number_px_var.get())))
        except (tk.TclError, ValueError):
            result["number_px"] = self.local.get("number_px", 9)
        result["sec_color"] = self.sec_color_btn.get()

        periods = []
        for row in self.period_rows:
            try:
                start_hour = max(0, min(23, int(row["hour_var"].get())))
            except (tk.TclError, ValueError):
                start_hour = 0
            periods.append({
                "start_hour": start_hour,
                "icon": row["icon_var"].get(),
                "face": row["face_btn"].get(),
                "outline": row["outline_btn"].get(),
                "tick": row["tick_btn"].get(),
                "num": row["num_btn"].get(),
                "hand": row["hand_btn"].get(),
            })
        periods.sort(key=lambda p: p["start_hour"])
        result["periods"] = periods
        return result

    def _apply(self):
        new_settings = self._gather()
        self.local = copy.deepcopy(new_settings)
        self.clock.apply_settings(new_settings)

    def _ok(self):
        self._apply()
        self.destroy()

    def _reset_defaults(self):
        self.local = default_settings(self.clock.flag_code)
        self.destroy()
        SettingsDialog(self.master, self.clock)


# =======================================================================
# App
# =======================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Settings...", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="Minimize both to tray", command=self.minimize_to_tray)
        self.menu.add_separator()
        self.menu.add_command(label="Close this clock", command=self._close_active)
        self.menu.add_command(label="Close both", command=self.close_app)
        self._active_clock = None

        gap = 20
        first_width = SIZE_PRESETS[get_settings_for("IR").get("size", "medium")]
        self.clocks = [
            ClockClass(self, "Asia/Tehran", "IR", x=100, y=100),
            ClockClass(self, "America/New_York", "US", x=100 + first_width + gap, y=100),
        ]
        self.tray_icon = None

    def show_context_menu(self, event, clock):
        self._active_clock = clock
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_settings(self):
        if self._active_clock is not None:
            SettingsDialog(self, self._active_clock)

    def _close_active(self):
        if self._active_clock is not None:
            self._active_clock.destroy()
            self.clocks = [c for c in self.clocks if c is not self._active_clock]
            self._active_clock = None
        if not self.clocks:
            self.close_app()

    def minimize_to_tray(self):
        for c in self.clocks:
            c.withdraw()
        if self.tray_icon is None:
            threading.Thread(target=self._run_tray, daemon=True).start()
        else:
            self.tray_icon.visible = True

    def _run_tray(self):
        try:
            import pystray
            from PIL import Image as PILImage, ImageDraw as PILImageDraw
        except ImportError:
            self.after(0, self._restore_all)
            return

        img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = PILImageDraw.Draw(img)
        d.ellipse((2, 2, 62, 62), fill=(43, 43, 43, 255), outline=(200, 200, 200, 255), width=3)
        d.line((32, 32, 32, 12), fill=(242, 242, 242, 255), width=3)
        d.line((32, 32, 46, 32), fill=(231, 76, 60, 255), width=2)

        def on_restore(icon, item=None):
            icon.stop()
            self.tray_icon = None
            self.after(0, self._restore_all)

        def on_quit(icon, item=None):
            icon.stop()
            self.after(0, self.close_app)

        menu = pystray.Menu(
            pystray.MenuItem("Show clocks", on_restore, default=True),
            pystray.MenuItem("Quit", on_quit),
        )
        self.tray_icon = pystray.Icon("analog_clocks", img, "Analog Clocks", menu)
        self.tray_icon.run()

    def _restore_all(self):
        for c in self.clocks:
            c.deiconify()

    def close_app(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
