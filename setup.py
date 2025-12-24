import customtkinter
import os
from cx_Freeze import setup, Executable

# Find customtkinter path to include its assets (json themes, etc.)
ctk_path = os.path.dirname(customtkinter.__file__)

build_exe_options = {
    "excludes": ["unittest"],
    "include_files": [
        (ctk_path, "customtkinter"),
        ("res", "res")
    ],
    "packages": [
        "keyboard",
        "tkinter",
        "threading",
        "time",
        "tomlkit",
        "tomllib",
        "dxcam_cpp",
        "cv2",
        "customtkinter",
        "PIL"
    ],
}

setup(
    name="AutoShakeGUI",
    version="1.0",
    description="My GUI application!",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "auto_shake_gui.py",
            base="gui",
            icon="res/icon.ico"
        )
    ],
)
