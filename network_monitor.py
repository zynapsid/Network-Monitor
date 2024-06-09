import psutil
import tkinter as tk
from tkinter import ttk, colorchooser
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
import threading
import pystray
from PIL import Image, ImageDraw
import json
import os
import winreg

class NetworkMonitorApp:
    CONFIG_FILE = 'network_monitor_config.json'
    REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "NetworkMonitor"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Network Traffic Monitor")
        self.root.geometry("600x400")
        self.root.configure(bg='#0D0D0D')
        self.root.withdraw()  # Minimize the main window at startup
        self.root.iconbitmap('network.ico')

        self.in_color = "#00FFFF"
        self.out_color = "#FF00FF"
        self.bg_color = "#0D0D0D"
        self.text_color = "#39FF14"

        self.load_config()

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background=self.bg_color, foreground=self.text_color, font=('Helvetica', 12, 'bold'))

        self.label_in = ttk.Label(self.root, text="Incoming Traffic: 0 Mbps (Process: None)")
        self.label_in.pack(padx=10, pady=5)

        self.label_out = ttk.Label(self.root, text="Outgoing Traffic: 0 Mbps (Process: None)")
        self.label_out.pack(padx=10, pady=5)

        self.fig, self.ax = plt.subplots()
        self.fig.patch.set_facecolor(self.bg_color)
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(axis='x', colors=self.text_color)
        self.ax.tick_params(axis='y', colors=self.text_color)
        self.ax.spines['bottom'].set_color(self.text_color)
        self.ax.spines['top'].set_color(self.text_color)
        self.ax.spines['left'].set_color(self.text_color)
        self.ax.spines['right'].set_color(self.text_color)
        self.line_in, = self.ax.plot([], [], label='Incoming Traffic (Mbps)', color=self.in_color)
        self.line_out, = self.ax.plot([], [], label='Outgoing Traffic (Mbps)', color=self.out_color)
        self.ax.legend(facecolor=self.bg_color, edgecolor=self.text_color, labelcolor=self.text_color)
        self.ax.set_xlabel('Time (s)', color=self.text_color)
        self.ax.set_ylabel('Traffic (Mbps)', color=self.text_color)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.time_data = []
        self.in_data = []
        self.out_data = []

        self.start_time = time.time()

        self.last_received = 0
        self.last_sent = 0

        self.process_usage = {}

        self.tray_icon = None
        self.tray_thread = None

        self.initialize_network_usage()
        self.update_network_usage()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.create_tray_icon()
        self.startup_enabled = tk.BooleanVar()
        self.startup_enabled.set(self.is_startup_enabled())
        self.create_options_menu()

    def initialize_network_usage(self):
        self.process_usage = {}
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                io_counters = proc.io_counters()
                if io_counters:
                    self.process_usage[proc.pid] = {
                        'name': proc.name(),
                        'initial_read': io_counters.read_bytes,
                        'initial_write': io_counters.write_bytes,
                        'recv_per_sec': 0,
                        'sent_per_sec': 0
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def update_process_network_usage(self):
        for pid, usage in list(self.process_usage.items()):
            try:
                proc = psutil.Process(pid)
                io_counters = proc.io_counters()
                if io_counters:
                    recv_per_sec = io_counters.read_bytes - usage['initial_read']
                    sent_per_sec = io_counters.write_bytes - usage['initial_write']

                    self.process_usage[pid]['recv_per_sec'] = recv_per_sec
                    self.process_usage[pid]['sent_per_sec'] = sent_per_sec
                    self.process_usage[pid]['initial_read'] = io_counters.read_bytes
                    self.process_usage[pid]['initial_write'] = io_counters.write_bytes
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                del self.process_usage[pid]
                continue

    def update_network_usage(self):
        current_time = time.time() - self.start_time
        self.time_data.append(current_time)

        counters = psutil.net_io_counters()

        if self.last_received == 0 and self.last_sent == 0:
            self.last_received = counters.bytes_recv
            self.last_sent = counters.bytes_sent

        received_per_sec = counters.bytes_recv - self.last_received
        sent_per_sec = counters.bytes_sent - self.last_sent

        self.last_received = counters.bytes_recv
        self.last_sent = counters.bytes_sent

        received_mbps = (received_per_sec * 8) / 1e6
        sent_mbps = (sent_per_sec * 8) / 1e6

        self.in_data.append(received_mbps)
        self.out_data.append(sent_mbps)

        self.update_process_network_usage()

        process_in = max(self.process_usage.items(), key=lambda x: x[1]['recv_per_sec'], default=(None, {'name': 'None'}))[1]['name']
        process_out = max(self.process_usage.items(), key=lambda x: x[1]['sent_per_sec'], default=(None, {'name': 'None'}))[1]['name']

        self.label_in.config(text=f"Incoming Traffic: {received_mbps:.2f} Mbps (Process: {process_in})")
        self.label_out.config(text=f"Outgoing Traffic: {sent_mbps:.2f} Mbps (Process: {process_out})")

        self.line_in.set_data(self.time_data, self.in_data)
        self.line_out.set_data(self.time_data, self.out_data)
        self.ax.set_xlim(0, current_time)
        self.ax.set_ylim(0, max(max(self.in_data), max(self.out_data)) * 1.1)

        self.canvas.draw()

        if self.tray_icon:
            self.update_tray_icon(received_mbps, sent_mbps, process_in, process_out)

        self.root.after(1000, self.update_network_usage)

    def create_image(self, received_mbps, sent_mbps, process_in, process_out):
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (13, 13, 13))
        dc = ImageDraw.Draw(image)

        max_height = height - 20
        max_value = max(received_mbps, sent_mbps, 10)

        recv_height = int((received_mbps / max_value) * max_height)
        sent_height = int((sent_mbps / max_value) * max_height)

        dc.rectangle([10, height - recv_height, 30, height], fill=self.in_color)
        dc.rectangle([34, height - sent_height, 54, height], fill=self.out_color)

        dc.text((10, height - recv_height - 15), "In", fill=self.in_color)
        dc.text((34, height - sent_height - 15), "Out", fill=self.out_color)

        return image

    def update_tray_icon(self, received_mbps, sent_mbps, process_in, process_out):
        icon_image = self.create_image(received_mbps, sent_mbps, process_in, process_out)
        self.tray_icon.icon = icon_image
        self.tray_icon.title = f"Incoming: {received_mbps:.2f} Mbps (Process: {process_in}), Outgoing: {sent_mbps:.2f} Mbps (Process: {process_out})"

    def create_tray_icon(self):
        icon_image = self.create_image(0, 0, "None", "None")
        self.tray_icon = pystray.Icon("NetworkMonitor", icon_image, "Network Monitor", menu=pystray.Menu(
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Exit", self.exit_app)
        ))
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def show_window(self):
        self.root.deiconify()

    def hide_window(self):
        self.root.withdraw()

    def exit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.save_config()
        self.root.quit()

    def create_options_menu(self):
        menubar = tk.Menu(self.root)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Change Incoming Color", command=self.change_incoming_color)
        options_menu.add_command(label="Change Outgoing Color", command=self.change_outgoing_color)
        options_menu.add_command(label="Change Background Color", command=self.change_background_color)
        options_menu.add_command(label="Change Text Color", command=self.change_text_color)
        options_menu.add_checkbutton(label="Toggle Startup", command=self.toggle_startup, variable=self.startup_enabled)
        menubar.add_cascade(label="Options", menu=options_menu)
        self.root.config(menu=menubar)

    def change_incoming_color(self):
        color = colorchooser.askcolor(title="Choose Incoming Traffic Color")[1]
        if color:
            self.in_color = color
            self.line_in.set_color(self.in_color)
            self.ax.legend().texts[0].set_color(self.in_color)
            self.canvas.draw()

    def change_outgoing_color(self):
        color = colorchooser.askcolor(title="Choose Outgoing Traffic Color")[1]
        if color:
            self.out_color = color
            self.line_out.set_color(self.out_color)
            self.ax.legend().texts[1].set_color(self.out_color)
            self.canvas.draw()

    def change_background_color(self):
        color = colorchooser.askcolor(title="Choose Background Color")[1]
        if color:
            self.bg_color = color
            self.root.configure(bg=self.bg_color)
            style = ttk.Style()
            style.configure('TLabel', background=self.bg_color)
            self.fig.patch.set_facecolor(self.bg_color)
            self.ax.set_facecolor(self.bg_color)
            self.ax.legend().set_facecolor(self.bg_color)
            self.canvas.draw()

    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color")[1]
        if color:
            self.text_color = color
            style = ttk.Style()
            style.configure('TLabel', foreground=self.text_color)
            self.ax.tick_params(axis='x', colors=self.text_color)
            self.ax.tick_params(axis='y', colors=self.text_color)
            for spine in self.ax.spines.values():
                spine.set_color(self.text_color)
            for text in self.ax.legend().texts:
                text.set_color(self.text_color)
            self.ax.set_xlabel('Time (s)', color=self.text_color)
            self.ax.set_ylabel('Traffic (Mbps)', color=self.text_color)
            self.canvas.draw()

    def toggle_startup(self):
        try:
            # Use the path to the executable created by cx_Freeze
            exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist', 'network_monitor.exe')
            exe_path_quoted = f'"{exe_path}"'  # Ensure the path is in quotation marks

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if self.is_startup_enabled():
                    winreg.DeleteValue(key, self.APP_NAME)
                    self.startup_enabled.set(False)
                    print("Startup entry removed")
                else:
                    winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, exe_path_quoted)
                    self.startup_enabled.set(True)
                    print(f"Startup entry added: {exe_path_quoted}")
        except Exception as e:
            print(f"Failed to update startup setting: {e}")


    def is_startup_enabled(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, self.APP_NAME)
                return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Error checking startup setting: {e}")
            return False

    def load_config(self):
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                config = json.load(f)
                self.in_color = config.get('in_color', self.in_color)
                self.out_color = config.get('out_color', self.out_color)
                self.bg_color = config.get('bg_color', self.bg_color)
                self.text_color = config.get('text_color', self.text_color)
        except FileNotFoundError:
            pass

    def save_config(self):
        config = {
            'in_color': self.in_color,
            'out_color': self.out_color,
            'bg_color': self.bg_color,
            'text_color': self.text_color
        }
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(config, f)

if __name__ == "__main__":
    app = NetworkMonitorApp()
    app.root.mainloop()
