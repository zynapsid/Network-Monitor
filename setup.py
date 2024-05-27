from cx_Freeze import setup, Executable
import sys

# Dependencies are automatically detected, but it might need fine-tuning.
build_exe_options = {
    "packages": ["os", "tkinter", "psutil", "matplotlib", "pystray", "PIL", "json", "winreg", "threading", "time"],
    "include_files": []  # Include any other necessary files here
}

base = None
if sys.platform == "win32":
    base = "Win32GUI"  # Use "Win32GUI" to avoid the console window popping up

setup(
    name="NetworkMonitor",
    version="0.1",
    description="Network Traffic Monitor Application",
    options={"build_exe": build_exe_options},
    executables=[Executable("network_monitor.py", base=base, icon="network.ico")]
)
