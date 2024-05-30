import sys
from cx_Freeze import setup, Executable

# Include additional files
include_files = ['network.ico']

# Base setup for Windows
base = None
if sys.platform == 'win32':
    base = 'Win32GUI'  # Use 'Win32GUI' for a GUI application, 'Console' for a console application

# Setup configuration
setup(
    name='NetworkMonitorApp',
    version='1.0',
    description='Network Traffic Monitor',
    options={
        'build_exe': {
            'packages': ['psutil', 'tkinter', 'matplotlib', 'pystray', 'PIL'],
            'include_files': include_files,
        }
    },
    executables=[Executable('network_monitor.py', base=base, icon='network.ico')]
)
