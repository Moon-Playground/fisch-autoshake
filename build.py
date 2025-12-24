import PyInstaller.__main__
import os
import customtkinter

# Define dependencies manually
hidden_imports = [
    'dxcam_cpp',
    'cv2',
    'keyboard',
    'PIL',
    'customtkinter',
    'tomlkit',
    'tomllib'
]

# Define data files (Source, Destination)
# CustomTkinter needs its json themes/fonts
ctk_path = os.path.dirname(customtkinter.__file__)

datas = [
    (ctk_path, 'customtkinter')
]

if os.path.exists("res"):
    datas.append(('res', 'res'))
elif os.path.exists("icon.ico"):
    # Map root icon.ico to res/icon.ico in bundle
    datas.append(('icon.ico', 'res'))

# Construct arguments
args = [
    '--name=AutoShake',
    '--onefile',
    '--windowed',
    '--icon=res/icon.ico',
    'auto_shake_gui.py',
]

# Add hidden imports
for mod in hidden_imports:
    args.append(f'--hidden-import={mod}')

# Add datas
for src, dest in datas:
    # PyInstaller uses os.pathsep (';' on Windows) to separate source and dest in command line
    # Format: "source;dest"
    args.append(f'--add-data={src}{os.pathsep}{dest}')

PyInstaller.__main__.run(args)
