#!/usr/bin/env python3
"""Modernised GUI application to control the articulated robot arm."""

from __future__ import annotations

import json
import os
import queue
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover - optional dependency
    serial = None  # type: ignore

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    ImageTk = None  # type: ignore


# =============================================================================
# Styling helpers
# =============================================================================

@dataclass(frozen=True)
class Palette:
    """Centralised colour palette for the dark themed interface."""

    background: str = "#10131a"
    surface: str = "#181d29"
    surface_alt: str = "#1f2533"
    accent: str = "#5c7cfa"
    accent_hover: str = "#748ffc"
    success: str = "#51cf66"
    warning: str = "#fab005"
    text: str = "#f8f9fa"
    text_muted: str = "#adb5bd"


class DarkTheme:
    """Apply a consistent dark theme to ttk widgets."""

    def __init__(self, root: tk.Tk, palette: Palette | None = None) -> None:
        self.palette = palette or Palette()
        self._style = ttk.Style(root)
        self._apply()

    def _apply(self) -> None:
        palette = self.palette
        style = self._style

        style.theme_use("clam")
        style.configure("TFrame", background=palette.background)
        style.configure("Card.TFrame", background=palette.surface, relief="flat")
        style.configure("Accent.TFrame", background=palette.surface_alt, relief="flat")

        style.configure(
            "TLabel",
            background=palette.background,
            foreground=palette.text,
        )
        style.configure(
            "Heading.TLabel",
            font=("Segoe UI", 10, "bold"),
            background=palette.background,
            foreground=palette.text,
        )
        style.configure(
            "Muted.TLabel",
            background=palette.background,
            foreground=palette.text_muted,
        )

        style.configure(
            "TButton",
            background=palette.surface_alt,
            foreground=palette.text,
            borderwidth=0,
            focuscolor=palette.accent,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", palette.accent_hover), ("pressed", palette.accent)],
            foreground=[("disabled", palette.text_muted)],
        )

        style.configure(
            "Accent.TButton",
            background=palette.accent,
            foreground=palette.background,
            padding=(10, 6),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", palette.accent_hover), ("pressed", palette.accent)],
        )

        style.configure(
            "Toggle.TButton",
            background=palette.surface,
            foreground=palette.text,
            padding=(6, 3),
        )

        entry_fields = {
            "foreground": palette.text,
            "fieldbackground": palette.surface,
            "background": palette.surface,
            "insertcolor": palette.text,
            "bordercolor": palette.surface_alt,
            "lightcolor": palette.surface_alt,
        }
        for widget in ("TEntry", "TCombobox", "Spinbox", "TSpinbox"):
            style.configure(widget, **entry_fields)

        style.configure(
            "Horizontal.TScale",
            background=palette.background,
            troughcolor=palette.surface,
            sliderlength=18,
        )

        style.configure(
            "Dark.Treeview",
            background=palette.surface,
            fieldbackground=palette.surface,
            foreground=palette.text,
            borderwidth=0,
            rowheight=26,
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=palette.surface_alt,
            foreground=palette.text,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", palette.accent)],
            foreground=[("selected", palette.background)],
        )

        style.configure(
            "Card.TLabelframe",
            background=palette.surface,
            foreground=palette.text,
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 10, "bold"),
        )

        style.configure("Status.TLabel", background=palette.surface_alt, foreground=palette.text_muted)


# =============================================================================
# Serial manager
# =============================================================================


class SerialManager:
    """Minimal abstraction for asynchronous serial communications."""

    def __init__(self, on_line_callback: Optional[Callable[[str], None]] = None) -> None:
        self.ser: Optional[serial.Serial] = None  # type: ignore[attr-defined]
        self.on_line_callback = on_line_callback
        self.read_queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.buffer = ""

    def list_ports(self) -> List[str]:
        if not serial:  # pragma: no cover - optional dependency
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def open(self, port: str, baud: int = 115200) -> None:
        if not serial:  # pragma: no cover - optional dependency
            raise RuntimeError("pyserial n'est pas installé")
        self.close()
        self.ser = serial.Serial(port, baudrate=baud, timeout=0.05)  # type: ignore[attr-defined]
        self.running = True

    def close(self) -> None:
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def send_line(self, line: str) -> None:
        if not self.ser:
            return
        if not line.endswith("\n"):
            line += "\n"
        try:
            self.ser.write(line.encode("utf-8"))
        except Exception:
            pass

    def poll(self) -> None:
        if self.ser and self.running:
            try:
                data = self.ser.read(1024)
                if data:
                    self.buffer += data.decode("utf-8", errors="ignore")
                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        line = line.strip()
                        if self.on_line_callback:
                            self.on_line_callback(line)
            except Exception:
                pass


# =============================================================================
# Timeline handling
# =============================================================================


class TimelineManager:
    def __init__(self) -> None:
        self.steps: List[Dict[str, object]] = []
        self.loop_count = 1

    def add_step(self, step: Dict[str, object]) -> None:
        self.steps.append(step)

    def clear(self) -> None:
        self.steps.clear()

    def to_json(self) -> str:
        return json.dumps(self.steps, indent=2)

    def from_json_str(self, data: str) -> None:
        self.steps = json.loads(data)

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.steps, handle, indent=2)

    def load_from_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as handle:
            self.steps = json.load(handle)


# =============================================================================
# Arm control logic
# =============================================================================


class ArmController:
    def __init__(self, serial_mgr: SerialManager, log_callback: Optional[Callable[[str], None]] = None) -> None:
        self.serial = serial_mgr
        self.log = log_callback or (lambda msg: None)
        self.playing = False
        self.current_sequence: List[Dict[str, object]] = []
        self.current_step_idx = 0
        self.waiting_for_ok = False
        self.rest_angle = 90
        self.on_sequence_finished: Optional[Callable[[], None]] = None
        self.loop_total = 1
        self.loop_remaining = 1

    def send(self, line: str) -> None:
        self.log(f">> {line}")
        self.serial.send_line(line)

    def play_sequence(self, steps: List[Dict[str, object]], loops: int = 1, on_finished: Optional[Callable[[], None]] = None) -> None:
        if not steps:
            return
        self.playing = True
        self.current_sequence = steps
        self.current_step_idx = 0
        self.waiting_for_ok = False
        self.loop_total = max(1, loops)
        self.loop_remaining = self.loop_total
        self.on_sequence_finished = on_finished
        self.log(f"--- Lancement séquence ({len(steps)} pas, boucles={self.loop_total}) ---")
        self._play_next_step()

    def _play_next_step(self) -> None:
        if not self.playing:
            return
        if self.current_step_idx >= len(self.current_sequence):
            self.loop_remaining -= 1
            if self.loop_remaining > 0:
                self.log(f"--- Boucles restantes: {self.loop_remaining} ---")
                self.current_step_idx = 0
            else:
                self.log("--- Séquence terminée ---")
                self.playing = False
                if self.on_sequence_finished:
                    self.on_sequence_finished()
                self.goto_rest()
                return

        step = self.current_sequence[self.current_step_idx]
        self.current_step_idx += 1
        self.log(f"Pas {self.current_step_idx}/{len(self.current_sequence)}: {step.get('name', '')}")

        s0 = step.get("servo0", self.rest_angle)
        s1 = step.get("servo1", self.rest_angle)
        s2 = step.get("servo2", self.rest_angle)
        speed = step.get("speed", 60)
        pause = step.get("pause", 0)
        nano_cmd = str(step.get("nano_cmd", "")).strip()

        self.send("M279")
        self.send(f"M280 P0 S{s0} V{speed}")
        self.send(f"M280 P1 S{s1} V{speed}")
        self.send(f"M280 P2 S{s2} V{speed}")
        self.send("M278")

        if pause and isinstance(pause, (int, float)) and pause > 0:
            self.send(f"G4 P{int(pause)}")

        if nano_cmd:
            self.send(nano_cmd)

        self.send("M400")
        self.waiting_for_ok = True

    def on_serial_line(self, line: str) -> None:
        if self.playing and self.waiting_for_ok and line.lower().endswith("ok"):
            self.waiting_for_ok = False
            self._play_next_step()

    def stop_sequence(self) -> None:
        if not self.playing:
            self.send("M901")
            self.goto_rest()
            return
        self.log("--- Arrêt de la séquence demandé ---")
        self.playing = False
        self.waiting_for_ok = False
        self.send("M901")
        self.goto_rest()

    def goto_rest(self) -> None:
        self.log("--- Retour position repos ---")
        self.send("M279")
        self.send(f"M280 P0 S{self.rest_angle} V60")
        self.send(f"M280 P1 S{self.rest_angle} V60")
        self.send(f"M280 P2 S{self.rest_angle} V60")
        self.send("M278")
        self.send("M400")


# =============================================================================
# SD manager window
# =============================================================================


class SdManagerWindow(tk.Toplevel):
    def __init__(self, master: tk.Widget, serial_mgr: SerialManager, log_callback: Callable[[str], None], palette: Palette) -> None:
        super().__init__(master)
        self.title("Gestion SD / Téléversement")
        self.serial = serial_mgr
        self.log = log_callback
        self.palette = palette
        self.file_list: List[Dict[str, str]] = []
        self.configure(bg=self.palette.background)
        DarkTheme(self)  # ensure nested windows inherit styling
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.transient(master)
        self._build_ui()

    def _on_close(self) -> None:
        """Release references on close to avoid stale windows."""
        if isinstance(self.master, MainWindow):
            self.master.sd_window = None  # type: ignore[assignment]
        self.destroy()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        button_bar = ttk.Frame(self, padding=10, style="Accent.TFrame")
        button_bar.grid(row=0, column=0, sticky="ew")
        for idx in range(4):
            button_bar.columnconfigure(idx, weight=1)

        ttk.Button(button_bar, text="Monter SD (M21)", command=self.cmd_mount).grid(row=0, column=0, padx=6, pady=4, sticky="ew")
        ttk.Button(button_bar, text="Rafraîchir (M20)", command=self.cmd_list).grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        ttk.Button(button_bar, text="Téléverser fichier", command=self.cmd_upload).grid(row=0, column=2, padx=6, pady=4, sticky="ew")
        ttk.Button(button_bar, text="Supprimer (M30)", command=self.cmd_delete).grid(row=0, column=3, padx=6, pady=4, sticky="ew")

        columns = ("name", "size")
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            style="Dark.Treeview",
            selectmode="browse",
        )
        self.tree.heading("name", text="Nom")
        self.tree.heading("size", text="Taille")
        self.tree.column("name", width=220, stretch=True)
        self.tree.column("size", width=80, anchor="e")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=10)

        info_frame = ttk.Frame(self, padding=10, style="Card.TFrame")
        info_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        info_frame.columnconfigure(0, weight=1)

        self.sd_info = tk.Text(
            info_frame,
            height=6,
            bg=self.palette.surface,
            fg=self.palette.text,
            insertbackground=self.palette.text,
            relief="flat",
            wrap="word",
        )
        self.sd_info.grid(row=0, column=0, sticky="ew")
        self.sd_info.insert("end", "Infos SD / logs...\n")
        self.sd_info.configure(state="disabled")

    def append_info(self, text: str) -> None:
        self.sd_info.configure(state="normal")
        self.sd_info.insert("end", text + "\n")
        self.sd_info.see("end")
        self.sd_info.configure(state="disabled")

    def send(self, line: str) -> None:
        self.log(f">> {line}")
        self.serial.send_line(line)

    def cmd_mount(self) -> None:
        self.send("M21")
        self.append_info("M21 envoyé (montage SD)")

    def cmd_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.file_list.clear()
        self.send("M20")
        self.append_info("M20 envoyé (liste fichiers)")

    def cmd_upload(self) -> None:
        path = filedialog.askopenfilename(title="Choisir un fichier à téléverser")
        if not path:
            return
        filename = os.path.basename(path)
        self.append_info(f"Téléversement de {filename} ...")
        self.send(f"M28 {filename}")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    self.send(line.rstrip("\r\n"))
        except Exception as exc:  # pragma: no cover - file interaction
            self.append_info(f"Erreur lecture fichier: {exc}")
        self.send("M29")
        self.append_info(f"{filename} envoyé (M28/M29). Utiliser M20 pour rafraîchir.")

    def cmd_delete(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        filename = self.tree.item(iid, "values")[0]
        self.send(f"M30 {filename}")
        self.append_info(f"Demande suppression M30 {filename}")

    def on_sd_line(self, line: str) -> None:
        if line.startswith("Begin file list") or line.startswith("End file list"):
            self.append_info(line)
            return
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            size = parts[1]
            self.tree.insert("", "end", values=(name, size))
            self.file_list.append({"name": name, "size": size})
            self.append_info(line)


# =============================================================================
# Main window
# =============================================================================


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Contrôle bras robotique")
        self.geometry("1250x760")
        self.minsize(1100, 680)
        self.palette = Palette()
        self.configure(bg=self.palette.background)
        self.theme = DarkTheme(self, self.palette)

        self.serial_mgr = SerialManager(on_line_callback=self.on_serial_line)
        self.timeline = TimelineManager()
        self.arm = ArmController(self.serial_mgr, log_callback=self.append_console)
        self.sd_window: Optional[SdManagerWindow] = None
        self.background_image: Optional[ImageTk.PhotoImage] = None  # type: ignore[assignment]

        self._build_ui()
        self._setup_serial_ui()
        self.after(50, self._poll_serial)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI ---

    def _build_ui(self) -> None:
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))

        left = ttk.Frame(paned, padding=10, style="Card.TFrame")
        center = ttk.Frame(paned, padding=10, style="Card.TFrame")
        right = ttk.Frame(paned, padding=10, style="Card.TFrame")
        paned.add(left, weight=1)
        paned.add(center, weight=1)
        paned.add(right, weight=1)

        self._build_left(left)
        self._build_center(center)
        self._build_right(right)
        self._build_bottom()

    def _build_left(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        image_frame = ttk.Frame(parent, style="Accent.TFrame")
        image_frame.grid(row=0, column=0, sticky="nsew")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)

        self.background_label = ttk.Label(image_frame, anchor="center")
        self.background_label.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.load_background_image()

        control_section = ttk.LabelFrame(parent, text="Contrôles locaux", style="Card.TLabelframe")
        control_section.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        # Arrow buttons
        arrow_frame = ttk.Frame(control_section, style="Card.TFrame")
        arrow_frame.grid(row=0, column=0, padx=6, pady=6)
        button_opts = {
            "width": 4,
            "style": "Toggle.TButton",
        }
        ttk.Button(arrow_frame, text="▲", command=lambda: self.send_nano_move(+10), **button_opts).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(arrow_frame, text="▼", command=lambda: self.send_nano_move(-10), **button_opts).grid(row=2, column=1, padx=2, pady=2)
        ttk.Button(arrow_frame, text="◀", command=lambda: self.send_nano_move(-10, axis="x"), **button_opts).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(arrow_frame, text="▶", command=lambda: self.send_nano_move(+10, axis="x"), **button_opts).grid(row=1, column=2, padx=2, pady=2)

        # Delta controls
        inc_frame = ttk.Frame(control_section, style="Card.TFrame")
        inc_frame.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 8))
        ttk.Label(inc_frame, text="ΔX:", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.delta_x = tk.IntVar(value=10)
        ttk.Button(inc_frame, text="-10", command=lambda: self.set_delta(-10), style="Toggle.TButton").grid(row=0, column=1, padx=2)
        ttk.Button(inc_frame, text="-1", command=lambda: self.set_delta(-1), style="Toggle.TButton").grid(row=0, column=2, padx=2)
        ttk.Button(inc_frame, text="+1", command=lambda: self.set_delta(1), style="Toggle.TButton").grid(row=0, column=3, padx=2)
        ttk.Button(inc_frame, text="+10", command=lambda: self.set_delta(10), style="Toggle.TButton").grid(row=0, column=4, padx=2)
        ttk.Label(inc_frame, textvariable=self.delta_x, style="Heading.TLabel").grid(row=0, column=5, padx=(8, 0))

        servo_frame = ttk.LabelFrame(control_section, text="Servos", style="Card.TLabelframe")
        servo_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        servo_frame.columnconfigure(1, weight=1)

        self.servo_vars = [tk.IntVar(value=90) for _ in range(3)]
        for idx in range(3):
            ttk.Label(servo_frame, text=f"S{idx}", style="Muted.TLabel").grid(row=idx, column=0, sticky="e", padx=4, pady=4)
            scale = ttk.Scale(
                servo_frame,
                from_=0,
                to=180,
                orient="horizontal",
                variable=self.servo_vars[idx],
                style="Horizontal.TScale",
            )
            scale.grid(row=idx, column=1, sticky="ew", padx=6)

        self.speed_var = tk.IntVar(value=60)
        ttk.Label(servo_frame, text="Vitesse °/s", style="Muted.TLabel").grid(row=3, column=0, sticky="e", padx=4, pady=4)
        ttk.Scale(
            servo_frame,
            from_=1,
            to=200,
            orient="horizontal",
            variable=self.speed_var,
            style="Horizontal.TScale",
        ).grid(row=3, column=1, sticky="ew", padx=6)

        ttk.Button(servo_frame, text="Envoyer position", command=self.send_current_servo_pos, style="Accent.TButton").grid(row=4, column=0, columnspan=2, pady=(10, 4))

    def _build_center(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Console", style="Heading.TLabel").grid(row=0, column=0, sticky="w")

        self.console = tk.Text(
            parent,
            wrap="word",
            bg=self.palette.surface,
            fg=self.palette.text,
            insertbackground=self.palette.text,
            relief="flat",
        )
        self.console.grid(row=1, column=0, sticky="nsew", pady=(6, 10))
        self.console.insert("end", "Console prête.\n")
        self.console.configure(state="disabled")

        entry_frame = ttk.Frame(parent, style="Card.TFrame")
        entry_frame.grid(row=2, column=0, sticky="ew")
        entry_frame.columnconfigure(0, weight=1)

        self.console_entry = ttk.Entry(entry_frame)
        self.console_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)
        self.console_entry.bind("<Return>", self.on_console_enter)
        ttk.Button(entry_frame, text="Envoyer", command=self.send_console_line, style="Accent.TButton").grid(row=0, column=1, pady=4)

    def _build_right(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(parent, text="Timeline / Carrousel", style="Heading.TLabel").grid(row=0, column=0, sticky="w")

        columns = ("name", "s0", "s1", "s2", "pause", "nano")
        self.timeline_tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            style="Dark.Treeview",
            selectmode="browse",
        )
        headings = {
            "name": "Nom",
            "s0": "S0",
            "s1": "S1",
            "s2": "S2",
            "pause": "Pause",
            "nano": "Cmd Nano",
        }
        for key, label in headings.items():
            self.timeline_tree.heading(key, text=label)
            anchor = "w" if key in {"name", "nano"} else "center"
            self.timeline_tree.column(key, anchor=anchor, stretch=True, width=80)
        self.timeline_tree.grid(row=1, column=0, sticky="nsew", pady=6)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.timeline_tree.yview)
        self.timeline_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns")

        self.timeline_tree.bind("<Button-3>", self.on_timeline_right_click)

        btn_frame = ttk.Frame(parent, style="Card.TFrame")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for idx in range(3):
            btn_frame.columnconfigure(idx, weight=1)
        ttk.Button(btn_frame, text="Ajouter", command=self.add_step_dialog, style="Accent.TButton").grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(btn_frame, text="Charger", command=self.load_sequence).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(btn_frame, text="Sauvegarder", command=self.save_sequence).grid(row=0, column=2, padx=4, sticky="ew")

    def _build_bottom(self) -> None:
        bottom = ttk.Frame(self, padding=(12, 0, 12, 12), style="Accent.TFrame")
        bottom.pack(fill=tk.X)
        for idx in range(6):
            bottom.columnconfigure(idx, weight=1)

        ttk.Button(bottom, text="Play", command=self.play_sequence, style="Accent.TButton").grid(row=0, column=0, padx=6, pady=10, sticky="ew")
        ttk.Button(bottom, text="Stop", command=self.stop_sequence).grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        ttk.Button(bottom, text="Clear", command=self.clear_sequence).grid(row=0, column=2, padx=6, pady=10, sticky="ew")
        ttk.Button(bottom, text="Téléverser / SD", command=self.open_sd_window).grid(row=0, column=3, padx=6, pady=10, sticky="ew")

        loop_frame = ttk.Frame(bottom, style="Accent.TFrame")
        loop_frame.grid(row=0, column=4, sticky="e")
        ttk.Label(loop_frame, text="Boucles:", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.loop_var = tk.IntVar(value=1)
        ttk.Label(loop_frame, textvariable=self.loop_var, style="Heading.TLabel", width=4).grid(row=0, column=1)
        ttk.Button(loop_frame, text="-10", command=lambda: self.change_loop(-10), style="Toggle.TButton").grid(row=0, column=2, padx=2)
        ttk.Button(loop_frame, text="-1", command=lambda: self.change_loop(-1), style="Toggle.TButton").grid(row=0, column=3, padx=2)
        ttk.Button(loop_frame, text="+1", command=lambda: self.change_loop(+1), style="Toggle.TButton").grid(row=0, column=4, padx=2)
        ttk.Button(loop_frame, text="+10", command=lambda: self.change_loop(+10), style="Toggle.TButton").grid(row=0, column=5, padx=2)

        self.loop_info = tk.StringVar(value="Boucles prévues: 1")
        ttk.Label(bottom, textvariable=self.loop_info, style="Muted.TLabel").grid(row=0, column=5, sticky="e")

        self.status = ttk.Label(self, text="Prêt", style="Status.TLabel", anchor="w")
        self.status.pack(fill=tk.X, padx=12, pady=(0, 12))

    def _setup_serial_ui(self) -> None:
        menu_bar = tk.Menu(self)
        self.config(menu=menu_bar)
        serial_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="Série", menu=serial_menu)
        serial_menu.add_command(label="Choisir / ouvrir port", command=self.choose_serial_port)
        serial_menu.add_command(label="Fermer", command=self.close_serial)

    # ------------------------------------------------------- timeline ops ---

    def refresh_timeline_list(self) -> None:
        for item in self.timeline_tree.get_children():
            self.timeline_tree.delete(item)
        for idx, step in enumerate(self.timeline.steps):
            name = step.get("name", f"Step {idx + 1}")
            values = (
                name,
                step.get("servo0", 90),
                step.get("servo1", 90),
                step.get("servo2", 90),
                step.get("pause", 0),
                step.get("nano_cmd", ""),
            )
            self.timeline_tree.insert("", "end", iid=str(idx), values=values)

    def add_step_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Ajouter un pas")
        dialog.configure(bg=self.palette.background)
        DarkTheme(dialog, self.palette)
        dialog.grab_set()

        fields = {
            "name": tk.StringVar(value=f"Step {len(self.timeline.steps) + 1}"),
            "servo0": tk.IntVar(value=self.servo_vars[0].get()),
            "servo1": tk.IntVar(value=self.servo_vars[1].get()),
            "servo2": tk.IntVar(value=self.servo_vars[2].get()),
            "speed": tk.IntVar(value=self.speed_var.get()),
            "pause": tk.IntVar(value=500),
            "nano": tk.StringVar(value=""),
        }

        form = ttk.Frame(dialog, padding=20, style="Card.TFrame")
        form.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        entries = [
            ("Nom", "name"),
            ("Servo 0", "servo0"),
            ("Servo 1", "servo1"),
            ("Servo 2", "servo2"),
            ("Vitesse", "speed"),
            ("Pause (ms)", "pause"),
            ("Commande Nano", "nano"),
        ]
        for row, (label, key) in enumerate(entries):
            ttk.Label(form, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="e", padx=(0, 12), pady=4)
            ttk.Entry(form, textvariable=fields[key]).grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        def on_ok() -> None:
            step = {
                "name": fields["name"].get(),
                "servo0": fields["servo0"].get(),
                "servo1": fields["servo1"].get(),
                "servo2": fields["servo2"].get(),
                "speed": fields["speed"].get(),
                "pause": fields["pause"].get(),
                "nano_cmd": fields["nano"].get().strip(),
            }
            self.timeline.add_step(step)
            self.refresh_timeline_list()
            dialog.destroy()

        action_row = ttk.Frame(dialog, padding=(20, 0, 20, 20), style="Card.TFrame")
        action_row.grid(row=1, column=0, sticky="ew")
        action_row.columnconfigure(0, weight=1)
        ttk.Button(action_row, text="Valider", command=on_ok, style="Accent.TButton").grid(row=0, column=0, sticky="ew")

    def on_timeline_right_click(self, event: tk.Event) -> None:
        iid = self.timeline_tree.identify_row(event.y)
        if not iid:
            return
        self.timeline_tree.selection_set(iid)
        index = int(iid)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Répéter ce mouvement", command=lambda: self.repeat_step(index))
        menu.add_command(label="Revenir à cette étape", command=lambda: self.goto_step(index))
        menu.add_command(label="Supprimer cette étape", command=lambda: self.delete_step(index))
        menu.tk_popup(event.x_root, event.y_root)

    def repeat_step(self, idx: int) -> None:
        if 0 <= idx < len(self.timeline.steps):
            self.timeline.add_step(self.timeline.steps[idx].copy())
            self.refresh_timeline_list()

    def goto_step(self, idx: int) -> None:
        if not (0 <= idx < len(self.timeline.steps)):
            return
        step = self.timeline.steps[idx]
        self.append_console(f"Demande retour à l'étape {idx + 1} : {step.get('name', '')}")
        self.timeline_tree.selection_set(str(idx))
        self.timeline_tree.see(str(idx))

    def delete_step(self, idx: int) -> None:
        if 0 <= idx < len(self.timeline.steps):
            del self.timeline.steps[idx]
            self.refresh_timeline_list()

    # --------------------------------------------------------- sequences ---

    def play_sequence(self) -> None:
        if not self.timeline.steps:
            self.append_console("Aucune étape dans la timeline")
            self.status.configure(text="Séquence vide")
            return
        loops = max(1, self.loop_var.get())
        self.arm.play_sequence(self.timeline.steps, loops=loops, on_finished=self.on_sequence_finished)
        self.update_loop_info()
        self.status.configure(text=f"Lecture séquence ({loops} boucle(s))")

    def on_sequence_finished(self) -> None:
        self.append_console("Séquence terminée (callback)")
        self.status.configure(text="Séquence terminée")

    def stop_sequence(self) -> None:
        self.arm.stop_sequence()
        self.update_loop_info()
        self.status.configure(text="Séquence stoppée")

    def clear_sequence(self) -> None:
        self.timeline.clear()
        self.refresh_timeline_list()
        self.update_loop_info()
        self.status.configure(text="Timeline effacée")

    def change_loop(self, delta: int) -> None:
        value = max(1, self.loop_var.get() + delta)
        self.loop_var.set(value)
        self.update_loop_info()

    def update_loop_info(self) -> None:
        if self.arm.playing:
            done = self.arm.loop_total - self.arm.loop_remaining
            self.loop_info.set(f"Boucle: {done}/{self.arm.loop_total}")
        else:
            self.loop_info.set(f"Boucles prévues: {self.loop_var.get()}")

    # -------------------------------------------------- persistence ops ---

    def save_sequence(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Enregistrer séquence",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            self.timeline.save_to_file(path)
            self.append_console(f"Séquence sauvegardée: {path}")
        except Exception as exc:
            messagebox.showerror("Erreur", f"Erreur sauvegarde: {exc}")

    def load_sequence(self) -> None:
        path = filedialog.askopenfilename(
            title="Charger séquence",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            self.timeline.load_from_file(path)
            self.refresh_timeline_list()
            self.append_console(f"Séquence chargée: {path}")
        except Exception as exc:
            messagebox.showerror("Erreur", f"Erreur chargement: {exc}")

    # ---------------------------------------------------------- SD window ---

    def open_sd_window(self) -> None:
        if self.sd_window is None or not tk.Toplevel.winfo_exists(self.sd_window):
            self.sd_window = SdManagerWindow(self, self.serial_mgr, self.append_console, self.palette)
        else:
            self.sd_window.lift()

    # --------------------------------------------------- commands helpers ---

    def send_current_servo_pos(self) -> None:
        s0 = self.servo_vars[0].get()
        s1 = self.servo_vars[1].get()
        s2 = self.servo_vars[2].get()
        speed = self.speed_var.get()
        self.arm.send("M279")
        self.arm.send(f"M280 P0 S{s0} V{speed}")
        self.arm.send(f"M280 P1 S{s1} V{speed}")
        self.arm.send(f"M280 P2 S{s2} V{speed}")
        self.arm.send("M278")
        self.arm.send("M400")

    def set_delta(self, value: int) -> None:
        self.delta_x.set(value)

    def send_nano_move(self, delta: int, axis: str = "y") -> None:
        dx = self.delta_x.get()
        value = -abs(dx) if delta < 0 else abs(dx)
        axis = axis.lower()
        if axis not in {"x", "y", "z"}:
            axis = "y"
        cmd = f"R1 g0 {axis}{value} s200"
        self.arm.send(cmd)

    # ----------------------------------------------------------- console ---

    def append_console(self, text: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", text + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def send_console_line(self) -> None:
        line = self.console_entry.get().strip()
        self.console_entry.delete(0, "end")
        if not line:
            return
        self.arm.send(line)

    def on_console_enter(self, _: tk.Event) -> None:
        self.send_console_line()

    # ----------------------------------------------------------- serial ---

    def _on_close(self) -> None:
        if self.sd_window and tk.Toplevel.winfo_exists(self.sd_window):
            self.sd_window.destroy()
            self.sd_window = None
        self.serial_mgr.close()
        self.destroy()

    def choose_serial_port(self) -> None:
        ports = self.serial_mgr.list_ports()
        if not ports:
            messagebox.showerror("Erreur", "Aucun port série détecté (ou pyserial manquant).")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Choisir port série")
        dialog.configure(bg=self.palette.background)
        DarkTheme(dialog, self.palette)
        dialog.grab_set()

        selection = tk.StringVar(value=ports[0])
        option_frame = ttk.Frame(dialog, padding=20, style="Card.TFrame")
        option_frame.grid(row=0, column=0, sticky="nsew")
        for port in ports:
            ttk.Radiobutton(option_frame, text=port, variable=selection, value=port).pack(anchor="w", pady=4)

        def on_ok() -> None:
            try:
                self.serial_mgr.open(selection.get())
                self.append_console(f"Port série ouvert: {selection.get()}")
                self.status.configure(text=f"Connecté à {selection.get()}")
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("Erreur", f"Impossible d'ouvrir le port: {exc}")

        action_frame = ttk.Frame(dialog, padding=(20, 0, 20, 20), style="Card.TFrame")
        action_frame.grid(row=1, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        ttk.Button(action_frame, text="Valider", command=on_ok, style="Accent.TButton").grid(row=0, column=0, sticky="ew")

    def close_serial(self) -> None:
        self.serial_mgr.close()
        self.append_console("Port série fermé.")
        self.status.configure(text="Port série fermé")

    def _poll_serial(self) -> None:
        self.serial_mgr.poll()
        self.after(50, self._poll_serial)

    def on_serial_line(self, line: str) -> None:
        self.append_console(line)
        self.arm.on_serial_line(line)
        if self.sd_window and tk.Toplevel.winfo_exists(self.sd_window):
            if ("file list" in line) or ("." in line and " " in line):
                self.sd_window.on_sd_line(line)

    # ----------------------------------------------------- background img ---

    def load_background_image(self) -> None:
        if not Image:
            return
        path = "background.png"
        if not os.path.exists(path):
            return
        try:
            img = Image.open(path)
            img = img.resize((320, 320))
            self.background_image = ImageTk.PhotoImage(img)
            self.background_label.configure(image=self.background_image)
        except Exception:
            self.background_image = None
            self.background_label.configure(text="Impossible de charger l'image", style="Muted.TLabel")


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
