"""
Multi-Timezone Digital Clock Widget for Windows 11
Borderless, draggable, always-on-top, auto-resizing width.
Right-click for Settings / Close menu.

Requirements to build the .exe:
    pip install pyinstaller

Build command (run in the folder containing this file):
    pyinstaller --onefile --noconsole --name ClockWidget clock_widget.py

The .exe will appear in the "dist" folder.
Settings are saved to: %APPDATA%\\ClockWidget\\config.json
"""

import tkinter as tk
from tkinter import ttk, colorchooser
import base64
import json
import os
import sys
import webbrowser
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ----------------------------------------------------------------------
# Embedded flag icons (28x28 PNG, base64-encoded) - no external files needed
# ----------------------------------------------------------------------
FLAG_B64 = {
    "IR": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAACPklEQVRIie2WTWsTQRyHn5ndZde8tE2jFWtspS/YXgoVX6BeFGztJYge/AIK3v0Y+gkEPXoRfMFcWvBQ0N6kllp6sPFQTFNM05c0TTabzO540ErwIFlMbn1Oc/n9nv8MwzBwTJsRR4v003Skul++owNGtRDiX6GWy7XWQrIe6Ym/yTzMVP8Ipx9PjwZazSUTySHHdprG+E80uDWX3f2db6bF7PyjhawJ4Kv688GB80PKaOCpWptsgACny2YgOji8sbnxDLguZp7MRKWkFDsVNTzltU/WhGM6lLcP/bKqJKQw6meQumMygJqqgdRGzLJOSwA/8DsmO+LIIceS45GO234zlhyPmNcu3LAGT47Q25foqGy3sEcqec4S2Wx2xLbt9VQq1VJQlQ+ofFkGIDYxiRGLt5TL5XJ4njdqhplyJ/MaYVpoXwFQ+rCAVg2S6bstd8gwwsraKvXiNggBQlAvblNZWw1TEU5odndTz+eQto20ber57xhdXaGEoY40fmWKRrHA7vt5ABI3Z7F6kx0UXryMOijhrn8FKei+OoURD7lDb3ExXipsYiR6Wg5JxwGg8PJFy5nC3j5O39m4ufXule+ufEJZRqhJw1Jo+JyYuOTLyvJStaOmJirLS9VQt7QdSCfa2FJad/z1Vlr70g3y8tbKj4oPi26gOyZzA00AH9P5fNUEsLRxv6jUXEzKYUu263/xi0agOQyCrKXNB9D0e8n090eUw20tmARtt0cnPKH53KjLt/dyObc9ncf8xU80o9k517uvxQAAAABJRU5ErkJggg==",
    "US": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAADr0lEQVRIie3Ue0iddRzH8ffznEfPZWcePd4oL5TllslY1GR1snJ0YbHMCTGwVuufbETMCNe6THFthdQuULBVDv/YVnRhsdj+0LUwB46WDBdLZV7nPN49evSc8zzn8TyX/tCJBNJxaH/tAz/48eXh++L5wu8Ld7LMEW5dDr17IKOne6TGpyj3LSgvmpIs941oAJvN3h1Rwx+8cKx6ch6s3PH+K981d54kwS1YbVaE//bYq41E4xFWFFQRNWX9g08Wf/XZnwKAp7DMH1RxxVptjIz7AXCtdjAVkFnttBOSwxiGOV8DaP+pKioQQSAcVhkYGTy33vNYofjpFz8m9/SPuXxTMuVvFJKW6iY10UXVO9uQZZVtWzw87VmHrhscqXgdgEBQIXBzMLrTN4A2NsHMsO/5hoNfJwnl+2sKar+/0GCIViyiiOeRtUQ0jb/a+ijevJH6iy3ErXLw8LosfjnfjG4YmKbJ0Yg3uj+ci9/UyCkp3CQBaLqOKILFIiIrKoZpohsGMZIFRYngsBsEQgqiKKDpJgCPH6lcEjg0PkZMnHNCulUQRYHPP3qNwzVn0Q2DQ3t3ULavlrde3UxH7yAXL7dz7JNSyvbVEgyFSSt4dEmgOTCAPqMqQvn+moJvvq1vEGMcuOOdJCbEoWkaoVCY1JR4hkYmEUWRlCQXE/4gQ6OTtzXSCU0ld/vWTdLC4uRUiCfyctB0g7rGFnbvLOLAl6e5Jz2R/LwHOHqyHtOcHWn2y0VLAken/Tgy0oPzoCAIvLeziBOnGzFMk92lReypPkXJi/l03hjm+A+/UbnrJQ7WnCUkh9lQsWtJoNfrRVVV/zxomiZ1v18lOPfm6hpbMAyTS1euo85oqGqEC03XkBUVgLriN5cEjishMp/zpEhxTntkbUYy+qRMoKeP5LkPprv7yLIKMDqGDciyCgxdu869sRDN6lssQldX1/1Wq7UzPT39tptEk7mRZku+xub48fYOhuPiVxQcnfaTlLMmXpL7vc7eM+eZkqwrCk5oKg6nwyl0t7VlW2KtHelpaSsKemcf/hrJ39lnj0wHEZL6VxQcnl1tdmm65W9366kzuP+HkeZu3+oWLh0+7rZkpoxm3p1mWUnw5tCgrveNpAgAV5v+OHdXYtIWh8OxIpgsy4wH/E25eRvyJYDe2p8/vtza+ozpm7JKgrismGYaiEnuSNazT1XAgpXxa+kel7nKVq0E5IdMXZMWb7GEiJaIzWm/kpCaWrXxw7d9y9LzTv6dfwBIGbZTuS/R9QAAAABJRU5ErkJggg==",
    "UK": "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",
    "TR": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAACuUlEQVRIie3WT0gUURwH8O97szM76+iaf1azcKutRaSydO0iIVlIlwzyYEjgobp06dChDl26dAg6REHgIShCwyAqpMhDCBFEoYmEoBm1/lus3dVcd2f2z7z3Ouia0brmtnuqLwwMb+b3PvDeb5gH/E+WQ5I3vZ4teVJYPsEIcZNV438bifPPi3LBg7aRkfgK2FvtcoOzF8WlDpdVVQGSJU8IRKMGAsG5wXhUHGvzemctAMCZece5fYdLiccg9HB2sOXYrCo0p9Mz4fXeBtBK+mrKNSHsC1tVVeJRI6tYMtRmw4wRM0N8vohGWX6FxHnOMADghgGJM4sV9s0UAARjOcOSSRqWdC8pzm1wdJyBVucBURREx0YR6LqHyPuBjOE1QXvjITiv3wRVrAj2dOF733MkAn7Yqqqh1dYjMpQZmhKUHWVwXrsBqtowdfki5nsfrzyLT06AUGnpUhRsdO9TgiUnT4FqGvThoV+wZARf2o/CpiNI+L/BDPhhzs+BLSysC9JUg7Y9NQCA8Ns3axaq7irYG5vg6ryLiguXwEKhdbE1wWSIJW1PZZSUM+ofhlHQcBB5+2rXLIyOjyH0qh/BRz0wA35IdnvmSzr3sBtc16F5DqDoeGuKKgpQilD/S0QG3iHm/fJHGABI7WXFxbIQ5/OlnzbXIzDGRlF4uBmbmo/CUlIKETVAFAXafg8sJaVIzExDmOYfIQAQ4RwmpbfI0907d9kYGy+Xf19dpdIJR8dpaHX1IBYZxsdRBLvvZ/QNfk2YMCTJnbYr4lOTmLl6ZcOTp0vaLs1FKFUNnymQyDVkcsGoavhoy6BPjwn2zOA8Z5jBORjB65ZBn24BgERcOjdLWGUhFR4lW8eL5cSFQJixT1yWzwKrDkudHo9cuehvByF7GYiSDYxCxMD5UJEhnjRMT+fuD/9v5weunRI0FwAc2wAAAABJRU5ErkJggg==",
    "JP": "iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAAABmJLR0QA/wD/AP+gvaeTAAACEklEQVRIie2WwWvTUBzHv0lemzVdpSlja8NiYdBT7TyIPVdw4GAe3E129eLZXWTniYce/CeGtyKorODAIh4rgjsUyqp2lCwTezDNS1LzfPNkaYWtqU097XMKeb/f9/PyCD8ecEnICH8eDMNQXNe9xznPDb+fFkLIZ8dxnufz+Z8DYavVynHOq8lkckWW5bBcAIB+v49ut/vBsqyNYrFoAgCazeY7SunZrKCUnjUajQoACKZpxj3P+5HNZqVQP+0v2u02o5Sqom3bGUmSZioDAEmSiCzLaTJpI6MUvaMvAIBEbgVEUSbqDyz0vn3H4ZMyjOoBOGMAAJEQaOtrKDx+hLnFhUA5YpAi98REbXMLnVfVgQwAOGPovNxHbXMLrnkanvDTbvnCQNc8xeFuORyhb/VgHtTGBp28eQu/Z08vtL8ejxzjeXDGQNvH0wshTDDlAtSOFc5ndYhk/M8sEoL4VX16YeRKAunbpbFBmbVbiCTmpxcCwOrONmLppXPXY+klFHa2g0QFE8YyaZQqe1jeuDNyvCIhWL67jlJl78INDRN40swtLuDms6f/b7QNGuJxqNevTdo2QFQUxfB93//nhIAwxn4pimKImqY5nue9ppTOTEYpBWPsvaZpDgEA27YfdjodXVXVG7O4YliWdSQIwgNg6LJUr9cjqVTqPue8ACAalk8QhI/RaPSFrutuSJmXjPIbYqAe/wgimQIAAAAASUVORK5CYII=",
}

TIMEZONES = {
    "IR": ZoneInfo("Asia/Tehran"),
    "US": ZoneInfo("America/New_York"),
    "UK": ZoneInfo("Europe/London"),
    "TR": ZoneInfo("Europe/Istanbul"),
    "JP": ZoneInfo("Asia/Tokyo"),
}

COUNTRY_NAMES = {
    "IR": "Iran (Tehran)",
    "US": "USA (New York)",
    "UK": "United Kingdom (London)",
    "TR": "Turkey (Istanbul)",
    "JP": "Japan (Tokyo)",
}

# ----------------------------------------------------------------------
# Jalali (Hijri-Shamsi / Solar) calendar support
# ----------------------------------------------------------------------
# Conversion routine adapted from JDF.SCR.IR (GNU/LGPL, open source & free)
# https://jdf.scr.ir/jdf/python
def _gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


# Persian (Farsi) month names, in order (1 = Farvardin ... 12 = Esfand)
JALALI_MONTH_NAMES = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

# Full Gregorian month names, keyed by the 3-letter abbreviation strftime
# ("%b") produces, so the "full month name" option can look one up without
# depending on OS locale settings.
GREGORIAN_MONTH_FULL = {
    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
    "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
    "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December",
}


def _gregorian_month_label(dt, full_month_name):
    """Return the month portion of the Gregorian date block.

    full_month_name=True  -> e.g. "September"
    full_month_name=False -> e.g. "Sep"  (easy to switch back later)
    """
    abbr = dt.strftime("%b")
    if full_month_name:
        return GREGORIAN_MONTH_FULL.get(abbr, abbr)
    return abbr


def _jalali_date_text(dt):
    """Return the 2-line Jalali date text (day / Persian month, no year)."""
    jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jd}\n{JALALI_MONTH_NAMES[jm - 1]}"


CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ClockWidget")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# Magic "chroma key" color used to punch a hole through the window on Windows
# when the glassy/transparent background option is enabled. Chosen to be a
# color nobody is likely to pick for text/flags. It is never shown to the
# user as an actual color - it's an implementation detail of the OS-level
# transparency trick (wm_attributes("-transparentcolor", ...)).
GLASS_KEY_COLOR = "#123456"

# Windows system font files used for the stroked (outlined) text rendering.
# Each is a list of candidates tried in order; falls back to PIL's built-in
# font (no bold/size control) if none of them exist.
CLOCK_FONT_CANDIDATES = ["consolab.ttf", "consola.ttf", "cour.ttf"]
DATE_FONT_CANDIDATES = ["segoeuib.ttf", "seguisb.ttf", "segoeui.ttf", "arial.ttf"]
# Separate bold/regular candidate lists for the weekday label, since it has
# its own independent bold toggle.
WEEKDAY_FONT_CANDIDATES_BOLD = ["segoeuib.ttf", "seguisb.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"]
WEEKDAY_FONT_CANDIDATES_REGULAR = ["segoeui.ttf", "arial.ttf"]


def _find_font(candidates, size):
    if not PIL_AVAILABLE:
        return None
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in candidates:
        path = os.path.join(fonts_dir, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _shape_rtl_text(text):
    """Best-effort Arabic/Persian shaping+reordering without libraqm.

    Pillow's built-in RTL support requires libraqm, which most default
    Windows Pillow installs don't have. If the optional pure-Python
    'arabic_reshaper' + 'python-bidi' packages are installed
    (pip install arabic_reshaper python-bidi), use them to join the
    Persian letters correctly and reverse them into visual order, then
    draw the result as plain left-to-right text. Returns None if those
    packages aren't available, so the caller can fall back further.
    Shapes each line separately so a mixed block (e.g. a plain numeric
    day line above a Persian month-name line) isn't reordered as a whole.
    """
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return None
    lines = text.split("\n")
    shaped_lines = [get_display(arabic_reshaper.reshape(line)) for line in lines]
    return "\n".join(shaped_lines)


def _render_stroked_text(text, font, fill, stroke_width, stroke_color, align="center", rtl=False):
    """Render text to a PhotoImage with an outline, via a transparent PIL image.

    rtl=True asks Pillow to shape/reorder the text as right-to-left (needed
    for Persian). This is tried in order of preference:
      1. Pillow's native direction="rtl" (needs the optional libraqm build)
      2. Pure-Python arabic_reshaper + python-bidi pre-shaping (needs those
         two pip packages, no libraqm needed)
      3. Plain left-to-right drawing (letters will look disjointed/reversed)
    """
    text_kwargs = {}
    if rtl:
        text_kwargs = {"direction": "rtl", "language": "fa"}
    scratch = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(scratch)
    try:
        bbox = d.multiline_textbbox(
            (0, 0), text, font=font, stroke_width=stroke_width, align=align, **text_kwargs)
    except Exception:
        # libraqm not available - fall back to pre-shaping the text
        # ourselves (option 2), or plain drawing if that's unavailable too.
        text_kwargs = {}
        if rtl:
            shaped = _shape_rtl_text(text)
            if shaped is not None:
                text = shaped
        bbox = d.multiline_textbbox((0, 0), text, font=font, stroke_width=stroke_width, align=align)
    pad = stroke_width + 2
    w = int(bbox[2] - bbox[0]) + pad * 2
    h = int(bbox[3] - bbox[1]) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.multiline_text(
        (pad - bbox[0], pad - bbox[1]), text, font=font, fill=fill,
        stroke_width=stroke_width, stroke_fill=stroke_color, align=align,
        **text_kwargs,
    )
    return ImageTk.PhotoImage(img)


DEFAULT_CONFIG = {
    "order": {"IR": 1, "US": 2, "UK": 3, "TR": 4, "JP": 5},
    "enabled": {"IR": True, "US": True, "UK": False, "TR": False, "JP": False},
    "font_size": 18,
    "font_color": "#00ff9c",
    "bg_color": "#0a0a0a",
    "glass_bg": False,
    "stroke_width": 1,
    "stroke_color": "#000000",
    "height": 40,
    "date_font_size": 10,
    "date_color": "#bbbbbb",
    "show_date": True,
    "show_jalali_date": True,
    "full_month_name": True,
    "show_weekday": True,
    "weekday_font_size": 12,
    "weekday_color": "#ffffff",
    "weekday_bold": True,
    "pos_x": 100,
    "pos_y": 20,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg["order"] = dict(DEFAULT_CONFIG["order"])
    cfg["enabled"] = dict(DEFAULT_CONFIG["enabled"])
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in ("order", "enabled") and isinstance(v, dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

class ClockWidget:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.overrideredirect(True)            # no border/titlebar
        self.root.wm_attributes("-topmost", True)    # always on top
        self.root.resizable(False, False)

        self._flag_images = {}  # keep references so Tk doesn't garbage-collect them
        self._offset_x = 0
        self._offset_y = 0
        self.settings_win = None
        self._after_id = None
        self.tray_icon = None

        self.build_ui()

        # NOTE: this menu is created once and re-used for the lifetime of the
        # app. build_ui() must never destroy it (it only destroys self.frame).
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Settings", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="Close  (Ctrl+X)", command=self.close_app)

        # Keyboard shortcut: Ctrl+X closes the app from anywhere in the window
        self.root.bind_all("<Control-x>", lambda e: self.close_app())
        self.root.bind_all("<Control-X>", lambda e: self.close_app())
        self.root.focus_force()

        self.setup_tray()
        self.update_clock()

    # ------------------------------------------------------------------
    # UI construction (called on start and whenever settings are applied)
    # ------------------------------------------------------------------
    def build_ui(self):
        cfg = self.cfg

        # Glassy/transparent background: on Windows, painting the window
        # (and every child widget) in one exact "key" color and telling the
        # OS to treat that color as a hole makes the whole rectangle
        # see-through - only the text and flags remain visible, floating
        # over the desktop. If disabled, we paint everything with the
        # regular bg_color and turn the OS-level transparency back off.
        if cfg.get("glass_bg", False):
            bg_color = GLASS_KEY_COLOR
            try:
                self.root.wm_attributes("-transparentcolor", GLASS_KEY_COLOR)
            except tk.TclError:
                pass  # not supported on this platform - falls back to opaque
        else:
            bg_color = cfg["bg_color"]
            try:
                self.root.wm_attributes("-transparentcolor", "")
            except tk.TclError:
                pass
        self._effective_bg = bg_color

        self.root.configure(bg=bg_color)

        # Only tear down the content frame from a previous build - never
        # touch other children of root (e.g. the right-click Menu), or
        # right-click stops working after Settings are applied.
        if hasattr(self, "frame") and self.frame.winfo_exists():
            self.frame.destroy()

        self.frame = tk.Frame(self.root, bg=bg_color)
        self.frame.pack(expand=True, fill="both")

        self._bind_drag_and_menu(self.root)
        self._bind_drag_and_menu(self.frame)

        # Determine active codes, sorted by their user-assigned order number
        active_codes = [c for c in FLAG_B64 if cfg["enabled"].get(c, False)]
        active_codes.sort(key=lambda c: cfg["order"].get(c, 99))
        self.active_codes = active_codes

        # Fonts used for the stroked (outlined) text rendering
        self._clock_font = _find_font(CLOCK_FONT_CANDIDATES, cfg["font_size"])
        self._date_font = _find_font(DATE_FONT_CANDIDATES, cfg["date_font_size"])
        weekday_candidates = (
            WEEKDAY_FONT_CANDIDATES_BOLD if cfg.get("weekday_bold", True)
            else WEEKDAY_FONT_CANDIDATES_REGULAR
        )
        self._weekday_font = _find_font(weekday_candidates, cfg.get("weekday_font_size", 12))

        # Optional weekday name before the date block(s), e.g. "Friday"
        self.weekday_label = None
        if cfg.get("show_date", True) and cfg.get("show_weekday", True):
            now = datetime.now()
            self.weekday_label = tk.Label(self.frame, bg=bg_color, justify="center")
            self.weekday_label.pack(side="left", padx=(8, 1))
            self._bind_drag_and_menu(self.weekday_label)
            self._set_stroked_label(self.weekday_label, now.strftime("%A"), self._weekday_font, cfg.get("weekday_color", "#ffffff"))

        # Optional date block(s) before the first clock: Jalali date first
        # (day + Persian month name, no year), then the Gregorian date.
        self.jalali_label = None
        self.date_label = None
        if cfg.get("show_date", True):
            now = datetime.now()
            is_first = self.weekday_label is None

            if cfg.get("show_jalali_date", True):
                jalali_text = _jalali_date_text(now)
                self.jalali_label = tk.Label(self.frame, bg=bg_color, justify="center")
                self.jalali_label.pack(side="left", padx=(8 if is_first else 6, 1))
                self._bind_drag_and_menu(self.jalali_label)
                self._set_stroked_label(self.jalali_label, jalali_text, self._date_font, cfg["date_color"], rtl=True)
                is_first = False

            month_label = _gregorian_month_label(now, cfg.get("full_month_name", True))
            date_text = now.strftime("%d") + "\n" + month_label
            self.date_label = tk.Label(self.frame, bg=bg_color, justify="center")
            self.date_label.pack(side="left", padx=(8 if is_first else 6, 1))
            self._bind_drag_and_menu(self.date_label)
            self._set_stroked_label(self.date_label, date_text, self._date_font, cfg["date_color"])

        # Flag + time pairs
        self.time_labels = {}
        for i, code in enumerate(active_codes):
            img_data = base64.b64decode(FLAG_B64[code])
            photo = tk.PhotoImage(data=img_data)
            self._flag_images[code] = photo

            flag_lbl = tk.Label(self.frame, image=photo, bg=bg_color, bd=0)
            flag_lbl.pack(side="left", padx=(0 if i == 0 and not self.date_label else 8, 4))
            self._bind_drag_and_menu(flag_lbl)

            time_lbl = tk.Label(self.frame, bg=bg_color)
            time_lbl.pack(side="left")
            self._bind_drag_and_menu(time_lbl)
            self._set_stroked_label(time_lbl, "--:--", self._clock_font, cfg["font_color"])

            self.time_labels[code] = time_lbl

        # Auto-size the window to fit its content, fixed height from config
        self.root.update_idletasks()
        req_width = self.frame.winfo_reqwidth() + 4
        height = cfg["height"]
        self.root.geometry(f"{req_width}x{height}+{cfg['pos_x']}+{cfg['pos_y']}")

    def _set_stroked_label(self, label, text, font, color, rtl=False):
        """Render text with an outline (stroke) into the given Label.

        Uses Pillow to draw the text with a colored outline, since plain
        tkinter Labels have no built-in text-stroke option. Falls back to a
        normal (unstroked) text label if Pillow isn't available.
        """
        cfg = self.cfg
        stroke_width = cfg.get("stroke_width", 0)
        stroke_color = cfg.get("stroke_color", "#000000")
        if PIL_AVAILABLE and font is not None:
            photo = _render_stroked_text(text, font, color, stroke_width, stroke_color, rtl=rtl)
            label.configure(image=photo, text="")
            label.image = photo  # keep a reference so Tk doesn't GC it
        else:
            label.configure(text=text, fg=color, font=("Consolas", 14, "bold"), image="")

    def _bind_drag_and_menu(self, widget):
        widget.bind("<ButtonPress-1>", self.start_move)
        widget.bind("<B1-Motion>", self.do_move)
        widget.bind("<Button-3>", self.show_menu)

    # ------------------------------------------------------------------
    # Dragging / context menu
    # ------------------------------------------------------------------
    def start_move(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def do_move(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")
        self.cfg["pos_x"] = x
        self.cfg["pos_y"] = y

    def show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ------------------------------------------------------------------
    # Clock update
    # ------------------------------------------------------------------
    def update_clock(self):
        now_utc = datetime.now(ZoneInfo("UTC"))
        for code, lbl in self.time_labels.items():
            t = now_utc.astimezone(TIMEZONES[code]).strftime("%H:%M")
            self._set_stroked_label(lbl, t, self._clock_font, self.cfg["font_color"])
        if self.date_label is not None or self.jalali_label is not None or self.weekday_label is not None:
            now = datetime.now()
            if self.weekday_label is not None:
                self._set_stroked_label(self.weekday_label, now.strftime("%A"), self._weekday_font, self.cfg.get("weekday_color", "#ffffff"))
            if self.jalali_label is not None:
                jalali_text = _jalali_date_text(now)
                self._set_stroked_label(self.jalali_label, jalali_text, self._date_font, self.cfg["date_color"], rtl=True)
            if self.date_label is not None:
                month_label = _gregorian_month_label(now, self.cfg.get("full_month_name", True))
                date_text = now.strftime("%d") + "\n" + month_label
                self._set_stroked_label(self.date_label, date_text, self._date_font, self.cfg["date_color"])
        self._after_id = self.root.after(1000, self.update_clock)

    # ------------------------------------------------------------------
    # Settings window
    # ------------------------------------------------------------------
    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return

        cfg = self.cfg
        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("Clock Widget Settings")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg="#f0f0f0")

        pad = {"padx": 8, "pady": 4}

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        settings_tab = tk.Frame(nb, bg="#f0f0f0")
        nb.add(settings_tab, text="Settings")
        about_tab = tk.Frame(nb, bg="#f0f0f0", padx=20, pady=20)
        nb.add(about_tab, text="About")
        tk.Label(about_tab, text="developed by: Senuvard_tools",
                 bg="#f0f0f0").pack(anchor="w", pady=(0, 10))
        channel = tk.Label(about_tab, text="Telegram channel: @Senuvard_tools",
                           bg="#f0f0f0", fg="#0066cc", cursor="hand2",
                           font=("Segoe UI", 10, "underline"))
        channel.pack(anchor="w")
        channel.bind("<Button-1>", lambda event: webbrowser.open_new_tab(
            "https://t.me/Senuvard_tools"))

        # ---- Timezones section ----
        tz_frame = tk.LabelFrame(settings_tab, text="Timezones (check to show, set order number)", bg="#f0f0f0")
        tz_frame.pack(fill="x", padx=10, pady=(10, 4))

        self._enabled_vars = {}
        self._order_vars = {}
        for code in FLAG_B64:
            row = tk.Frame(tz_frame, bg="#f0f0f0")
            row.pack(fill="x", padx=4, pady=2)

            ev = tk.BooleanVar(value=cfg["enabled"].get(code, False))
            self._enabled_vars[code] = ev
            cb = tk.Checkbutton(row, variable=ev, bg="#f0f0f0")
            cb.pack(side="left")

            lbl = tk.Label(row, text=COUNTRY_NAMES[code], bg="#f0f0f0", width=24, anchor="w")
            lbl.pack(side="left")

            tk.Label(row, text="Order:", bg="#f0f0f0").pack(side="left", padx=(6, 2))
            ov = tk.IntVar(value=cfg["order"].get(code, 9))
            self._order_vars[code] = ov
            sb = tk.Spinbox(row, from_=1, to=9, width=3, textvariable=ov)
            sb.pack(side="left")

        # ---- Date section ----
        date_frame = tk.LabelFrame(settings_tab, text="Date (shown before first clock)", bg="#f0f0f0")
        date_frame.pack(fill="x", padx=10, pady=4)

        self._show_date_var = tk.BooleanVar(value=cfg.get("show_date", True))
        tk.Checkbutton(date_frame, text="Show date", variable=self._show_date_var, bg="#f0f0f0").grid(
            row=0, column=0, columnspan=2, sticky="w", **pad)

        self._show_weekday_var = tk.BooleanVar(value=cfg.get("show_weekday", True))
        tk.Checkbutton(
            date_frame, text='Show weekday name before the date(s) (e.g. "Friday")',
            variable=self._show_weekday_var, bg="#f0f0f0").grid(
            row=1, column=0, columnspan=4, sticky="w", **pad)

        tk.Label(date_frame, text="Weekday font size:", bg="#f0f0f0").grid(row=2, column=0, sticky="w", **pad)
        self._weekday_size_var = tk.IntVar(value=cfg.get("weekday_font_size", 12))
        tk.Spinbox(date_frame, from_=6, to=32, width=4, textvariable=self._weekday_size_var).grid(
            row=2, column=1, sticky="w", **pad)

        self._weekday_bold_var = tk.BooleanVar(value=cfg.get("weekday_bold", True))
        tk.Checkbutton(date_frame, text="Bold", variable=self._weekday_bold_var, bg="#f0f0f0").grid(
            row=2, column=2, sticky="w", **pad)

        tk.Label(date_frame, text="Weekday color:", bg="#f0f0f0").grid(row=2, column=3, sticky="w", **pad)
        self._weekday_color_var = tk.StringVar(value=cfg.get("weekday_color", "#ffffff"))
        self._weekday_color_btn = tk.Button(
            date_frame, text="Choose...", bg=cfg.get("weekday_color", "#ffffff"),
            command=lambda: self._pick_color(self._weekday_color_var, self._weekday_color_btn))
        self._weekday_color_btn.grid(row=2, column=4, sticky="w", **pad)

        self._show_jalali_var = tk.BooleanVar(value=cfg.get("show_jalali_date", True))
        tk.Checkbutton(
            date_frame, text="Show Jalali (Persian) date before the Gregorian date",
            variable=self._show_jalali_var, bg="#f0f0f0").grid(
            row=3, column=0, columnspan=4, sticky="w", **pad)

        self._full_month_var = tk.BooleanVar(value=cfg.get("full_month_name", True))
        tk.Checkbutton(
            date_frame, text='Full Gregorian month name (e.g. "September" instead of "Sep")',
            variable=self._full_month_var, bg="#f0f0f0").grid(
            row=4, column=0, columnspan=4, sticky="w", **pad)

        tk.Label(date_frame, text="Date font size:", bg="#f0f0f0").grid(row=5, column=0, sticky="w", **pad)
        self._date_size_var = tk.IntVar(value=cfg["date_font_size"])
        tk.Spinbox(date_frame, from_=6, to=24, width=4, textvariable=self._date_size_var).grid(
            row=5, column=1, sticky="w", **pad)

        tk.Label(date_frame, text="Date color:", bg="#f0f0f0").grid(row=6, column=0, sticky="w", **pad)
        self._date_color_var = tk.StringVar(value=cfg["date_color"])
        self._date_color_btn = tk.Button(
            date_frame, text="Choose...", bg=cfg["date_color"],
            command=lambda: self._pick_color(self._date_color_var, self._date_color_btn))
        self._date_color_btn.grid(row=6, column=1, sticky="w", **pad)

        # ---- Appearance section ----
        appear_frame = tk.LabelFrame(settings_tab, text="Clock appearance", bg="#f0f0f0")
        appear_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(appear_frame, text="Font size:", bg="#f0f0f0").grid(row=0, column=0, sticky="w", **pad)
        self._font_size_var = tk.IntVar(value=cfg["font_size"])
        tk.Spinbox(appear_frame, from_=8, to=48, width=4, textvariable=self._font_size_var).grid(
            row=0, column=1, sticky="w", **pad)

        tk.Label(appear_frame, text="Font color:", bg="#f0f0f0").grid(row=1, column=0, sticky="w", **pad)
        self._font_color_var = tk.StringVar(value=cfg["font_color"])
        self._font_color_btn = tk.Button(
            appear_frame, text="Choose...", bg=cfg["font_color"],
            command=lambda: self._pick_color(self._font_color_var, self._font_color_btn))
        self._font_color_btn.grid(row=1, column=1, sticky="w", **pad)

        tk.Label(appear_frame, text="Text stroke width (px):", bg="#f0f0f0").grid(
            row=1, column=2, sticky="w", **pad)
        self._stroke_width_var = tk.IntVar(value=cfg.get("stroke_width", 1))
        tk.Spinbox(appear_frame, from_=0, to=4, width=3, textvariable=self._stroke_width_var).grid(
            row=1, column=3, sticky="w", **pad)

        tk.Label(appear_frame, text="Stroke color:", bg="#f0f0f0").grid(row=1, column=4, sticky="w", **pad)
        self._stroke_color_var = tk.StringVar(value=cfg.get("stroke_color", "#000000"))
        self._stroke_color_btn = tk.Button(
            appear_frame, text="Choose...", bg=cfg.get("stroke_color", "#000000"),
            command=lambda: self._pick_color(self._stroke_color_var, self._stroke_color_btn))
        self._stroke_color_btn.grid(row=1, column=5, sticky="w", **pad)

        tk.Label(appear_frame, text="Background color:", bg="#f0f0f0").grid(row=2, column=0, sticky="w", **pad)
        self._bg_color_var = tk.StringVar(value=cfg["bg_color"])
        self._bg_color_btn = tk.Button(
            appear_frame, text="Choose...", bg=cfg["bg_color"],
            command=lambda: self._pick_color(self._bg_color_var, self._bg_color_btn))
        self._bg_color_btn.grid(row=2, column=1, sticky="w", **pad)

        self._glass_var = tk.BooleanVar(value=cfg.get("glass_bg", False))
        tk.Checkbutton(
            appear_frame, text="Glassy background (fully see-through - shows the desktop behind it)",
            variable=self._glass_var, bg="#f0f0f0",
            command=lambda: self._bg_color_btn.configure(
                state=("disabled" if self._glass_var.get() else "normal"))
        ).grid(row=3, column=0, columnspan=6, sticky="w", **pad)
        tk.Label(
            appear_frame,
            text="Note: when glassy, background color is ignored and the see-through\n"
                 "area won't respond to clicks - drag/right-click using the text or flags.",
            bg="#f0f0f0", fg="#666666", justify="left", font=("Segoe UI", 8),
        ).grid(row=4, column=0, columnspan=6, sticky="w", padx=8)
        if cfg.get("glass_bg", False):
            self._bg_color_btn.configure(state="disabled")

        tk.Label(appear_frame, text="Height (px):", bg="#f0f0f0").grid(row=5, column=0, sticky="w", **pad)
        self._height_var = tk.IntVar(value=cfg["height"])
        tk.Spinbox(appear_frame, from_=24, to=120, width=4, textvariable=self._height_var).grid(
            row=5, column=1, sticky="w", **pad)

        # ---- Buttons ----
        btn_frame = tk.Frame(win, bg="#f0f0f0")
        btn_frame.pack(fill="x", padx=10, pady=(6, 10))
        tk.Button(btn_frame, text="Apply", width=10, command=self.apply_settings).pack(side="right", padx=4)
        tk.Button(btn_frame, text="Cancel", width=10, command=win.destroy).pack(side="right")

    def _pick_color(self, var, button):
        color = colorchooser.askcolor(color=var.get())
        if color and color[1]:
            var.set(color[1])
            button.configure(bg=color[1])

    def apply_settings(self):
        cfg = self.cfg
        for code in FLAG_B64:
            cfg["enabled"][code] = self._enabled_vars[code].get()
            cfg["order"][code] = self._order_vars[code].get()

        cfg["show_date"] = self._show_date_var.get()
        cfg["show_weekday"] = self._show_weekday_var.get()
        cfg["weekday_font_size"] = self._weekday_size_var.get()
        cfg["weekday_bold"] = self._weekday_bold_var.get()
        cfg["weekday_color"] = self._weekday_color_var.get()
        cfg["show_jalali_date"] = self._show_jalali_var.get()
        cfg["full_month_name"] = self._full_month_var.get()
        cfg["date_font_size"] = self._date_size_var.get()
        cfg["date_color"] = self._date_color_var.get()

        cfg["font_size"] = self._font_size_var.get()
        cfg["font_color"] = self._font_color_var.get()
        cfg["stroke_width"] = self._stroke_width_var.get()
        cfg["stroke_color"] = self._stroke_color_var.get()
        cfg["bg_color"] = self._bg_color_var.get()
        cfg["glass_bg"] = self._glass_var.get()
        cfg["height"] = self._height_var.get()

        # Guard against turning every timezone off
        if not any(cfg["enabled"].values()):
            cfg["enabled"]["IR"] = True

        save_config(cfg)
        self.settings_win.destroy()
        self.settings_win = None
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.build_ui()
        self.update_clock()

    # ------------------------------------------------------------------
    # System tray icon
    # ------------------------------------------------------------------
    def setup_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            # pystray/Pillow not installed - app still works fine without a
            # tray icon, just skip it.
            return

        image = self._load_tray_image(Image, ImageDraw)

        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", self._tray_toggle_visibility, default=True),
            pystray.MenuItem("Settings", self._tray_open_settings),
            pystray.MenuItem("Close", self._tray_close),
        )
        self.tray_icon = pystray.Icon("ClockWidget", image, "Clock Widget", menu)

        import threading
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _load_tray_image(self, Image, ImageDraw):
        # Look for a user-supplied icon.ico or icon.png next to the exe/script
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        for fname in ("icon.ico", "icon.png"):
            path = os.path.join(base_dir, fname)
            if os.path.exists(path):
                try:
                    return Image.open(path)
                except Exception:
                    pass

        # Fallback: draw a simple default clock icon
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill="#0a0a0a", outline="#00ff9c", width=4)
        d.line((32, 32, 32, 14), fill="#00ff9c", width=4)
        d.line((32, 32, 46, 32), fill="#00ff9c", width=4)
        return img

    def _tray_toggle_visibility(self, icon, item):
        self.root.after(0, self._toggle_visibility)

    def _toggle_visibility(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        else:
            self.root.withdraw()

    def _tray_open_settings(self, icon, item):
        self.root.after(0, self._show_and_open_settings)

    def _show_and_open_settings(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        self.open_settings()

    def _tray_close(self, icon, item):
        self.root.after(0, self.close_app)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------
    def close_app(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ClockWidget().run()
