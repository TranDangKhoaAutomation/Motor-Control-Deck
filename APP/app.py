import queue
import threading
import time
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import serial
from PIL import Image
from serial.tools import list_ports


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


BACKGROUND = "#f5f7fb"
SURFACE = "#ffffff"
SURFACE_ALT = "#eef3f8"
SURFACE_STRONG = "#e7edf5"
TEXT = "#132033"
MUTED = "#667489"
ACCENT = "#1570ef"
ACCENT_HOVER = "#0f5dcc"
ACCENT_SOFT = "#dce8ff"
SUCCESS = "#157f3d"
SUCCESS_SOFT = "#ddf5e6"
DANGER = "#c83f3f"
DANGER_HOVER = "#aa3030"
DANGER_SOFT = "#fde2e2"
SECONDARY = "#ef8d32"
SECONDARY_HOVER = "#d77620"
OUTLINE = "#d7e0ea"
FRAME_PREVIEW = "#f7f9fc"
LOG_BG = "#f9fbfd"
TOOLTIP_BG = "#1f2a37"
TOOLTIP_TEXT = "#f8fafc"

KEY_COMMANDS = {
    "w": "FWD",
    "s": "BACK",
    "a": "LEFT",
    "d": "RIGHT",
}

BRIDGE_STREAM_MS = 20
COM_AUTO_REFRESH_MS = 1200
AUTO_RECONNECT_RETRY_S = 1.5
DEFAULT_BRIDGE_BAUD = 115200
DEFAULT_DIRECT_BAUD = "115200"
DEFAULT_DIRECT_INTERVAL_MS = 20
DIRECT_BAUD_CHOICES = ["9600", "19200", "38400", "57600", "115200", "230400"]
APP_DIR = Path(__file__).resolve().parent
BRAND_LOGO_PATH = APP_DIR / "logo_trandangkhoa_background.png"
BRAND_ICON_PATH = APP_DIR / "logo_trandangkhoa_icon.ico"
BRAND_NAME = "TranDangKhoaAutomation"
BRAND_LABEL = BRAND_NAME
APP_TITLE = f"{BRAND_NAME} Control Deck"
APP_HEADER_TITLE = BRAND_LABEL
APP_SUBTITLE = "USB CDC 4PID Control Deck for STM32F103C8T6 bridge control and direct motor-driver UART testing."
TAB_BASE = "Base Control"
TAB_MOTOR = "STM32 Bridge"
TAB_DIRECT = "Direct UART"
TAB_NAMES = (TAB_BASE, TAB_MOTOR, TAB_DIRECT)


class HoverTooltip:
    def __init__(self, widget, text: str, *, delay_ms: int = 260) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._hide_after_id: str | None = None
        self._tipwindow: tk.Toplevel | None = None
        self._bound_widget_names: set[str] = set()

        self._bind_widget_tree(self.widget)
        self.widget.after_idle(lambda: self._bind_widget_tree(self.widget))
        self.widget.bind("<Destroy>", self._on_destroy, add="+")

    def _bind_widget_tree(self, widget) -> None:
        widget_name = str(widget)
        if widget_name in self._bound_widget_names:
            return

        self._bound_widget_names.add(widget_name)
        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._schedule_hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

        for child in widget.winfo_children():
            self._bind_widget_tree(child)

    def _schedule_show(self, _event=None) -> None:
        self._cancel_scheduled_hide()
        self._cancel_scheduled_show()
        self._after_id = self.widget.after(self.delay_ms, self.show)

    def _cancel_scheduled_show(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _schedule_hide(self, _event=None) -> None:
        self._cancel_scheduled_show()
        self._cancel_scheduled_hide()
        self._hide_after_id = self.widget.after(40, self._hide_if_pointer_left)

    def _cancel_scheduled_hide(self) -> None:
        if self._hide_after_id is not None:
            self.widget.after_cancel(self._hide_after_id)
            self._hide_after_id = None

    def _hide_if_pointer_left(self) -> None:
        self._hide_after_id = None
        if not self._pointer_inside_target():
            self._hide()

    def _pointer_inside_target(self) -> bool:
        try:
            current = self.widget.winfo_containing(
                self.widget.winfo_pointerx(),
                self.widget.winfo_pointery(),
            )
        except tk.TclError:
            return False

        while current is not None:
            if str(current) in self._bound_widget_names:
                return True
            parent_name = current.winfo_parent()
            if not parent_name:
                break
            try:
                current = current.nametowidget(parent_name)
            except KeyError:
                break
        return False

    def show(self) -> None:
        self._after_id = None
        if not self._pointer_inside_target():
            return
        if self._tipwindow is not None or not self.text:
            return

        tipwindow = tk.Toplevel(self.widget)
        tipwindow.withdraw()
        tipwindow.overrideredirect(True)
        try:
            tipwindow.attributes("-topmost", True)
        except tk.TclError:
            pass

        label = tk.Label(
            tipwindow,
            text=self.text,
            justify="left",
            wraplength=320,
            bg=TOOLTIP_BG,
            fg=TOOLTIP_TEXT,
            padx=12,
            pady=10,
            font=("Segoe UI", 10),
        )
        label.pack()

        tipwindow.update_idletasks()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 12
        y = self.widget.winfo_rooty() - 4
        screen_width = tipwindow.winfo_screenwidth()
        screen_height = tipwindow.winfo_screenheight()
        width = tipwindow.winfo_reqwidth()
        height = tipwindow.winfo_reqheight()

        x = min(x, screen_width - width - 16)
        y = min(max(y, 16), screen_height - height - 16)
        tipwindow.geometry(f"+{x}+{y}")
        tipwindow.deiconify()
        self._tipwindow = tipwindow

    def _hide(self, _event=None) -> None:
        self._cancel_scheduled_show()
        self._cancel_scheduled_hide()
        if self._tipwindow is not None:
            self._tipwindow.destroy()
            self._tipwindow = None

    def _on_destroy(self, _event=None) -> None:
        self._hide()


class AsyncSerialTransport:
    def __init__(self, name: str, *, decode_lines: bool) -> None:
        self.name = name
        self.decode_lines = decode_lines
        self._command_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._lock = threading.Lock()
        self._connected = False
        self._port = ""
        self._baudrate = 0
        self._error = ""
        self._stop = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def connect(self, port: str, baudrate: int) -> None:
        self._command_queue.put(("connect", (port, baudrate)))

    def disconnect(self) -> None:
        self._command_queue.put(("disconnect", None))

    def write_bytes(self, payload: bytes) -> None:
        self._command_queue.put(("write", payload))

    def write_line(self, line: str) -> None:
        self.write_bytes(line.encode("ascii", errors="ignore") + b"\n")

    def snapshot(self) -> dict[str, str | int | bool]:
        with self._lock:
            return {
                "connected": self._connected,
                "port": self._port,
                "baudrate": self._baudrate,
                "error": self._error,
            }

    def read_events(self) -> list[tuple[str, object]]:
        events: list[tuple[str, object]] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                return events

    def close(self) -> None:
        self._command_queue.put(("close", None))
        self._thread.join(timeout=1.0)

    def _set_status(self, *, connected: bool, port: str = "", baudrate: int = 0, error: str = "") -> None:
        with self._lock:
            self._connected = connected
            self._port = port
            self._baudrate = baudrate
            self._error = error

    def _emit(self, kind: str, payload: object) -> None:
        self._event_queue.put((kind, payload))

    def _close_port(self, serial_port: serial.Serial | None) -> None:
        if serial_port is None:
            return
        try:
            serial_port.close()
        except serial.SerialException:
            pass

    def _worker(self) -> None:
        serial_port: serial.Serial | None = None
        read_buffer = bytearray()

        while not self._stop:
            try:
                action, payload = self._command_queue.get(timeout=0.05)
            except queue.Empty:
                action = ""
                payload = None

            if action == "connect":
                port, baudrate = payload
                self._close_port(serial_port)
                serial_port = None
                read_buffer.clear()
                try:
                    serial_port = serial.Serial(
                        port=port,
                        baudrate=baudrate,
                        timeout=0.05,
                        write_timeout=0.2,
                    )
                    self._set_status(connected=True, port=port, baudrate=baudrate, error="")
                    self._emit("status", f"Connected to {port} @ {baudrate}")
                except serial.SerialException as exc:
                    serial_port = None
                    self._set_status(connected=False, port="", baudrate=0, error=str(exc))
                    self._emit("error", str(exc))

            elif action == "disconnect":
                self._close_port(serial_port)
                serial_port = None
                read_buffer.clear()
                self._set_status(connected=False, port="", baudrate=0, error="")
                self._emit("status", "Disconnected")

            elif action == "write":
                if serial_port is None or not serial_port.is_open:
                    continue
                try:
                    serial_port.write(payload)
                    serial_port.flush()
                except serial.SerialException as exc:
                    self._close_port(serial_port)
                    serial_port = None
                    read_buffer.clear()
                    self._set_status(connected=False, port="", baudrate=0, error=str(exc))
                    self._emit("error", str(exc))

            elif action == "close":
                self._stop = True
                self._close_port(serial_port)
                serial_port = None
                read_buffer.clear()
                self._set_status(connected=False, port="", baudrate=0, error="")
                continue

            if serial_port is None or not serial_port.is_open:
                continue

            try:
                waiting = serial_port.in_waiting
                chunk = serial_port.read(waiting or 1)
                if not chunk:
                    continue

                if self.decode_lines:
                    read_buffer.extend(chunk)
                    while True:
                        newline_index = read_buffer.find(b"\n")
                        if newline_index == -1:
                            break

                        raw_line = bytes(read_buffer[:newline_index]).rstrip(b"\r")
                        del read_buffer[: newline_index + 1]
                        if raw_line:
                            self._emit("rx_line", raw_line.decode("ascii", errors="replace"))
                else:
                    self._emit("rx_bytes", bytes(chunk))
            except serial.SerialException as exc:
                self._close_port(serial_port)
                serial_port = None
                read_buffer.clear()
                self._set_status(connected=False, port="", baudrate=0, error=str(exc))
                self._emit("error", str(exc))


class MotorCard(ctk.CTkFrame):
    def __init__(self, master, index: int, on_change) -> None:
        super().__init__(
            master,
            corner_radius=24,
            fg_color=SURFACE,
            border_width=1,
            border_color=OUTLINE,
        )
        self.index = index
        self.on_change = on_change
        self.dir_value = tk.StringVar(value="0")
        self.dir_text_var = tk.StringVar(value="Nghịch")
        self.speed_value = tk.IntVar(value=0)

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=f"Motor {index}",
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=18, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        hint = ctk.CTkFrame(self, fg_color="transparent")
        hint.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        hint.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hint,
            text="Đảo chiều",
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        direction_row = ctk.CTkFrame(self, fg_color="transparent")
        direction_row.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="w")
        direction_row.grid_columnconfigure(1, weight=1)

        self.dir_switch = ctk.CTkSwitch(
            direction_row,
            text="",
            variable=self.dir_value,
            onvalue="1",
            offvalue="0",
            command=self._on_direction_toggle,
            fg_color=SURFACE_ALT,
            progress_color=ACCENT,
            button_color=SURFACE,
            button_hover_color=SURFACE_ALT,
            border_width=0,
            width=44,
            height=24,
            switch_width=40,
            switch_height=20,
        )
        self.dir_switch.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            direction_row,
            textvariable=self.dir_text_var,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12, weight="bold"),
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")

        ctk.CTkLabel(
            direction_row,
            text="Tắt = nghịch, bật = thuận",
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=10),
        ).grid(row=1, column=1, padx=(8, 0), sticky="w")

        speed_row = ctk.CTkFrame(self, fg_color="transparent")
        speed_row.grid(row=3, column=0, padx=14, sticky="ew")
        speed_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            speed_row,
            text="Speed",
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(
            speed_row,
            text="0",
            text_color=SECONDARY,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
        )
        self.speed_label.grid(row=0, column=1, sticky="e")

        self.slider = ctk.CTkSlider(
            self,
            from_=0,
            to=255,
            number_of_steps=255,
            progress_color=SECONDARY,
            button_color=SECONDARY,
            button_hover_color=SECONDARY_HOVER,
            command=self._on_slider,
        )
        self.slider.grid(row=4, column=0, padx=14, pady=(6, 14), sticky="ew")

    def _on_slider(self, value: float) -> None:
        current = int(round(value))
        self.speed_value.set(current)
        self.speed_label.configure(text=str(current))
        self.on_change()

    def _on_direction_toggle(self) -> None:
        self.dir_text_var.set("Thuận" if self.dir_value.get() == "1" else "Nghịch")
        self.on_change()

    def set_values(self, direction: int, speed: int) -> None:
        self.dir_value.set("1" if direction else "0")
        self.dir_text_var.set("Thuận" if direction else "Nghịch")
        self.speed_value.set(speed)
        self.slider.set(speed)
        self.speed_label.configure(text=str(speed))

    def get_values(self) -> tuple[int, int]:
        return int(self.dir_value.get()), int(self.speed_value.get())


class ControlApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_scaling = float(self._get_window_scaling())
        window_width = min(1440, max(960, screen_width - 36))
        window_height = min(860, max(640, screen_height - 96))
        min_width = min(1100, max(900, screen_width - 80))
        min_height = min(700, max(620, screen_height - 140))
        logical_width = max(860, int(window_width / window_scaling))
        logical_height = max(560, int(window_height / window_scaling))
        logical_min_width = max(820, int(min_width / window_scaling))
        logical_min_height = max(520, int(min_height / window_scaling))
        self.geometry(f"{logical_width}x{logical_height}+0+0")
        self.minsize(logical_min_width, logical_min_height)
        self.configure(fg_color=BACKGROUND)

        self.bridge_transport = AsyncSerialTransport("STM32 Bridge", decode_lines=True)
        self.direct_transport = AsyncSerialTransport("Direct UART", decode_lines=False)
        self.brand_logo_image: ctk.CTkImage | None = None
        self.brand_window_icon: tk.PhotoImage | None = None

        self.bridge_port_var = tk.StringVar(value="")
        self.direct_port_var = tk.StringVar(value="")
        self.base_speed_var = tk.IntVar(value=50)
        self.lock_var = tk.IntVar(value=0)
        self.direct_baud_var = tk.StringVar(value=DEFAULT_DIRECT_BAUD)
        self.direct_address_var = tk.StringVar(value="1")
        self.direct_direction_var = tk.StringVar(value="1")
        self.direct_speed_var = tk.IntVar(value=0)
        self.direct_interval_var = tk.StringVar(value=str(DEFAULT_DIRECT_INTERVAL_MS))
        self.direct_duration_var = tk.StringVar(value="3")
        self.direct_direction_text_var = tk.StringVar(value="Thuận")

        self.active_tab = TAB_NAMES[0]
        self.active_keys: list[str] = []
        self.command_buttons: dict[str, ctk.CTkButton] = {}
        self.motor_cards: list[MotorCard] = []
        self.tab_buttons: dict[str, ctk.CTkButton] = {}
        self.page_frames: dict[str, ctk.CTkScrollableFrame] = {}
        self.bridge_log_boxes: list[ctk.CTkTextbox] = []
        self.direct_log_boxes: list[ctk.CTkTextbox] = []
        self.bridge_port_lookup: dict[str, str] = {}
        self.direct_port_lookup: dict[str, str] = {}
        self.bridge_port_combo: ctk.CTkComboBox | None = None
        self.bridge_connect_button: ctk.CTkButton | None = None
        self.bridge_status_badge: ctk.CTkLabel | None = None
        self.bridge_context_feedback_label: ctk.CTkLabel | None = None

        self.bridge_mode = "IDLE"
        self.active_base_command = "STOP"
        self.bridge_last_feedback = "Bridge ready"
        self.bridge_last_trace = "Waiting for TRACE,UART..."
        self.bridge_want_connection = False
        self.bridge_target_port = ""
        self.bridge_target_baud = DEFAULT_BRIDGE_BAUD
        self.bridge_last_reconnect_attempt = 0.0

        self.direct_last_feedback = "Direct UART ready"
        self.direct_last_rx = "No RX yet"
        self.direct_tx_count = 0
        self.direct_stream_mode = "IDLE"
        self.direct_stream_started = 0.0
        self.direct_stream_ends_at = 0.0
        self.direct_stream_job: str | None = None
        self.direct_want_connection = False
        self.direct_target_port = ""
        self.direct_target_baud = int(DEFAULT_DIRECT_BAUD)
        self.direct_last_reconnect_attempt = 0.0

        self.hero_status_var = tk.StringVar(value=TAB_BASE)
        self.bridge_status_var = tk.StringVar(value="Disconnected")
        self.bridge_feedback_var = tk.StringVar(value=self.bridge_last_feedback)
        self.bridge_last_tx_var = tk.StringVar(value="No TX yet")
        self.bridge_last_rx_var = tk.StringVar(value="No RX yet")
        self.bridge_trace_var = tk.StringVar(value=self.bridge_last_trace)
        self.base_feedback_var = tk.StringVar(value="Giữ pad hoặc dùng W/A/S/D. Có thể giữ 2 phím để đi chéo.")
        self.base_preview_var = tk.StringVar(value="")
        self.motor_feedback_var = tk.StringVar(value="Edit the 4 motors, then click Send All.")
        self.motor_preview_var = tk.StringVar(value="")
        self.direct_status_var = tk.StringVar(value="Disconnected")
        self.direct_feedback_var = tk.StringVar(value=self.direct_last_feedback)
        self.direct_preview_var = tk.StringVar(value="")
        self.direct_decimal_var = tk.StringVar(value="")
        self.direct_elapsed_var = tk.StringVar(value="0.0 s")
        self.direct_remaining_var = tk.StringVar(value="0.0 s")
        self.direct_tx_count_var = tk.StringVar(value="0")
        self.direct_rx_var = tk.StringVar(value=self.direct_last_rx)

        self._load_brand_assets()
        self._build_layout()
        self._refresh_bridge_ports()
        self._refresh_direct_ports()
        self._update_base_preview()
        self._update_motor_preview()
        self._update_direct_preview()
        self._update_base_button_states()
        self._show_tab(self.active_tab)

        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(120, self._poll_transports)
        self.after(BRIDGE_STREAM_MS, self._bridge_heartbeat)
        self.after(120, self._direct_runtime_heartbeat)
        self.after(COM_AUTO_REFRESH_MS, self._auto_refresh_ports)

    def _load_brand_assets(self) -> None:
        if not BRAND_LOGO_PATH.exists():
            return
        try:
            logo = Image.open(BRAND_LOGO_PATH).convert("RGBA")
            self.brand_logo_image = ctk.CTkImage(light_image=logo, dark_image=logo, size=(74, 74))
            self._ensure_brand_icon_file(logo)
            if BRAND_ICON_PATH.exists():
                try:
                    self.iconbitmap(str(BRAND_ICON_PATH))
                except tk.TclError:
                    pass
            self.brand_window_icon = tk.PhotoImage(file=str(BRAND_LOGO_PATH))
            self.iconphoto(True, self.brand_window_icon)
        except Exception:
            self.brand_logo_image = None
            self.brand_window_icon = None

    def _ensure_brand_icon_file(self, logo: Image.Image) -> None:
        if BRAND_ICON_PATH.exists():
            return
        try:
            logo.save(BRAND_ICON_PATH, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        except Exception:
            pass

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        hero = ctk.CTkFrame(self, corner_radius=22, fg_color=SURFACE, border_width=1, border_color=OUTLINE)
        hero.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="ew")
        hero.grid_columnconfigure(0, weight=1)
        hero.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, padx=20, pady=18, sticky="w")
        left.grid_columnconfigure(1, weight=1)

        if self.brand_logo_image is not None:
            ctk.CTkLabel(
                left,
                text="",
                image=self.brand_logo_image,
            ).grid(row=0, column=0, rowspan=3, padx=(0, 14), sticky="nw")

        title_col = 1 if self.brand_logo_image is not None else 0

        ctk.CTkLabel(
            left,
            text=APP_HEADER_TITLE,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24, weight="bold"),
        ).grid(row=0, column=title_col, sticky="w")

        ctk.CTkLabel(
            left,
            text=APP_SUBTITLE,
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wraplength=680,
            justify="left",
        ).grid(row=1, column=title_col, pady=(6, 0), sticky="w")

        ctk.CTkLabel(
            left,
            text=f"Bản quyền: {BRAND_LABEL}",
            corner_radius=999,
            fg_color=ACCENT_SOFT,
            text_color=ACCENT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=11, weight="bold"),
            padx=10,
            pady=4,
        ).grid(row=2, column=title_col, pady=(10, 0), sticky="w")

        right = ctk.CTkFrame(hero, fg_color="transparent")
        right.grid(row=0, column=1, padx=20, pady=18, sticky="e")

        self._create_summary_chip(right, "Active Page", self.hero_status_var, ACCENT_SOFT, ACCENT).grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self._create_summary_chip(right, "STM32 Bridge", self.bridge_status_var, FRAME_PREVIEW, TEXT).grid(row=0, column=1, padx=(0, 10), sticky="ew")
        self._create_summary_chip(right, "Direct UART", self.direct_status_var, FRAME_PREVIEW, TEXT).grid(row=0, column=2, sticky="ew")

        tabbar = ctk.CTkFrame(self, fg_color="transparent")
        tabbar.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="ew")
        tabbar.grid_columnconfigure((0, 1, 2), weight=1)

        for index, name in enumerate(TAB_NAMES):
            button = ctk.CTkButton(
                tabbar,
                text=name,
                height=38,
                corner_radius=16,
                fg_color=SURFACE_ALT,
                hover_color=SURFACE_STRONG,
                text_color=TEXT,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold"),
                command=lambda tab=name: self._show_tab(tab),
            )
            button.grid(row=0, column=index, padx=(0 if index == 0 else 6, 0 if index == 2 else 6), sticky="ew")
            self.tab_buttons[name] = button

        self.context_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.context_panel.grid(row=2, column=0, padx=18, pady=(0, 8), sticky="ew")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=3, column=0, padx=18, pady=(0, 18), sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        for name in TAB_NAMES:
            page = ctk.CTkScrollableFrame(content, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()
            self.page_frames[name] = page

        self._build_base_page(self.page_frames[TAB_BASE])
        self._build_motor_page(self.page_frames[TAB_MOTOR])
        self._build_direct_page(self.page_frames[TAB_DIRECT])

    def _build_bridge_context_panel(self) -> None:
        card = ctk.CTkFrame(self.context_panel, corner_radius=18, fg_color=SURFACE, border_width=1, border_color=OUTLINE)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        left.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="w")

        self._create_title_with_help(
            title_row,
            f"{BRAND_LABEL} | STM32 Bridge",
            "Cổng COM này chỉ dùng cho các trang làm việc qua STM32. Trang Direct UART dùng cổng COM và baud riêng ở tab Direct UART.",
            size=16,
        ).pack(side="left")

        ctk.CTkLabel(
            title_row,
            text=f"Baud {DEFAULT_BRIDGE_BAUD}",
            corner_radius=999,
            fg_color=ACCENT_SOFT,
            text_color=ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            padx=10,
            pady=4,
        ).pack(side="left", padx=(10, 0))

        self.bridge_context_feedback_label = ctk.CTkLabel(
            left,
            textvariable=self.bridge_feedback_var,
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            justify="left",
            wraplength=760,
            anchor="w",
        )
        self.bridge_context_feedback_label.grid(row=1, column=0, pady=(6, 0), sticky="ew")

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=1, padx=16, pady=12, sticky="e")

        self.bridge_port_combo = ctk.CTkComboBox(
            actions,
            width=360,
            values=["No COM ports"],
            variable=self.bridge_port_var,
            fg_color=FRAME_PREVIEW,
            border_color=OUTLINE,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SURFACE_ALT,
            dropdown_text_color=TEXT,
            text_color=TEXT,
            height=34,
        )
        self.bridge_port_combo.grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(actions, text="Refresh", width=80, height=34, fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT, command=self._refresh_bridge_ports).grid(row=0, column=1, padx=(0, 8))

        self.bridge_connect_button = ctk.CTkButton(
            actions,
            text="Connect",
            width=96,
            height=34,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._toggle_bridge_connection,
        )
        self.bridge_connect_button.grid(row=0, column=2, padx=(0, 8))

        self.bridge_status_badge = ctk.CTkLabel(
            actions,
            textvariable=self.bridge_status_var,
            corner_radius=999,
            fg_color=FRAME_PREVIEW,
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            padx=12,
            pady=6,
        )
        self.bridge_status_badge.grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(actions, text="Stop", width=84, height=34, fg_color=DANGER, hover_color=DANGER_HOVER, command=self._send_bridge_stop).grid(row=0, column=4)

        self._refresh_bridge_ports()

    def _build_base_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=7)
        page.grid_columnconfigure(1, weight=5)

        drive_card = self._create_card(page)
        drive_card.grid(row=0, column=0, padx=(0, 8), pady=(0, 10), sticky="nsew")
        drive_card.grid_columnconfigure((0, 1, 2), weight=1)

        self._create_section_header(
            drive_card,
            "Drive Pad",
            "Hold a pad button or use W/A/S/D. Keep two direction keys together to move diagonally. The app keeps sending the selected BASE frame every 20 ms.",
            f"Trang {TAB_BASE} gửi frame chuẩn dạng BASE,<lenh>,<toc_do>,<khoa_banh>. Khi nhả nút điều khiển, app sẽ gửi STOP.",
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 10), sticky="ew")

        shortcut_row = ctk.CTkFrame(drive_card, fg_color="transparent")
        shortcut_row.grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 8), sticky="ew")
        shortcut_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            shortcut_row,
            text="Keyboard: W tiến   S lùi   A trái   D phải   WA chéo trái tiến   WD chéo phải tiến   SA chéo trái lùi   SD chéo phải lùi",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="left",
            wraplength=760,
        ).grid(row=0, column=0, sticky="w")

        pad_frame = ctk.CTkFrame(drive_card, fg_color="transparent")
        pad_frame.grid(row=2, column=0, columnspan=3, padx=14, pady=(0, 14), sticky="nsew")
        pad_frame.grid_columnconfigure((0, 1, 2), weight=1)
        pad_frame.grid_rowconfigure((0, 1, 2), weight=1)

        self._create_command_button(pad_frame, "FWD_LEFT", "WA\nChéo Trái", 0, 0, SECONDARY, SECONDARY_HOVER)
        self._create_command_button(pad_frame, "FWD", "W\nTiến", 0, 1, ACCENT, ACCENT_HOVER)
        self._create_command_button(pad_frame, "FWD_RIGHT", "WD\nChéo Phải", 0, 2, SECONDARY, SECONDARY_HOVER)
        self._create_command_button(pad_frame, "LEFT", "A\nTrái", 1, 0, ACCENT, ACCENT_HOVER)
        self._create_stop_center(pad_frame, 1, 1)
        self._create_command_button(pad_frame, "RIGHT", "D\nPhải", 1, 2, ACCENT, ACCENT_HOVER)
        self._create_command_button(pad_frame, "BACK_LEFT", "SA\nChéo Trái", 2, 0, SECONDARY, SECONDARY_HOVER)
        self._create_command_button(pad_frame, "BACK", "S\nLùi", 2, 1, ACCENT, ACCENT_HOVER)
        self._create_command_button(pad_frame, "BACK_RIGHT", "SD\nChéo Phải", 2, 2, SECONDARY, SECONDARY_HOVER)

        settings_card = self._create_card(page)
        settings_card.grid(row=0, column=1, padx=(8, 0), pady=(0, 10), sticky="nsew")
        settings_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            settings_card,
            "Base Settings",
            "Single-speed base mode. This removes the old confusing two-speed model and keeps the frame explicit.",
            "Lock = 1 sẽ giữ chế độ hãm hoặc khóa bánh khi STOP. Khung preview bên dưới chính là frame thật mà app sẽ gửi.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._create_slider_panel(
            settings_card,
            row=1,
            title="Base Speed",
            variable=self.base_speed_var,
            accent=ACCENT,
            hover=ACCENT_HOVER,
            help_text="Giá trị tốc độ 0..255 được dùng chung cho mọi lệnh BASE.",
            command=self._on_base_settings_changed,
        )

        lock_wrap = ctk.CTkFrame(settings_card, fg_color="transparent")
        lock_wrap.grid(row=2, column=0, padx=16, pady=(2, 8), sticky="w")

        self.base_lock_switch = ctk.CTkSwitch(
            lock_wrap,
            text="Wheel lock on STOP",
            variable=self.lock_var,
            onvalue=1,
            offvalue=0,
            progress_color=SECONDARY,
            button_color=SURFACE,
            button_hover_color=SURFACE_ALT,
            text_color=TEXT,
            command=self._on_base_settings_changed,
        )
        self.base_lock_switch.pack(side="left")
        self._create_help_badge(lock_wrap, "Nếu bật, khi gửi STOP app sẽ dùng lock=1 để firmware hãm hoặc giữ bánh thay vì thả trôi tự do.").pack(side="left", padx=(8, 0))

        preview_label = self._create_title_with_help(settings_card, "BASE Preview", "Đây là frame BASE chính xác được tạo từ lệnh hiện tại, tốc độ và trạng thái khóa bánh.", size=14)
        preview_label.grid(row=3, column=0, padx=16, pady=(2, 4), sticky="w")

        self.base_preview = ctk.CTkLabel(
            settings_card,
            textvariable=self.base_preview_var,
            corner_radius=14,
            fg_color=FRAME_PREVIEW,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
            anchor="w",
            padx=12,
            pady=8,
        )
        self.base_preview.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")

        self._create_feedback_banner(settings_card, self.base_feedback_var).grid(row=5, column=0, padx=16, pady=(0, 14), sticky="ew")

        base_log_card = self._create_card(page)
        base_log_card.grid(row=1, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        base_log_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            base_log_card,
            "Bridge Feedback Log",
            "ACK / ERR / EVENT / TRACE lines from STM32 stay visible here while driving the base.",
            "Khung này giúp bạn kiểm tra frame cuối cùng và trạng thái timeout mà không cần chuyển sang trang khác.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._register_bridge_log_box(base_log_card, row=1)

    def _build_motor_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure((0, 1), weight=1)

        header = self._create_card(page)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        self._create_section_header(
            header,
            f"{BRAND_LABEL} | STM32 Motor Bridge",
            "Edit each motor, then let STM32 keep forwarding the 4 motor packets every 20 ms.",
            "Dùng trang này để so sánh lệnh logic MOTOR,... với phản hồi TRACE,UART mà firmware trả về.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, padx=16, pady=14, sticky="e")

        ctk.CTkButton(actions, text="Send All", width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._activate_motor_stream).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(actions, text="Reset", width=90, fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT, command=self._reset_motor_cards).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(actions, text="Stop All", width=100, fg_color=DANGER, hover_color=DANGER_HOVER, command=self._send_bridge_stop).grid(row=0, column=2)

        for index in range(4):
            row = 1 + (index // 2)
            column = index % 2
            card = MotorCard(page, index + 1, self._on_motor_card_changed)
            card.grid(row=row, column=column, padx=(0 if column == 0 else 8), pady=(0, 10), sticky="nsew")
            self.motor_cards.append(card)

        preview_card = self._create_card(page)
        preview_card.grid(row=3, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        preview_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            preview_card,
            "Motor Frame + Trace",
            "Preview the outbound MOTOR frame and compare it against the last TRACE,UART line returned by STM32.",
            "Nếu có bánh nào chạy max tốc bất thường, hãy đối chiếu MOTOR preview với 4 gói UART 3 byte thực tế hiển thị ở đây.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._create_value_card(preview_card, "MOTOR Preview", self.motor_preview_var, 1, 0, tooltip_text="Đây là frame MOTOR chính xác mà app gửi tới STM32.")
        self._create_value_card(preview_card, "Last TRACE,UART", self.bridge_trace_var, 2, 0, tooltip_text="Đây là 4 gói UART 3 byte thực tế mà STM32 báo lại gần nhất.")
        self._create_feedback_banner(preview_card, self.motor_feedback_var).grid(row=3, column=0, padx=16, pady=(0, 14), sticky="ew")

        log_card = self._create_card(page)
        log_card.grid(row=4, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        log_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            log_card,
            "STM32 Bridge Log",
            "Detailed bridge telemetry stays here while motor streaming is active.",
            "ACK chỉ hiện khi trạng thái yêu cầu thực sự thay đổi để log không bị tràn khi stream mỗi 20 ms.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._register_bridge_log_box(log_card, row=1)

    def _build_direct_page(self, page: ctk.CTkScrollableFrame) -> None:
        page.grid_columnconfigure(0, weight=7)
        page.grid_columnconfigure(1, weight=5)

        link_card = self._create_card(page)
        link_card.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        link_card.grid_columnconfigure(0, weight=1)
        link_card.grid_columnconfigure(1, weight=0)

        self._create_section_header(
            link_card,
            f"{BRAND_LABEL} | Direct UART Driver",
            "Separate COM port path that bypasses STM32 and writes the 3-byte driver packet directly.",
            "Định dạng gói là: byte1=((dir&1)<<7)|(address&0x7F), byte2=speed, byte3=0xFF. Trong đó dir=1 là chạy thuận.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        direct_actions = ctk.CTkFrame(link_card, fg_color="transparent")
        direct_actions.grid(row=0, column=1, padx=16, pady=14, sticky="e")

        self.direct_port_combo = ctk.CTkComboBox(
            direct_actions,
            width=360,
            values=["No COM ports"],
            variable=self.direct_port_var,
            fg_color=FRAME_PREVIEW,
            border_color=OUTLINE,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SURFACE_ALT,
            dropdown_text_color=TEXT,
            text_color=TEXT,
        )
        self.direct_port_combo.grid(row=0, column=0, padx=(0, 8), pady=(0, 8))

        ctk.CTkButton(direct_actions, text="Refresh", width=76, height=34, fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT, command=self._refresh_direct_ports).grid(row=0, column=1, padx=(0, 8), pady=(0, 8))

        self.direct_baud_combo = ctk.CTkComboBox(
            direct_actions,
            width=98,
            values=DIRECT_BAUD_CHOICES,
            variable=self.direct_baud_var,
            fg_color=FRAME_PREVIEW,
            border_color=OUTLINE,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE,
            dropdown_hover_color=SURFACE_ALT,
            dropdown_text_color=TEXT,
            text_color=TEXT,
        )
        self.direct_baud_combo.grid(row=0, column=2, padx=(0, 8), pady=(0, 8))

        self.direct_connect_button = ctk.CTkButton(
            direct_actions,
            text="Connect",
            width=96,
            height=34,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._toggle_direct_connection,
        )
        self.direct_connect_button.grid(row=0, column=3, pady=(0, 8))

        self.direct_status_badge = ctk.CTkLabel(
            direct_actions,
            textvariable=self.direct_status_var,
            corner_radius=999,
            fg_color=FRAME_PREVIEW,
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            padx=12,
            pady=6,
        )
        self.direct_status_badge.grid(row=1, column=0, columnspan=4, sticky="ew")

        control_card = self._create_card(page)
        control_card.grid(row=1, column=0, padx=(0, 8), pady=(0, 10), sticky="nsew")
        control_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            control_card,
            "Driver Packet Builder",
            "Choose the address, direction, and speed byte, then send once, continuously, or for N seconds.",
            "Send Once gửi đúng 1 gói 3 byte. Hai chế độ Continuous và gửi theo thời gian sẽ lặp lại gói hiện tại theo chu kỳ đã chọn.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        fields = ctk.CTkFrame(control_card, fg_color="transparent")
        fields.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        fields.grid_columnconfigure((0, 1), weight=1)

        self._create_labeled_entry(fields, "Address (1..127)", self.direct_address_var, 0, 0, tooltip_text="Địa chỉ driver 7 bit sẽ được ghép vào byte1.")
        self._create_labeled_entry(fields, "Interval ms", self.direct_interval_var, 0, 1, tooltip_text="Khoảng thời gian giữa các gói khi gửi liên tục hoặc gửi theo thời lượng.")
        self._create_labeled_entry(fields, "Duration s", self.direct_duration_var, 1, 0, tooltip_text="Thời gian dùng cho chế độ Send For N Seconds.")

        dir_row = ctk.CTkFrame(fields, fg_color="transparent")
        dir_row.grid(row=1, column=1, padx=(8, 0), pady=(0, 14), sticky="ew")
        dir_row.grid_columnconfigure(0, weight=1)

        self._create_title_with_help(dir_row, "Direction", "dir=1 là quay thuận, dir=0 là quay nghịch.", size=13).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(dir_row, text="Tắt = nghịch, bật = thuận", text_color=MUTED, font=ctk.CTkFont(family="Segoe UI", size=11)).grid(row=1, column=0, sticky="w", pady=(2, 6))

        direct_dir_control = ctk.CTkFrame(dir_row, fg_color="transparent")
        direct_dir_control.grid(row=2, column=0, sticky="w")
        direct_dir_control.grid_columnconfigure(1, weight=1)

        self.direct_direction_switch = ctk.CTkSwitch(
            direct_dir_control,
            text="",
            variable=self.direct_direction_var,
            onvalue="1",
            offvalue="0",
            command=self._on_direct_direction_toggle,
            fg_color=SURFACE_ALT,
            progress_color=ACCENT,
            button_color=SURFACE,
            button_hover_color=SURFACE_ALT,
            border_width=0,
            width=48,
            height=24,
            switch_width=42,
            switch_height=20,
        )
        self.direct_direction_switch.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            direct_dir_control,
            textvariable=self.direct_direction_text_var,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12, weight="bold"),
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")

        self._create_slider_panel(
            control_card,
            row=2,
            title="Driver Speed",
            variable=self.direct_speed_var,
            accent=SECONDARY,
            hover=SECONDARY_HOVER,
            help_text="Giá trị tốc độ 0..255 sẽ được ghi trực tiếp vào byte2.",
            command=lambda: self._update_direct_preview(),
        )

        button_row = ctk.CTkFrame(control_card, fg_color="transparent")
        button_row.grid(row=3, column=0, padx=16, pady=(2, 14), sticky="ew")
        button_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkButton(button_row, text="Send Once", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._direct_send_once).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(button_row, text="Start Continuous", fg_color=SECONDARY, hover_color=SECONDARY_HOVER, command=self._start_direct_continuous).grid(row=0, column=1, padx=8, sticky="ew")
        ctk.CTkButton(button_row, text="Send For N Seconds", fg_color="#6c7ae0", hover_color="#5866ca", command=self._start_direct_timed).grid(row=0, column=2, padx=8, sticky="ew")
        ctk.CTkButton(button_row, text="Stop", fg_color=DANGER, hover_color=DANGER_HOVER, command=self._stop_direct_stream).grid(row=0, column=3, padx=(8, 0), sticky="ew")

        preview_card = self._create_card(page)
        preview_card.grid(row=1, column=1, padx=(8, 0), pady=(0, 10), sticky="nsew")
        preview_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            preview_card,
            "Direct Preview + Runtime",
            "Live packet preview and runtime counters for the current direct UART send mode.",
            "Khung hex bên dưới là gói 3 byte thật sẽ được gửi ra cổng COM của Direct UART.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._create_value_card(preview_card, "TX Frame Hex", self.direct_preview_var, 1, 0, tooltip_text="Ba byte của gói gửi được hiển thị ở dạng hex.")
        self._create_value_card(preview_card, "TX Frame Decimal", self.direct_decimal_var, 2, 0, tooltip_text="Ba byte của gói gửi được hiển thị ở dạng số thập phân.")
        self._create_value_card(preview_card, "Latest RX", self.direct_rx_var, 3, 0, tooltip_text="Dữ liệu RX thô nhận được từ cổng COM Direct UART nếu thiết bị có phản hồi.")

        runtime_grid = ctk.CTkFrame(preview_card, fg_color="transparent")
        runtime_grid.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")
        runtime_grid.grid_columnconfigure((0, 1, 2), weight=1)

        self._create_runtime_tile(runtime_grid, "TX Count", self.direct_tx_count_var, 0)
        self._create_runtime_tile(runtime_grid, "Elapsed", self.direct_elapsed_var, 1)
        self._create_runtime_tile(runtime_grid, "Remaining", self.direct_remaining_var, 2)

        self._create_feedback_banner(preview_card, self.direct_feedback_var).grid(row=5, column=0, padx=16, pady=(0, 14), sticky="ew")

        log_card = self._create_card(page)
        log_card.grid(row=2, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        log_card.grid_columnconfigure(0, weight=1)

        self._create_section_header(
            log_card,
            "Direct UART Console",
            "TX and RX activity for the direct USB-UART path is logged here.",
            "Trang này bỏ qua STM32 hoàn toàn, vì vậy bạn có thể dùng nó để so sánh phản ứng thô của driver với tab STM32 Bridge.",
        ).grid(row=0, column=0, padx=16, pady=(14, 10), sticky="ew")

        self._register_direct_log_box(log_card, row=1)

    def _create_card(self, master) -> ctk.CTkFrame:
        return ctk.CTkFrame(master, corner_radius=20, fg_color=SURFACE, border_width=1, border_color=OUTLINE)

    def _create_help_badge(self, master, tooltip_text: str) -> ctk.CTkLabel:
        badge = ctk.CTkLabel(
            master,
            text="?",
            width=20,
            height=20,
            corner_radius=999,
            fg_color=ACCENT_SOFT,
            text_color=ACCENT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=11, weight="bold"),
        )
        setattr(badge, "_tooltip", HoverTooltip(badge, tooltip_text))
        return badge

    def _create_title_with_help(self, master, text: str, tooltip_text: str, *, size: int = 19):
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        ctk.CTkLabel(
            wrapper,
            text=text,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=size, weight="bold"),
        ).pack(side="left")
        self._create_help_badge(wrapper, tooltip_text).pack(side="left", padx=(8, 0))
        return wrapper

    def _create_section_header(self, master, title: str, description: str, tooltip_text: str):
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid_columnconfigure(0, weight=1)
        self._create_title_with_help(wrapper, title, tooltip_text).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            wrapper,
            text=description,
            text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            justify="left",
            wraplength=880,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        return wrapper

    def _create_summary_chip(self, master, title: str, variable: tk.StringVar, bg: str, fg: str):
        frame = ctk.CTkFrame(master, corner_radius=16, fg_color=bg, border_width=0)
        ctk.CTkLabel(frame, text=title, text_color=MUTED if bg == FRAME_PREVIEW else fg, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold")).pack(anchor="w", padx=12, pady=(7, 0))
        ctk.CTkLabel(frame, textvariable=variable, text_color=fg, font=ctk.CTkFont(family="Segoe UI Semibold", size=12, weight="bold"), wraplength=150, justify="left").pack(anchor="w", padx=12, pady=(2, 8))
        return frame

    def _create_value_card(self, master, title: str, variable: tk.StringVar, row: int, column: int, *, tooltip_text: str) -> None:
        wrapper = ctk.CTkFrame(master, corner_radius=16, fg_color=FRAME_PREVIEW, border_width=1, border_color=OUTLINE)
        wrapper.grid(row=row, column=column, padx=16, pady=(0, 8), sticky="ew")
        wrapper.grid_columnconfigure(0, weight=1)

        self._create_title_with_help(wrapper, title, tooltip_text, size=12).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(
            wrapper,
            textvariable=variable,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="left",
            wraplength=960,
            anchor="w",
        ).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")

    def _create_feedback_banner(self, master, variable: tk.StringVar) -> ctk.CTkFrame:
        wrapper = ctk.CTkFrame(master, corner_radius=16, fg_color=ACCENT_SOFT, border_width=0)
        wrapper.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(wrapper, text="Feedback", text_color=ACCENT, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).grid(row=0, column=0, padx=12, pady=(8, 2), sticky="w")
        ctk.CTkLabel(wrapper, textvariable=variable, text_color=TEXT, font=ctk.CTkFont(family="Segoe UI Semibold", size=12, weight="bold"), wraplength=980, justify="left", anchor="w").grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        return wrapper

    def _create_slider_panel(self, master, *, row: int, title: str, variable: tk.IntVar, accent: str, hover: str, help_text: str, command) -> None:
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=row, column=0, padx=22, pady=(0, 12), sticky="ew")
        wrapper.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(wrapper, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        self._create_title_with_help(top, title, help_text, size=13).grid(row=0, column=0, sticky="w")
        value_label = ctk.CTkLabel(top, text=str(variable.get()), text_color=accent, font=ctk.CTkFont(family="Consolas", size=16, weight="bold"))
        value_label.grid(row=0, column=1, sticky="e")

        slider = ctk.CTkSlider(
            wrapper,
            from_=0,
            to=255,
            number_of_steps=255,
            progress_color=accent,
            button_color=accent,
            button_hover_color=hover,
            command=lambda value, var=variable, label=value_label: self._on_slider_change(value, var, label, command),
        )
        slider.set(variable.get())
        slider.grid(row=1, column=0, pady=(8, 0), sticky="ew")

    def _create_labeled_entry(self, master, label_text: str, variable: tk.StringVar, row: int, column: int, *, tooltip_text: str) -> None:
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=row, column=column, padx=(0 if column == 0 else 8, 8 if column == 0 else 0), pady=(0, 14), sticky="ew")
        wrapper.grid_columnconfigure(0, weight=1)

        self._create_title_with_help(wrapper, label_text, tooltip_text, size=13).grid(row=0, column=0, sticky="w")
        entry = ctk.CTkEntry(wrapper, textvariable=variable, fg_color=FRAME_PREVIEW, border_color=OUTLINE, text_color=TEXT, height=38)
        entry.grid(row=1, column=0, pady=(8, 0), sticky="ew")
        entry.bind("<KeyRelease>", lambda _event: self._update_direct_preview())

    def _create_runtime_tile(self, master, title: str, variable: tk.StringVar, column: int) -> None:
        tile = ctk.CTkFrame(master, corner_radius=18, fg_color=FRAME_PREVIEW, border_width=1, border_color=OUTLINE)
        tile.grid(row=0, column=column, padx=(0 if column == 0 else 6, 0 if column == 2 else 6), sticky="ew")
        ctk.CTkLabel(tile, text=title, text_color=MUTED, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(tile, textvariable=variable, text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=16, weight="bold")).pack(anchor="w", padx=14, pady=(0, 12))

    def _register_bridge_log_box(self, master, *, row: int) -> None:
        box = ctk.CTkTextbox(master, height=180, fg_color=LOG_BG, border_color=OUTLINE, border_width=1, text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=12))
        box.grid(row=row, column=0, padx=16, pady=(0, 14), sticky="ew")
        box.insert("end", "[bridge] waiting for telemetry...\n")
        box.configure(state="disabled")
        self.bridge_log_boxes.append(box)

    def _register_direct_log_box(self, master, *, row: int) -> None:
        box = ctk.CTkTextbox(master, height=200, fg_color=LOG_BG, border_color=OUTLINE, border_width=1, text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=12))
        box.grid(row=row, column=0, padx=16, pady=(0, 14), sticky="ew")
        box.insert("end", "[direct] waiting for TX / RX...\n")
        box.configure(state="disabled")
        self.direct_log_boxes.append(box)

    def _show_tab(self, name: str) -> None:
        self.active_tab = name
        self.hero_status_var.set(name)

        for tab_name, frame in self.page_frames.items():
            if tab_name == name:
                frame.grid()
            else:
                frame.grid_remove()

        for tab_name, button in self.tab_buttons.items():
            if tab_name == name:
                button.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white")
            else:
                button.configure(fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT)

        self._render_context_panel()

    def _render_context_panel(self) -> None:
        for child in self.context_panel.winfo_children():
            child.destroy()

        self.bridge_port_combo = None
        self.bridge_connect_button = None
        self.bridge_status_badge = None
        self.bridge_context_feedback_label = None

        if self.active_tab in (TAB_BASE, TAB_MOTOR):
            self.context_panel.grid()
            self.context_panel.grid_columnconfigure(0, weight=1)
            self._build_bridge_context_panel()
        else:
            self.context_panel.grid_remove()

    def _on_slider_change(self, value: float, variable: tk.IntVar, label: ctk.CTkLabel, callback) -> None:
        current = int(round(value))
        variable.set(current)
        label.configure(text=str(current))
        callback()

    def _format_port_label(self, port_info) -> str:
        device = getattr(port_info, "device", "") or ""
        description = getattr(port_info, "description", "") or ""
        manufacturer = getattr(port_info, "manufacturer", "") or ""
        product = getattr(port_info, "product", "") or ""
        vid = getattr(port_info, "vid", None)
        pid = getattr(port_info, "pid", None)

        details: list[str] = []
        main_desc = description if description and description.lower() != "n/a" else product
        if main_desc and main_desc != device:
            details.append(main_desc)
        if manufacturer and manufacturer.lower() != str(main_desc).lower():
            details.append(manufacturer)
        if vid is not None and pid is not None:
            details.append(f"VID:PID={vid:04X}:{pid:04X}")

        return f"{device} | {' | '.join(details)}" if details else device

    def _list_available_ports(self) -> list[tuple[str, str]]:
        try:
            entries = [(self._format_port_label(port), port.device) for port in list_ports.comports()]
            return sorted(entries, key=lambda item: item[1])
        except Exception:
            return []

    def _refresh_port_selector(
        self,
        combo: ctk.CTkComboBox | None,
        variable: tk.StringVar,
        lookup: dict[str, str],
        ports: list[tuple[str, str]],
        *,
        connected_port: str = "",
        preferred_port: str = "",
        preferred_text: str = "",
    ) -> None:
        lookup.clear()
        values: list[str] = []
        device_to_label: dict[str, str] = {}
        for label, device in ports:
            lookup[label] = device
            device_to_label[device] = label
            values.append(label)

        connected_label = ""
        if connected_port:
            connected_label = device_to_label.get(connected_port, f"{connected_port} | Đang kết nối")
            if connected_label not in values:
                values.insert(0, connected_label)
            lookup[connected_label] = connected_port

        preferred_label = ""
        if preferred_port:
            preferred_label = device_to_label.get(preferred_port, f"{preferred_port} | {preferred_text or 'Chờ kết nối lại'}")
            if preferred_label not in values:
                values.insert(0, preferred_label)
            lookup[preferred_label] = preferred_port

        display_values = values or ["No COM ports"]
        if combo is not None:
            combo.configure(values=display_values)

        current = variable.get().strip()
        current_device = self._resolve_port_selection(current, lookup)
        if connected_label:
            variable.set(connected_label)
        elif preferred_label and (not current_device or current_device == preferred_port):
            variable.set(preferred_label)
        elif current in lookup:
            return
        elif current_device in device_to_label:
            variable.set(device_to_label[current_device])
        elif values:
            variable.set(values[0])
        else:
            variable.set("No COM ports")

    def _resolve_port_selection(self, selection: str, lookup: dict[str, str]) -> str:
        current = str(selection).strip()
        if not current or current == "No COM ports":
            return ""
        if current in lookup:
            return lookup[current]
        if "|" in current:
            return current.split("|", 1)[0].strip()
        return current

    def _refresh_bridge_ports(self, ports: list[tuple[str, str]] | None = None) -> None:
        snapshot = self.bridge_transport.snapshot()
        connected_port = str(snapshot["port"]) if bool(snapshot["connected"]) else ""
        port_entries = ports if ports is not None else self._list_available_ports()
        self._refresh_port_selector(
            self.bridge_port_combo,
            self.bridge_port_var,
            self.bridge_port_lookup,
            port_entries,
            connected_port=connected_port,
            preferred_port=self.bridge_target_port if self.bridge_want_connection else "",
            preferred_text="Chờ cắm lại",
        )

    def _refresh_direct_ports(self, ports: list[tuple[str, str]] | None = None) -> None:
        snapshot = self.direct_transport.snapshot()
        connected_port = str(snapshot["port"]) if bool(snapshot["connected"]) else ""
        port_entries = ports if ports is not None else self._list_available_ports()
        self._refresh_port_selector(
            self.direct_port_combo,
            self.direct_port_var,
            self.direct_port_lookup,
            port_entries,
            connected_port=connected_port,
            preferred_port=self.direct_target_port if self.direct_want_connection else "",
            preferred_text="Chờ cắm lại",
        )

    def _auto_refresh_ports(self) -> None:
        try:
            if not self.winfo_exists():
                return
            ports = self._list_available_ports()
            self._refresh_bridge_ports(ports)
            self._refresh_direct_ports(ports)
            self._maybe_auto_reconnect_bridge(ports)
            self._maybe_auto_reconnect_direct(ports)
        finally:
            if self.winfo_exists():
                self.after(COM_AUTO_REFRESH_MS, self._auto_refresh_ports)

    def _toggle_bridge_connection(self) -> None:
        status = self.bridge_transport.snapshot()
        if bool(status["connected"]) or self.bridge_want_connection:
            self.bridge_want_connection = False
            self.bridge_target_port = ""
            self.bridge_target_baud = DEFAULT_BRIDGE_BAUD
            self.bridge_last_reconnect_attempt = 0.0
            self.bridge_transport.disconnect()
            return

        port = self._resolve_port_selection(self.bridge_port_var.get(), self.bridge_port_lookup)
        if not port or port == "No COM ports":
            self._set_bridge_feedback("Select a valid STM32 COM port first.")
            return

        self.bridge_want_connection = True
        self.bridge_target_port = port
        self.bridge_target_baud = DEFAULT_BRIDGE_BAUD
        self.bridge_last_reconnect_attempt = time.monotonic()
        self.bridge_status_var.set(f"Connecting {port}...")
        self.bridge_transport.connect(port, DEFAULT_BRIDGE_BAUD)

    def _toggle_direct_connection(self) -> None:
        status = self.direct_transport.snapshot()
        if bool(status["connected"]) or self.direct_want_connection:
            self.direct_want_connection = False
            self.direct_target_port = ""
            self.direct_target_baud = int(DEFAULT_DIRECT_BAUD)
            self.direct_last_reconnect_attempt = 0.0
            self.direct_transport.disconnect()
            return

        port = self._resolve_port_selection(self.direct_port_var.get(), self.direct_port_lookup)
        if not port or port == "No COM ports":
            self._set_direct_feedback("Select a valid direct UART COM port first.")
            return

        baudrate = self._parse_positive_int(self.direct_baud_var.get(), default=115200)
        self.direct_want_connection = True
        self.direct_target_port = port
        self.direct_target_baud = baudrate
        self.direct_last_reconnect_attempt = time.monotonic()
        self.direct_status_var.set(f"Connecting {port}...")
        self.direct_transport.connect(port, baudrate)

    def _maybe_auto_reconnect_bridge(self, ports: list[tuple[str, str]]) -> None:
        if not self.bridge_want_connection or not self.bridge_target_port:
            return
        status = self.bridge_transport.snapshot()
        if bool(status["connected"]):
            return
        available_ports = {device for _label, device in ports}
        if self.bridge_target_port not in available_ports:
            return
        now = time.monotonic()
        if now - self.bridge_last_reconnect_attempt < AUTO_RECONNECT_RETRY_S:
            return
        self.bridge_last_reconnect_attempt = now
        self.bridge_status_var.set(f"Đang kết nối lại {self.bridge_target_port}...")
        self._append_log_line(self.bridge_log_boxes, "bridge", f"Tự kết nối lại {self.bridge_target_port} @ {self.bridge_target_baud}")
        self.bridge_transport.connect(self.bridge_target_port, self.bridge_target_baud)

    def _maybe_auto_reconnect_direct(self, ports: list[tuple[str, str]]) -> None:
        if not self.direct_want_connection or not self.direct_target_port:
            return
        status = self.direct_transport.snapshot()
        if bool(status["connected"]):
            return
        available_ports = {device for _label, device in ports}
        if self.direct_target_port not in available_ports:
            return
        now = time.monotonic()
        if now - self.direct_last_reconnect_attempt < AUTO_RECONNECT_RETRY_S:
            return
        self.direct_last_reconnect_attempt = now
        self.direct_status_var.set(f"Đang kết nối lại {self.direct_target_port}...")
        self._append_log_line(self.direct_log_boxes, "direct", f"Tự kết nối lại {self.direct_target_port} @ {self.direct_target_baud}")
        self.direct_transport.connect(self.direct_target_port, self.direct_target_baud)

    def _append_log_line(self, boxes: list[ctk.CTkTextbox], channel: str, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{channel}] {message}\n"
        for box in boxes:
            box.configure(state="normal")
            box.insert("end", line)
            total_lines = int(box.index("end-1c").split(".")[0])
            if total_lines > 180:
                box.delete("1.0", f"{total_lines - 180}.0")
            box.see("end")
            box.configure(state="disabled")

    def _set_bridge_feedback(self, message: str) -> None:
        self.bridge_feedback_var.set(message)
        self.base_feedback_var.set(message)
        self.motor_feedback_var.set(message)

    def _set_direct_feedback(self, message: str) -> None:
        self.direct_feedback_var.set(message)

    def _bridge_write_line(self, frame: str) -> None:
        self.bridge_last_tx_var.set(frame)
        self.bridge_transport.write_line(frame)

    def _poll_transports(self) -> None:
        self._poll_bridge_transport()
        self._poll_direct_transport()
        self.after(120, self._poll_transports)

    def _poll_bridge_transport(self) -> None:
        status = self.bridge_transport.snapshot()
        connected = bool(status["connected"])
        error = str(status["error"])
        port = str(status["port"])

        if connected:
            self.bridge_status_var.set(f"{port} @ {status['baudrate']}")
            if self.bridge_status_badge is not None:
                self.bridge_status_badge.configure(fg_color=SUCCESS_SOFT, text_color=SUCCESS)
            if self.bridge_connect_button is not None:
                self.bridge_connect_button.configure(text="Disconnect", fg_color="#365f8c", hover_color="#27486d")
        elif self.bridge_want_connection and self.bridge_target_port:
            self.bridge_status_var.set(f"Chờ kết nối lại {self.bridge_target_port}")
            if self.bridge_status_badge is not None:
                self.bridge_status_badge.configure(fg_color=ACCENT_SOFT, text_color=ACCENT)
            if self.bridge_connect_button is not None:
                self.bridge_connect_button.configure(text="Cancel Auto", fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT)
        elif error:
            self.bridge_status_var.set("Bridge error")
            if self.bridge_status_badge is not None:
                self.bridge_status_badge.configure(fg_color=DANGER_SOFT, text_color=DANGER)
            if self.bridge_connect_button is not None:
                self.bridge_connect_button.configure(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER)
        else:
            self.bridge_status_var.set("Disconnected")
            if self.bridge_status_badge is not None:
                self.bridge_status_badge.configure(fg_color=FRAME_PREVIEW, text_color=MUTED)
            if self.bridge_connect_button is not None:
                self.bridge_connect_button.configure(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER)

        for kind, payload in self.bridge_transport.read_events():
            if kind == "status":
                self._append_log_line(self.bridge_log_boxes, "bridge", str(payload))
                self._set_bridge_feedback(str(payload))
                if str(payload) == "Disconnected":
                    self.bridge_last_rx_var.set("No RX yet")
                    self._cancel_bridge_streams(reset_command=True)
            elif kind == "error":
                message = str(payload)
                self._append_log_line(self.bridge_log_boxes, "bridge", f"ERROR {message}")
                if self.bridge_want_connection and self.bridge_target_port:
                    self._set_bridge_feedback(f"Mất kết nối {self.bridge_target_port}: {message}. Cắm lại cáp/UART để app tự kết nối lại.")
                else:
                    self._set_bridge_feedback(message)
                self._cancel_bridge_streams(reset_command=True)
            elif kind == "rx_line":
                line = str(payload).strip()
                self.bridge_last_rx_var.set(line)
                self._append_log_line(self.bridge_log_boxes, "bridge", f"RX {line}")
                self._handle_bridge_line(line)

    def _poll_direct_transport(self) -> None:
        status = self.direct_transport.snapshot()
        connected = bool(status["connected"])
        error = str(status["error"])
        port = str(status["port"])

        if connected:
            self.direct_status_var.set(f"{port} @ {status['baudrate']}")
            self.direct_status_badge.configure(fg_color=SUCCESS_SOFT, text_color=SUCCESS)
            self.direct_connect_button.configure(text="Disconnect", fg_color="#365f8c", hover_color="#27486d")
        elif self.direct_want_connection and self.direct_target_port:
            self.direct_status_var.set(f"Chờ kết nối lại {self.direct_target_port}")
            self.direct_status_badge.configure(fg_color=ACCENT_SOFT, text_color=ACCENT)
            self.direct_connect_button.configure(text="Cancel Auto", fg_color=SURFACE_ALT, hover_color=SURFACE_STRONG, text_color=TEXT)
        elif error:
            self.direct_status_var.set("Direct UART error")
            self.direct_status_badge.configure(fg_color=DANGER_SOFT, text_color=DANGER)
            self.direct_connect_button.configure(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER)
        else:
            self.direct_status_var.set("Disconnected")
            self.direct_status_badge.configure(fg_color=FRAME_PREVIEW, text_color=MUTED)
            self.direct_connect_button.configure(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER)

        for kind, payload in self.direct_transport.read_events():
            if kind == "status":
                self._append_log_line(self.direct_log_boxes, "direct", str(payload))
                self._set_direct_feedback(str(payload))
                if str(payload) == "Disconnected":
                    self._stop_direct_stream(log_reason=False)
            elif kind == "error":
                message = str(payload)
                self._append_log_line(self.direct_log_boxes, "direct", f"ERROR {message}")
                if self.direct_want_connection and self.direct_target_port:
                    self._set_direct_feedback(f"Mất kết nối {self.direct_target_port}: {message}. Cắm lại USB-UART để app tự kết nối lại.")
                else:
                    self._set_direct_feedback(message)
                self._stop_direct_stream(log_reason=False)
            elif kind == "rx_bytes":
                data = bytes(payload)
                if not data:
                    continue
                hex_text = " ".join(f"{value:02X}" for value in data)
                self.direct_rx_var.set(hex_text)
                self._append_log_line(self.direct_log_boxes, "direct", f"RX {hex_text}")

    def _handle_bridge_line(self, line: str) -> None:
        if line.startswith("ACK,"):
            self._set_bridge_feedback(f"ACK applied: {line[4:]}")
        elif line.startswith("ERR,"):
            self._set_bridge_feedback(f"Firmware error: {line[4:]}")
        elif line.startswith("EVENT,"):
            self._set_bridge_feedback(f"Bridge event: {line[6:]}")
        elif line.startswith("TRACE,UART,"):
            self.bridge_trace_var.set(line[11:])
            self._set_bridge_feedback("TRACE updated from STM32.")
        else:
            self._set_bridge_feedback(f"STM32 says: {line}")

    def _build_base_frame(self, command: str | None = None) -> str:
        return f"BASE,{command or self.active_base_command},{self.base_speed_var.get()},{self.lock_var.get()}"

    def _build_motor_frame(self) -> str:
        payload = ["MOTOR"]
        for card in self.motor_cards:
            direction, speed = card.get_values()
            payload.extend([str(direction), str(speed)])
        return ",".join(payload)

    def _update_base_preview(self) -> None:
        self.base_preview_var.set(self._build_base_frame())

    def _update_motor_preview(self) -> None:
        self.motor_preview_var.set(self._build_motor_frame())

    def _on_base_settings_changed(self) -> None:
        self._update_base_preview()
        if self.bridge_mode == "BASE" and self.active_base_command != "STOP":
            self._bridge_write_line(self._build_base_frame())

    def _create_command_button(self, master, command: str, text: str, row: int, column: int, color: str, hover: str) -> None:
        button = ctk.CTkButton(master, text=text, height=78, corner_radius=18, fg_color=color, hover_color=hover, text_color="white", font=ctk.CTkFont(family="Segoe UI Semibold", size=15, weight="bold"), command=lambda: None)
        button.grid(row=row, column=column, padx=8, pady=8, sticky="nsew")
        button.bind("<ButtonPress-1>", lambda _event, cmd=command: self._on_base_press(cmd))
        button.bind("<ButtonRelease-1>", lambda _event, cmd=command: self._on_base_release(cmd))
        self.command_buttons[command] = button

    def _create_stop_center(self, master, row: int, column: int) -> None:
        button = ctk.CTkButton(master, text="STOP", height=78, corner_radius=18, fg_color=DANGER, hover_color=DANGER_HOVER, text_color="white", font=ctk.CTkFont(family="Segoe UI Semibold", size=17, weight="bold"), command=self._send_bridge_stop)
        button.grid(row=row, column=column, padx=8, pady=8, sticky="nsew")

    def _update_base_button_states(self) -> None:
        for command, button in self.command_buttons.items():
            if command == self.active_base_command and self.bridge_mode == "BASE":
                button.configure(border_width=2, border_color=TEXT)
            else:
                button.configure(border_width=0, border_color=OUTLINE)

    def _on_base_press(self, command: str) -> None:
        self.focus_force()
        self.bridge_mode = "BASE"
        self.active_base_command = command
        self._update_base_button_states()
        frame = self._build_base_frame(command)
        self._update_base_preview()
        self._set_bridge_feedback(f"Base hold active: {frame}")
        if bool(self.bridge_transport.snapshot()["connected"]):
            self._bridge_write_line(frame)

    def _on_base_release(self, command: str) -> None:
        if self.active_base_command == command and not self.active_keys:
            self.active_base_command = "STOP"
            self._update_base_button_states()
            self._update_base_preview()
            self._send_bridge_stop(update_feedback=False)

    def _resolve_key_command(self) -> str:
        vertical = ""
        horizontal = ""

        for key in self.active_keys:
            if key in ("w", "s"):
                vertical = key
            elif key in ("a", "d"):
                horizontal = key

        if vertical == "w" and horizontal == "a":
            return "FWD_LEFT"
        if vertical == "w" and horizontal == "d":
            return "FWD_RIGHT"
        if vertical == "s" and horizontal == "a":
            return "BACK_LEFT"
        if vertical == "s" and horizontal == "d":
            return "BACK_RIGHT"
        if vertical == "w":
            return "FWD"
        if vertical == "s":
            return "BACK"
        if horizontal == "a":
            return "LEFT"
        if horizontal == "d":
            return "RIGHT"
        return "STOP"

    def _on_key_press(self, event) -> None:
        if self.active_tab != TAB_BASE:
            return
        key = event.keysym.lower()
        if key not in KEY_COMMANDS:
            return
        if key not in self.active_keys:
            self.active_keys.append(key)
        self._sync_key_command()

    def _on_key_release(self, event) -> None:
        key = event.keysym.lower()
        if key in self.active_keys:
            self.active_keys.remove(key)
        self._sync_key_command()

    def _sync_key_command(self) -> None:
        if self.active_keys:
            command = self._resolve_key_command()
            self.bridge_mode = "BASE"
            self.active_base_command = command
            self._update_base_button_states()
            frame = self._build_base_frame(command)
            self._update_base_preview()
            self._set_bridge_feedback(f"Keyboard command active: {frame}")
            if bool(self.bridge_transport.snapshot()["connected"]):
                self._bridge_write_line(frame)
        else:
            self.active_base_command = "STOP"
            self._update_base_button_states()
            self._update_base_preview()
            self._send_bridge_stop(update_feedback=False)

    def _bridge_heartbeat(self) -> None:
        connected = bool(self.bridge_transport.snapshot()["connected"])
        if connected:
            if self.bridge_mode == "BASE" and self.active_base_command != "STOP":
                self._bridge_write_line(self._build_base_frame())
            elif self.bridge_mode == "MOTOR":
                self._bridge_write_line(self._build_motor_frame())
        self.after(BRIDGE_STREAM_MS, self._bridge_heartbeat)

    def _cancel_bridge_streams(self, *, reset_command: bool) -> None:
        self.bridge_mode = "IDLE"
        if reset_command:
            self.active_base_command = "STOP"
        self._update_base_button_states()
        self._update_base_preview()

    def _send_bridge_stop(self, *, update_feedback: bool = True) -> None:
        self._cancel_bridge_streams(reset_command=True)
        if bool(self.bridge_transport.snapshot()["connected"]):
            self._bridge_write_line("STOP")
        self.bridge_last_tx_var.set("STOP")
        if update_feedback:
            self._set_bridge_feedback("Emergency STOP sent to STM32 bridge.")

    def _activate_motor_stream(self) -> None:
        self.bridge_mode = "MOTOR"
        frame = self._build_motor_frame()
        self._update_motor_preview()
        self._set_bridge_feedback("STM32 motor bridge streaming active.")
        self.motor_feedback_var.set(f"Streaming via STM32: {frame}")
        if bool(self.bridge_transport.snapshot()["connected"]):
            self._bridge_write_line(frame)

    def _reset_motor_cards(self) -> None:
        for card in self.motor_cards:
            card.set_values(0, 0)
        self._update_motor_preview()
        self.motor_feedback_var.set("Motor cards reset to 0,0.")
        if self.bridge_mode == "MOTOR" and bool(self.bridge_transport.snapshot()["connected"]):
            self._bridge_write_line(self._build_motor_frame())

    def _on_motor_card_changed(self) -> None:
        self._update_motor_preview()
        if self.bridge_mode == "MOTOR":
            self.motor_feedback_var.set("Motor frame updated while streaming.")
            if bool(self.bridge_transport.snapshot()["connected"]):
                self._bridge_write_line(self._build_motor_frame())

    def _parse_positive_int(self, raw: str, *, default: int, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return default
        if value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value

    def _parse_positive_float(self, raw: str, *, default: float, minimum: float = 0.1) -> float:
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            return default
        if value < minimum:
            return minimum
        return value

    def _on_direct_direction_toggle(self) -> None:
        self.direct_direction_text_var.set("Thuận" if self.direct_direction_var.get() == "1" else "Nghịch")
        self._update_direct_preview()

    def _build_direct_packet(self) -> tuple[bytes, str, str]:
        address = self._parse_positive_int(self.direct_address_var.get(), default=1, minimum=1, maximum=127)
        direction = 1 if self.direct_direction_var.get() == "1" else 0
        speed = max(0, min(255, int(self.direct_speed_var.get())))
        byte1 = ((direction & 0x01) << 7) | (address & 0x7F)
        packet = bytes((byte1, speed, 0xFF))
        return packet, " ".join(f"{value:02X}" for value in packet), ", ".join(str(value) for value in packet)

    def _update_direct_preview(self) -> None:
        _packet, hex_text, decimal_text = self._build_direct_packet()
        self.direct_preview_var.set(hex_text)
        self.direct_decimal_var.set(decimal_text)

    def _send_direct_packet(self, *, reason: str) -> bool:
        if not bool(self.direct_transport.snapshot()["connected"]):
            self._set_direct_feedback("Direct UART is not connected.")
            return False

        packet, hex_text, decimal_text = self._build_direct_packet()
        self.direct_transport.write_bytes(packet)
        self.direct_tx_count += 1
        self.direct_tx_count_var.set(str(self.direct_tx_count))
        self.direct_preview_var.set(hex_text)
        self.direct_decimal_var.set(decimal_text)
        self._append_log_line(self.direct_log_boxes, "direct", f"TX {reason} {hex_text} ({decimal_text})")
        self._set_direct_feedback(f"Sent {reason}: {hex_text}")
        return True

    def _direct_send_once(self) -> None:
        self._update_direct_preview()
        self._send_direct_packet(reason="once")

    def _start_direct_continuous(self) -> None:
        self._stop_direct_stream(log_reason=False)
        interval_ms = self._parse_positive_int(self.direct_interval_var.get(), default=DEFAULT_DIRECT_INTERVAL_MS, minimum=1)
        self.direct_stream_mode = "CONTINUOUS"
        self.direct_stream_started = time.monotonic()
        self.direct_stream_ends_at = 0.0
        self._set_direct_feedback(f"Continuous direct UART sending every {interval_ms} ms.")
        self._append_log_line(self.direct_log_boxes, "direct", f"CONTINUOUS start interval={interval_ms} ms")
        self._direct_stream_tick()

    def _start_direct_timed(self) -> None:
        self._stop_direct_stream(log_reason=False)
        interval_ms = self._parse_positive_int(self.direct_interval_var.get(), default=DEFAULT_DIRECT_INTERVAL_MS, minimum=1)
        duration_s = self._parse_positive_float(self.direct_duration_var.get(), default=3.0, minimum=0.1)
        self.direct_stream_mode = "TIMED"
        self.direct_stream_started = time.monotonic()
        self.direct_stream_ends_at = self.direct_stream_started + duration_s
        self._set_direct_feedback(f"Timed direct UART sending for {duration_s:.1f} s every {interval_ms} ms.")
        self._append_log_line(self.direct_log_boxes, "direct", f"TIMED start duration={duration_s:.1f} s interval={interval_ms} ms")
        self._direct_stream_tick()

    def _stop_direct_stream(self, *, log_reason: bool = True) -> None:
        if self.direct_stream_job is not None:
            self.after_cancel(self.direct_stream_job)
            self.direct_stream_job = None
        if self.direct_stream_mode != "IDLE" and log_reason:
            self._append_log_line(self.direct_log_boxes, "direct", f"{self.direct_stream_mode} stop")
            self._set_direct_feedback("Direct UART streaming stopped.")
        self.direct_stream_mode = "IDLE"
        self.direct_stream_started = 0.0
        self.direct_stream_ends_at = 0.0
        self.direct_elapsed_var.set("0.0 s")
        self.direct_remaining_var.set("0.0 s")

    def _direct_stream_tick(self) -> None:
        self.direct_stream_job = None
        if self.direct_stream_mode == "IDLE":
            return

        interval_ms = self._parse_positive_int(self.direct_interval_var.get(), default=DEFAULT_DIRECT_INTERVAL_MS, minimum=1)
        if not self._send_direct_packet(reason=self.direct_stream_mode.lower()):
            self._stop_direct_stream(log_reason=False)
            return

        if self.direct_stream_mode == "TIMED":
            if time.monotonic() >= self.direct_stream_ends_at:
                self._set_direct_feedback("Timed direct UART send completed.")
                self._append_log_line(self.direct_log_boxes, "direct", "TIMED completed")
                self._stop_direct_stream(log_reason=False)
                return

        self.direct_stream_job = self.after(interval_ms, self._direct_stream_tick)

    def _direct_runtime_heartbeat(self) -> None:
        if self.direct_stream_mode == "IDLE":
            self.direct_elapsed_var.set("0.0 s")
            self.direct_remaining_var.set("0.0 s")
        else:
            now = time.monotonic()
            elapsed = max(0.0, now - self.direct_stream_started)
            self.direct_elapsed_var.set(f"{elapsed:.1f} s")
            if self.direct_stream_mode == "TIMED":
                remaining = max(0.0, self.direct_stream_ends_at - now)
                self.direct_remaining_var.set(f"{remaining:.1f} s")
                if remaining <= 0.0:
                    self._stop_direct_stream(log_reason=False)
            else:
                self.direct_remaining_var.set("continuous")
        self.after(120, self._direct_runtime_heartbeat)

    def _on_close(self) -> None:
        try:
            self._send_bridge_stop(update_feedback=False)
            self._stop_direct_stream(log_reason=False)
            self.bridge_transport.disconnect()
            self.direct_transport.disconnect()
        finally:
            self.bridge_transport.close()
            self.direct_transport.close()
            self.destroy()


def main() -> None:
    app = ControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
    
