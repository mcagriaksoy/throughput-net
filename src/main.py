import subprocess
import json
import threading
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# --- UI scaling constants for 2K screens ---
UI_FONT = ("Segoe UI", 16)
UI_PADX = 20
UI_PADY = 20
FIGSIZE = (10, 5)

def run_iperf_realtime(server, port, interval, update_callback, done_callback, stop_event):
    cmd = [
        "iperf3/iperf3.exe",
        "-c", server,
        "-p", str(port),
        "-i", str(interval),
        "-J"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        buffer = ""
        intervals = []
        while not stop_event.is_set():
            line = proc.stdout.readline()
            if not line:
                break
            buffer += line
            # Try to parse JSON if possible
            try:
                data = json.loads(buffer)
                if "intervals" in data:
                    intervals = data["intervals"]
                    update_callback(intervals)
            except Exception:
                pass  # Not yet a complete JSON
        if proc.poll() is None:
            proc.terminate()
        # Try to parse final output
        try:
            data = json.loads(buffer)
            done_callback(data)
        except Exception as e:
            done_callback({"error": f"Parse error: {e}"})
    except Exception as e:
        done_callback({"error": str(e)})

def run_iperf_server(port, output_callback, stop_event):
    cmd = [
        "iperf3/iperf3.exe",
        "-s",
        "-p", str(port),
        "-J"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output_callback("Server started on port {}".format(port))
        while not stop_event.is_set():
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            # Parse server output for status messages
            try:
                data = json.loads(line)
                if "connected" in line:
                    output_callback("Client connected.")
                if "intervals" in data:
                    output_callback("Test ongoing...")
                if "end" in data:
                    output_callback("Test finished.")
            except Exception:
                pass
        proc.terminate()
        output_callback("Server stopped.")
    except Exception as e:
        output_callback(f"Server error: {e}")

class IperfClientUI:
    def __init__(self, root):
        self.root = root
        self.root.title("iPerf Client - Network Throughput Graph")

        frame = ttk.Frame(root)
        frame.pack(padx=UI_PADX, pady=UI_PADY)

        ttk.Label(frame, text="Server:", font=UI_FONT).grid(row=0, column=0, sticky="e")
        self.server_entry = ttk.Entry(frame, font=UI_FONT, width=18)
        self.server_entry.insert(0, "127.0.0.1")
        self.server_entry.grid(row=0, column=1)

        ttk.Label(frame, text="Port:", font=UI_FONT).grid(row=1, column=0, sticky="e")
        self.port_entry = ttk.Entry(frame, font=UI_FONT, width=18)
        self.port_entry.insert(0, "5201")
        self.port_entry.grid(row=1, column=1)

        ttk.Label(frame, text="Duration (s):", font=UI_FONT).grid(row=2, column=0, sticky="e")
        self.duration_entry = ttk.Entry(frame, font=UI_FONT, width=18)
        self.duration_entry.insert(0, "10")
        self.duration_entry.grid(row=2, column=1)

        ttk.Label(frame, text="Interval (s):", font=UI_FONT).grid(row=3, column=0, sticky="e")
        self.interval_var = tk.StringVar(value="1")
        self.interval_combo = ttk.Combobox(frame, textvariable=self.interval_var, font=UI_FONT, width=16, state="readonly")
        self.interval_combo["values"] = ("1", "5", "10", "30")
        self.interval_combo.grid(row=3, column=1)

        self.run_button = ttk.Button(frame, text="Run iPerf", command=self.start_iperf, style="TButton")
        self.run_button.grid(row=4, column=0, pady=(UI_PADY//2, 0))
        self.stop_button = ttk.Button(frame, text="Stop Test", command=self.stop_iperf, state="disabled", style="TButton")
        self.stop_button.grid(row=4, column=1, pady=(UI_PADY//2, 0))

        self.status_label = ttk.Label(root, text="", font=UI_FONT)
        self.status_label.pack()

        self.figure, self.ax = plt.subplots(figsize=FIGSIZE)
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack()

        self.iperf_thread = None
        self.stop_event = threading.Event()
        self.intervals = []

    def start_iperf(self):
        server = self.server_entry.get()
        port = int(self.port_entry.get())
        interval = int(self.interval_var.get())
        self.status_label.config(text="Running iPerf...")
        self.run_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.stop_event.clear()
        self.intervals = []
        self.ax.clear()
        self.canvas.draw()
        self.iperf_thread = threading.Thread(
            target=run_iperf_realtime,
            args=(server, port, interval, self.update_graph, self.display_result, self.stop_event),
            daemon=True
        )
        self.iperf_thread.start()

    def stop_iperf(self):
        self.status_label.config(text="Stopping test...")
        self.stop_event.set()
        self.stop_button.config(state="disabled")

    def update_graph(self, intervals):
        def update_ui():
            self.intervals = intervals
            x = [i+1 for i in range(len(intervals))]
            y = [interval["sum"]["bits_per_second"] / 1e6 for interval in intervals]
            self.ax.clear()
            self.ax.plot(x, y, marker="o")
            self.ax.set_xlabel("Interval")
            self.ax.set_ylabel("Throughput (Mbps)")
            self.ax.set_title("Network Throughput")
            self.ax.grid(True)
            self.canvas.draw()
        self.root.after(0, update_ui)

    def display_result(self, data):
        def update_ui():
            if "error" in data:
                self.status_label.config(text=f"Error: {data['error']}")
            else:
                self.status_label.config(text="Test finished.")
            self.run_button.config(state="normal")
            self.stop_button.config(state="disabled")
        self.root.after(0, update_ui)

class IperfServerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("iPerf Server - Status")

        frame = ttk.Frame(root)
        frame.pack(padx=UI_PADX, pady=UI_PADY)

        ttk.Label(frame, text="Port:", font=UI_FONT).grid(row=0, column=0, sticky="e")
        self.port_entry = ttk.Entry(frame, font=UI_FONT, width=18)
        self.port_entry.insert(0, "5201")
        self.port_entry.grid(row=0, column=1)

        self.start_button = ttk.Button(frame, text="Start Server", command=self.start_server, style="TButton")
        self.start_button.grid(row=1, column=0, pady=(UI_PADY//2, 0))
        self.stop_button = ttk.Button(frame, text="Stop Server", command=self.stop_server, state="disabled", style="TButton")
        self.stop_button.grid(row=1, column=1, pady=(UI_PADY//2, 0))

        self.status_label = ttk.Label(root, text="", font=UI_FONT)
        self.status_label.pack()

        self.server_thread = None
        self.stop_event = threading.Event()

    def start_server(self):
        port = int(self.port_entry.get())
        self.status_label.config(text="Starting server...")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.stop_event.clear()
        self.server_thread = threading.Thread(target=run_iperf_server, args=(port, self.display_status, self.stop_event), daemon=True)
        self.server_thread.start()

    def stop_server(self):
        self.status_label.config(text="Stopping server...")
        self.stop_event.set()
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def display_status(self, msg):
        def update_ui():
            self.status_label.config(text=msg)
        self.root.after(0, update_ui)

class ModeSelectionUI:
    def __init__(self, root):
        self.root = root
        self.root.title("iPerf Mode Selection")
        frame = ttk.Frame(root)
        frame.pack(padx=UI_PADX, pady=UI_PADY)
        ttk.Label(frame, text="Select Operation Mode:", font=UI_FONT).pack(pady=(0, UI_PADY))
        client_btn = ttk.Button(frame, text="Client", command=self.launch_client, style="TButton")
        client_btn.pack(fill="x", pady=(0, UI_PADY//2))
        server_btn = ttk.Button(frame, text="Server", command=self.launch_server, style="TButton")
        server_btn.pack(fill="x")
        self.frame = frame

    def launch_client(self):
        self.frame.destroy()
        IperfClientUI(self.root)

    def launch_server(self):
        self.frame.destroy()
        IperfServerUI(self.root)

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.configure("TButton", font=UI_FONT, padding=10)
    ModeSelectionUI(root)
    root.mainloop()
