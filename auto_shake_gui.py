import dxcam_cpp as dxcam
import keyboard as kb
import cv2
import os
import sys
import tkinter as tk
import customtkinter as ctk
import threading
import time
import tomlkit
import tomllib
from PIL import Image

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class CaptureBox(tk.Toplevel):
    def __init__(
        self,
        box_color: str = "blue",
        box_alpha: float = 0.3,
        box_x: int = 122,
        box_y: int = 40,
        box_width: int = 1162,
        box_height: int = 586,
        text: str = ""
    ):
        super().__init__()
        self.capture_width, self.capture_height = box_width, box_height
        self.capture_x, self.capture_y = box_x, box_y
        self.geometry(f"{self.capture_width}x{self.capture_height}+{self.capture_x}+{self.capture_y}")
        self.overrideredirect(True)
        self.configure(bg=box_color)

        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)

        # Dragging
        self.bind("<ButtonPress-1>", self.start_move)
        self.bind("<B1-Motion>", self.do_move)

        # Resize handle - standard tk Label for cursor support
        self.resize_handle = tk.Label(self, bg="darkgreen", cursor="bottom_right_corner")
        self.resize_handle.place(relx=1.0, rely=1.0, anchor="se", width=20, height=20)
        self.resize_handle.bind("<ButtonPress-1>", self.start_resize)
        self.resize_handle.bind("<B1-Motion>", self.do_resize)

        self.text_label = tk.Label(self, text=text, bg=box_color, fg="white", font=("Arial", 12))
        self.text_label.place(relx=0.5, rely=0.5, anchor="center")

    def start_move(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def do_move(self, event):
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.capture_x = self.winfo_x() + dx
        self.capture_y = self.winfo_y() + dy
        self.geometry(f"{self.capture_width}x{self.capture_height}+{self.capture_x}+{self.capture_y}")

    def start_resize(self, event):
        self.resize_start_x = event.x_root
        self.resize_start_y = event.y_root
        self.resize_orig_width = self.capture_width
        self.resize_orig_height = self.capture_height

    def do_resize(self, event):
        dx = event.x_root - self.resize_start_x
        dy = event.y_root - self.resize_start_y
        self.capture_width = max(50, self.resize_orig_width + dx)
        self.capture_height = max(50, self.resize_orig_height + dy)
        self.geometry(f"{self.capture_width}x{self.capture_height}+{self.capture_x}+{self.capture_y}")


class AutoShakeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.active = threading.Event()
        self.force_stop = threading.Event()
        self.title("Auto Shake")
        self.geometry("600x400")
        
        # Load config first
        self.config_data = self.load_config()
        
        self.camera = dxcam.create()
        self.capture_box = CaptureBox(
            box_color="blue",
            box_alpha=0.3,
            text="Capture Box"
        )
        self.capture_box.capture_width = self.config_data['ocr']['capture_width']
        self.capture_box.capture_height = self.config_data['ocr']['capture_height']
        self.capture_box.capture_x = self.config_data['ocr']['capture_x']
        self.capture_box.capture_y = self.config_data['ocr']['capture_y']
        self.enable_overlay = self.config_data['ui']['enable_overlay']

        # Bind virtual events
        self.bind("<<ToggleBox>>", lambda e: self._toggle_box())
        self.bind("<<ToggleAction>>", lambda e: self._toggle_action())
        self.bind("<<ExitApp>>", lambda e: self._exit_app())

        self.setup_ui()
        self.apply_hotkeys()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Status Window (Standard TK for simpler overlay management)
        self.status_window = None
        self.create_status_window()
        if not self.enable_overlay:
            self.hide_status_window()
        self.after(200, lambda: self._set_icon())

    def _set_icon(self):
        icon_candidates = []
        
        # 1. PyInstaller Temp Path
        if hasattr(sys, '_MEIPASS'):
            icon_candidates.append(os.path.join(sys._MEIPASS, "res", "icon.ico"))
            icon_candidates.append(os.path.join(sys._MEIPASS, "icon.ico"))
        
        # 2. Local Paths
        icon_candidates.append(os.path.abspath("res/icon.ico"))
        icon_candidates.append(os.path.abspath("icon.ico"))

        for icon_path in icon_candidates:
            if os.path.exists(icon_path):
                try:
                    self.iconbitmap(icon_path)
                    # print(f"Icon loaded from: {icon_path}")
                    return
                except Exception:
                    continue
        
        # print("Icon not found in any candidate path")

    def setup_ui(self):
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        self.home_tab = self.tab_view.add("Home")
        self.settings_tab = self.tab_view.add("Settings")

        # --- HOME TAB ---
        self.description = ctk.CTkLabel(
            self.home_tab, 
            text="Simple Auto Shake for roblox fisch (Navigation Mode)\nWhen active, it will detect the shake box and press enter.\nMake sure to setup the navigation mode in roblox before activation.", 
            font=("Arial", 14)
        )
        self.description.pack(pady=20)

        self.status_label = ctk.CTkLabel(self.home_tab, text="Status: Inactive", text_color="red", font=("Arial", 16, "bold"))
        self.status_label.pack(pady=10)

        self.info_label = ctk.CTkLabel(self.home_tab, text="Hotkeys are configurable in Settings", font=("Arial", 12))
        self.info_label.pack(pady=10)

        # --- SETTINGS TAB ---
        self.settings_frame = ctk.CTkFrame(self.settings_tab)
        self.settings_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        # Hotkey Entries
        self.hk_entries = {}

        def add_hk_row(row, label, key):
            ctk.CTkLabel(self.settings_frame, text=label).grid(row=row, column=0, padx=15, pady=15, sticky="w")
            entry = ctk.CTkEntry(self.settings_frame)
            current_val = self.config_data['hotkeys'].get(key, "")
            entry.insert(0, current_val)
            entry.grid(row=row, column=1, padx=10, pady=15, sticky="ew")
            self.hk_entries[key] = entry

        add_hk_row(0, "Toggle Box:", "toggle_box")
        add_hk_row(1, "Start/Stop:", "toggle_action")
        add_hk_row(2, "Exit App:", "exit_app")

        # Overlay entries
        ctk.CTkLabel(self.settings_frame, text="Status Overlay").grid(row=3, column=0, padx=15, pady=15, sticky="w")
        self.overlay_var = ctk.BooleanVar(value=self.enable_overlay)
        overlay_cb = ctk.CTkSwitch(self.settings_frame, text="", variable=self.overlay_var)
        overlay_cb.grid(row=3, column=1, padx=10, pady=15, sticky="ew")

        self.save_btn = ctk.CTkButton(self.settings_frame, text="Save & Apply", command=self.save_and_apply_config)
        self.save_btn.grid(row=4, column=0, columnspan=2, pady=20)

    def create_status_window(self):
        if self.status_window:
            try:
                self.status_window.destroy()
            except:
                pass
        self.status_window = tk.Toplevel(self)
        self.status_window.title("AutoShake Status")
        
        # Load pos from config or default
        sx = self.config_data.get('ui', {}).get('status_x', 100)
        sy = self.config_data.get('ui', {}).get('status_y', 100)
        self.status_window.geometry(f"150x20+{sx}+{sy}")

        self.status_window.attributes("-topmost", True)
        self.status_window.attributes("-alpha", 0.7) # Semi-transparent
        self.status_window.overrideredirect(True)    # Borderless
        
        # Style
        self.status_window.configure(bg="black")
        self.status_lbl_widget = tk.Label(self.status_window, text="AutoShake: Inactive", font=("Arial", 10, "bold"), bg="black", fg="white")
        self.status_lbl_widget.pack(expand=True, fill="both")
        
        # Drag functionality
        self.status_window.bind("<ButtonPress-1>", self.start_status_move)
        self.status_window.bind("<B1-Motion>", self.do_status_move)
        self.status_window.bind("<ButtonRelease-1>", self.stop_status_move)
        
        self.status_lbl_widget.bind("<ButtonPress-1>", self.start_status_move)
        self.status_lbl_widget.bind("<B1-Motion>", self.do_status_move)
        self.status_lbl_widget.bind("<ButtonRelease-1>", self.stop_status_move)

        #self.hide_status_window()

    def start_status_move(self, event):
        self.status_drag_x = event.x
        self.status_drag_y = event.y

    def do_status_move(self, event):
        x = self.status_window.winfo_x() - self.status_drag_x + event.x
        y = self.status_window.winfo_y() - self.status_drag_y + event.y
        self.status_window.geometry(f"+{x}+{y}")
        
        # Update config directly (debounce could be better but this is fine for now)
        if "ui" not in self.config_data:
            self.config_data["ui"] = {}
        self.config_data["ui"]["status_x"] = x
        self.config_data["ui"]["status_y"] = y
        # We can save on mouse release ideally, but implicit save on exit is safer for perf
        # Let's bind ButtonRelease to save
        
    def stop_status_move(self, event):
        if "ui" not in self.config_data:
            self.config_data["ui"] = {}
        self.config_data["ui"]["status_x"] = self.status_window.winfo_x()
        self.config_data["ui"]["status_y"] = self.status_window.winfo_y()
        self.save_config_file(self.config_data)

    def hide_status_window(self):
        self.status_window.withdraw()

    def show_status_window(self):
        self.status_window.deiconify()
        self.status_window.lift()

    def _toggle_action(self):
        if self.active.is_set():
            self.active.clear()
            self.status_lbl_widget.config(text="AutoShake: Inactive")
            self.status_label.configure(text="AutoShake: Inactive", text_color="red")
        else:
            self.active.set()
            self.status_lbl_widget.config(text="AutoShake: Active")
            self.status_label.configure(text="AutoShake: Active", text_color="green")
            self.show_status_window()

    def _toggle_box(self):
        if self.capture_box.state() == "withdrawn":
            self.capture_box.deiconify()
        else:
            self.save_config_coords()
            self.capture_box.withdraw()

    def _exit_app(self):
        self.force_stop.set()
        self.quit()

    def on_close(self):
        self.force_stop.set()
        self.destroy()
        os._exit(0)

    def capture_screen(self):
        if self.camera is None:
            return None

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        x = int(self.capture_box.capture_x)
        y = int(self.capture_box.capture_y)
        w = int(self.capture_box.capture_width)
        h = int(self.capture_box.capture_height)

        left = max(0, x)
        top = max(0, y)
        right = min(screen_width, x + w)
        bottom = min(screen_height, y + h)

        if right <= left or bottom <= top:
            return None

        try:
            frame = self.camera.grab(region=(left, top, right, bottom))
            return frame
        except Exception as e:
            # print(f"Capture error: {e}")
            return None

    def capture_worker(self):
        while not self.force_stop.is_set():
            self.active.wait()
            
            frame = self.capture_screen()
            if frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            detected = False
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if w > 40 and h > 40:
                    detected = True
                    break

            if detected:
                kb.press_and_release('enter')

    def load_config(self):
        default_config = {
            "ocr": {
                "capture_width": 1162,
                "capture_height": 586,
                "capture_x": 122,
                "capture_y": 40
            },
            "hotkeys": {
                "toggle_box": "F3",
                "toggle_action": "F4",
                "exit_app": "F5"
            },
            "ui": {
                "enable_overlay": True,
                "status_x": 85,
                "status_y": 1
            }
        }

        if os.path.exists("auto_shake.toml"):
            try:
                with open("auto_shake.toml", "rb") as f:
                    config = tomllib.load(f)
                
                # Ensure all keys exist
                if "ocr" not in config: config["ocr"] = default_config["ocr"]
                if "hotkeys" not in config: config["hotkeys"] = default_config["hotkeys"]
                return config
            except Exception:
                pass

        # Save default if not exists or failed
        self.save_config_file(default_config)
        return default_config

    def save_config_coords(self):
        self.config_data["ocr"]["capture_width"] = self.capture_box.capture_width
        self.config_data["ocr"]["capture_height"] = self.capture_box.capture_height
        self.config_data["ocr"]["capture_x"] = self.capture_box.capture_x
        self.config_data["ocr"]["capture_y"] = self.capture_box.capture_y
        self.save_config_file(self.config_data)

    def save_and_apply_config(self):
        # Update config data from UI
        for key, entry in self.hk_entries.items():
            self.config_data["hotkeys"][key] = entry.get()
        if self.overlay_var.get() != self.enable_overlay:
            self.enable_overlay = self.overlay_var.get()
            if self.enable_overlay:
                self.show_status_window()
            else:
                self.hide_status_window()
        self.config_data["ui"]["enable_overlay"] = self.overlay_var.get()
        self.save_config_file(self.config_data)
        self.apply_hotkeys()

    def save_config_file(self, config):
        with open("auto_shake.toml", "w") as f:
            tomlkit.dump(tomlkit.parse(tomlkit.dumps(config)), f)

    def apply_hotkeys(self):
        if hasattr(self, 'active_hotkeys'):
            for hk in self.active_hotkeys:
                try:
                    kb.remove_hotkey(hk)
                except:
                    pass
        else:
            self.active_hotkeys = []
            
        self.active_hotkeys = []

        def reg(hk, event_name):
            if hk:
                try:
                    kb.add_hotkey(hk, lambda: self.after(0, self.event_generate, event_name))
                    self.active_hotkeys.append(hk)
                except Exception as e:
                    print(f"Failed to register hotkey {hk}: {e}")

        t_box = self.config_data["hotkeys"].get("toggle_box", "F3")
        t_act = self.config_data["hotkeys"].get("toggle_action", "F4")
        t_exit = self.config_data["hotkeys"].get("exit_app", "F5")

        reg(t_box, "<<ToggleBox>>")
        reg(t_act, "<<ToggleAction>>")
        reg(t_exit, "<<ExitApp>>")

        # Update info label
        self.info_label.configure(text=f"{t_box}: Box | {t_act}: Start/Stop | {t_exit}: Exit")

    def run(self):
        self.capture_box.geometry(f"{self.capture_box.capture_width}x{self.capture_box.capture_height}+{self.capture_box.capture_x}+{self.capture_box.capture_y}")
        self.capture_box.withdraw()
        
        threading.Thread(target=self.capture_worker, daemon=True).start()
        self.mainloop()

if __name__ == "__main__":
    AutoShakeApp().run()
