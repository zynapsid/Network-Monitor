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
            self.root.configure(bg='#0D0D0D')  # Dark background

            # Set the icon for the taskbar and title bar
            self.root.iconbitmap('network.ico')

            self.in_color = "#00FFFF"  # Default neon cyan for incoming
            self.out_color = "#FF00FF"  # Default neon magenta for outgoing
            self.bg_color = "#0D0D0D"   # Default dark background
            self.text_color = "#39FF14"  # Default neon green text

            self.load_config()

            style = ttk.Style()
            style.theme_use('clam')  # Use a modern theme
            style.configure('TLabel', background=self.bg_color, foreground=self.text_color, font=('Helvetica', 12, 'bold'))  # Neon green text

            self.label_in = ttk.Label(self.root, text="Incoming Traffic: 0 Mbps (Process: None)")
            self.label_in.pack(padx=10, pady=5)

            self.label_out = ttk.Label(self.root, text="Outgoing Traffic: 0 Mbps (Process: None)")
            self.label_out.pack(padx=10, pady=5)

            # Initialize plot with cyberpunk aesthetic
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

            self.tray_icon = None
            self.tray_thread = None

            self.update_network_usage()

            self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
            self.create_tray_icon()
            self.create_options_menu()

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

        received_mbps = (received_per_sec * 8) / 1e6  # Convert to Megabits
        sent_mbps = (sent_per_sec * 8) / 1e6  # Convert to Megabits

        self.in_data.append(received_mbps)
        self.out_data.append(sent_mbps)

        # Find process using most incoming and outgoing bandwidth
        process_in, process_out = self.get_top_bandwidth_processes()

        self.label_in.config(text=f"Incoming Traffic: {received_mbps:.2f} Mbps (Process: {process_in})")
        self.label_out.config(text=f"Outgoing Traffic: {sent_mbps:.2f} Mbps (Process: {process_out})")

        # Update the plot
        self.line_in.set_data(self.time_data, self.in_data)
        self.line_out.set_data(self.time_data, self.out_data)
        self.ax.set_xlim(0, current_time)
        self.ax.set_ylim(0, max(max(self.in_data), max(self.out_data)) * 1.1)

        self.canvas.draw()

        # Update tray icon
        if self.tray_icon:
            self.update_tray_icon(received_mbps, sent_mbps, process_in, process_out)

        self.root.after(1000, self.update_network_usage)

    def get_top_bandwidth_processes(self):
        net_io_by_pid = {}
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                connections = proc.connections(kind='inet')
                io_counters = proc.io_counters()
                if connections:
                    net_io_by_pid[proc.pid] = (proc.name(), io_counters.read_bytes, io_counters.write_bytes)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        in_proc = max(net_io_by_pid.items(), key=lambda x: x[1][1], default=(None, [None, 0]))[1][0]
        out_proc = max(net_io_by_pid.items(), key=lambda x: x[1][2], default=(None, [None, 0]))[1][0]

        return in_proc, out_proc

    def create_image(self, received_mbps, sent_mbps, process_in, process_out):
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (13, 13, 13))  # Dark background
        dc = ImageDraw.Draw(image)

        # Draw a simple two-bar graph for received and sent Mbps with chosen colors
        max_height = height - 20
        max_value = max(received_mbps, sent_mbps, 10)

        recv_height = int((received_mbps / max_value) * max_height)
        sent_height = int((sent_mbps / max_value) * max_height)

        # Draw the bars
        dc.rectangle([10, height - recv_height, 30, height], fill=self.in_color)
        dc.rectangle([34, height - sent_height, 54, height], fill=self.out_color)

        # Draw the labels
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
            pystray.MenuItem("Options", self.show_options_menu),  # Add an "Options" menu item
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
        self.options_window = tk.Toplevel(self.root)
        self.options_window.title("Options")
        self.options_window.geometry("350x250")
        self.options_window.configure(bg=self.bg_color)
        self.options_window.withdraw()

        ttk.Label(self.options_window, text="Incoming Traffic Color:").grid(row=0, column=0, padx=10, pady=5)
        self.in_color_canvas = tk.Canvas(self.options_window, width=25, height=25, bg="white", highlightthickness=0)
        self.in_color_canvas.grid(row=0, column=1, padx=10, pady=5)
        self.create_color_square(self.in_color_canvas, self.in_color)
        self.in_color_button = ttk.Button(self.options_window, text="Choose Color", command=lambda: self.choose_color('in'))
        self.in_color_button.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(self.options_window, text="Outgoing Traffic Color:").grid(row=1, column=0, padx=10, pady=5)
        self.out_color_canvas = tk.Canvas(self.options_window, width=25, height=25, bg="white", highlightthickness=0)
        self.out_color_canvas.grid(row=1, column=1, padx=10, pady=5)
        self.create_color_square(self.out_color_canvas, self.out_color)
        self.out_color_button = ttk.Button(self.options_window, text="Choose Color", command=lambda: self.choose_color('out'))
        self.out_color_button.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(self.options_window, text="Background Color:").grid(row=2, column=0, padx=10, pady=5)
        self.bg_color_canvas = tk.Canvas(self.options_window, width=25, height=25, bg="white", highlightthickness=0)
        self.bg_color_canvas.grid(row=2, column=1, padx=10, pady=5)
        self.create_color_square(self.bg_color_canvas, self.bg_color)
        self.bg_color_button = ttk.Button(self.options_window, text="Choose Color", command=lambda: self.choose_color('bg'))
        self.bg_color_button.grid(row=2, column=2, padx=5, pady=5)

        ttk.Label(self.options_window, text="Text Color:").grid(row=3, column=0, padx=10, pady=5)
        self.text_color_canvas = tk.Canvas(self.options_window, width=25, height=25, bg="white", highlightthickness=0)
        self.text_color_canvas.grid(row=3, column=1, padx=10, pady=5)
        self.create_color_square(self.text_color_canvas, self.text_color)
        self.text_color_button = ttk.Button(self.options_window, text="Choose Color", command=lambda: self.choose_color('text'))
        self.text_color_button.grid(row=3, column=2, padx=5, pady=5)

        self.startup_var = tk.BooleanVar()
        self.startup_check = ttk.Checkbutton(self.options_window, text="Start at Windows Login", variable=self.startup_var, command=self.update_startup)
        self.startup_check.grid(row=4, columnspan=3, padx=10, pady=10)
        self.startup_var.set(self.check_startup())

        ttk.Button(self.options_window, text="Close", command=self.hide_options_window).grid(row=5, columnspan=3, padx=10, pady=10)

        self.options_window.protocol("WM_DELETE_WINDOW", self.hide_options_window)

    def create_color_square(self, canvas, color):
        canvas.create_rectangle(0, 0, 25, 25, fill=color, outline="")

    def show_options_menu(self):
        self.options_window.deiconify()

    def hide_options_window(self):
        self.options_window.withdraw()

    def choose_color(self, color_type):
        color = colorchooser.askcolor(title="Choose Color")[1]
        if color:
            if color_type == 'in':
                self.in_color = color
            elif color_type == 'out':
                self.out_color = color
            elif color_type == 'bg':
                self.bg_color = color
            elif color_type == 'text':
                self.text_color = color
            self.update_colors()

    def update_colors(self):
        self.label_in.config(foreground=self.text_color)
        self.label_out.config(foreground=self.text_color)
        self.root.configure(bg=self.bg_color)

        self.fig.patch.set_facecolor(self.bg_color)
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(axis='x', colors=self.text_color)
        self.ax.tick_params(axis='y', colors=self.text_color)
        self.ax.spines['bottom'].set_color(self.text_color)
        self.ax.spines['top'].set_color(self.text_color)
        self.ax.spines['left'].set_color(self.text_color)
        self.ax.spines['right'].set_color(self.text_color)
        self.line_in.set_color(self.in_color)
        self.line_out.set_color(self.out_color)

        self.ax.legend(facecolor=self.bg_color, edgecolor=self.text_color, labelcolor=self.text_color)

        if self.tray_icon:
            self.update_tray_icon(0, 0, "None", "None")

        self.update_color_square(self.in_color_canvas, self.in_color)
        self.update_color_square(self.out_color_canvas, self.out_color)
        self.update_color_square(self.bg_color_canvas, self.bg_color)
        self.update_color_square(self.text_color_canvas, self.text_color)

    def update_color_square(self, canvas, color):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, 25, 25, fill=color, outline="")

    def save_config(self):
        config = {
            'in_color': self.in_color,
            'out_color': self.out_color,
            'bg_color': self.bg_color,
            'text_color': self.text_color
        }
        with open(self.CONFIG_FILE, 'w') as config_file:
            json.dump(config, config_file)

    def load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, 'r') as config_file:
                config = json.load(config_file)
                self.in_color = config.get('in_color', self.in_color)
                self.out_color = config.get('out_color', self.out_color)
                self.bg_color = config.get('bg_color', self.bg_color)
                self.text_color = config.get('text_color', self.text_color)

    def update_startup(self):
        if self.startup_var.get():
            self.add_to_startup()
        else:
            self.remove_from_startup()

    def check_startup(self):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH, 0, winreg.KEY_READ) as key:
            try:
                value, regtype = winreg.QueryValueEx(key, self.APP_NAME)
                return True
            except FileNotFoundError:
                return False

    def add_to_startup(self):
        exe_path = os.path.realpath(__file__)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, exe_path)

    def remove_from_startup(self):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, self.APP_NAME)

if __name__ == "__main__":
    app = NetworkMonitorApp()
    app.root.withdraw()
    app.root.mainloop()
