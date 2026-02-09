import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pychromecast
import socket
import socketserver
import http.server
import subprocess
import time
from collections import deque

VIDEO_MIME = "video/mp4"

BG_COLOR = "#1e1e1e"
FG_COLOR = "#e0e0e0"
ACCENT_COLOR = "#F8C8DC"
SECONDARY_BG = "#2d2d2d"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def format_time(seconds):
    try:
        seconds = int(float(seconds))
        return time.strftime('%H:%M:%S', time.gmtime(max(0, seconds)))
    except:
        return "00:00:00"

class FFmpegStreamHandler(http.server.BaseHTTPRequestHandler):
    video_file = None
    subtitle_file = None
    seek_time = 0 
    encoder = "libx264"
    hw_args = []
    aspect_ratio = "16/9"

    def do_GET(self):
        clean_path = self.path.split('?')[0]

        if clean_path == "/thumb.jpg":
            if os.path.exists("thumb.jpg"):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open("thumb.jpg", "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404)
                return

        if not clean_path.startswith("/stream.mp4"):
            self.send_error(404)
            return
        
        sub_filter = ""
        if self.subtitle_file and os.path.exists(self.subtitle_file):
            escaped_path = self.subtitle_file.replace("\\", "/").replace(":", "\\:")
            offset = self.seek_time
            crt_style = (
                "force_style='Alignment=2,Outline=1,Shadow=1,BorderStyle=4,"
                "BackColour=&H80000000,Spacing=0.2,MarginV=15,FontSize=20,Bold=1'"
            )
            sub_filter = f"setpts=PTS+{offset}/TB,subtitles='{escaped_path}':{crt_style},setpts=PTS-{offset}/TB,"

        ar = self.aspect_ratio 
        
        if ar == "4/3":
            res = "640:480"
            target_dar = "4/3"
        else:
            res = "1280:720"
            target_dar = "16/9"

        if "vaapi" in self.encoder:
            v_filter = f"format=nv12,{sub_filter}hwupload,scale_vaapi=w={res.split(':')[0]}:h={res.split(':')[1]},setsar=1,setdar={target_dar}"
        elif "nvenc" in self.encoder:
            v_filter = f"{sub_filter}scale={res},setsar=1,setdar={target_dar}"
        else:
            v_filter = f"{sub_filter}scale={res},setsar=1,setdar={target_dar},format=yuv420p"

        ffmpeg_cmd = [
            "ffmpeg", "-ss", str(self.seek_time), "-i", self.video_file
        ] + self.hw_args + [
            "-vf", v_filter,
            "-c:v", self.encoder,
            "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "mp4", 
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"
        ]

        self.send_response(200)
        self.send_header("Content-Type", VIDEO_MIME)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=None, bufsize=10**6)
        
        try:
            while True:
                chunk = proc.stdout.read(64*1024)
                if not chunk: break
                self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            proc.kill()

class ChromecastGui:
    def __init__(self, root):
        self.root = root
        self.root.title("sakuraCast")
        self.root.geometry("600x820")
        self.root.configure(bg=BG_COLOR)
        
        self.server = None
        self.cast_device = None
        self.browser = None
        self.chromecasts = []
        self.queue = deque()
        self.is_playing = False
        self.current_video_duration = 0
        self.manual_seek_cooldown = 0
        self.seek_lock_time = 0 
        self.seeking = False
        
        self.apply_styles()
        self.setup_ui()
        self.discover_chromecasts()
        self.detect_hardware_acceleration()
        self.selected_subtitles = None

    def generate_thumbnail(self, video_path):
        cmd = ["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:05", "-vframes", "1", "-q:v", "2", "thumb.jpg"]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Thumbnail failed: {e}")

    def load_subtitles(self):
        file = filedialog.askopenfilename(filetypes=[("Subtitle files", "*.srt")])
        if file:
            self.selected_subtitles = file
            self.sub_var.set(os.path.basename(file))
            FFmpegStreamHandler.subtitle_file = file

    def detect_hardware_acceleration(self):
            if self.test_ffmpeg_encoder("h264_vaapi", ["-vaapi_device", "/dev/dri/renderD128", "-vf", "format=nv12,hwupload"]):
                FFmpegStreamHandler.encoder = "h264_vaapi"
                FFmpegStreamHandler.hw_args = ["-vaapi_device", "/dev/dri/renderD128"]
                return

            if self.test_ffmpeg_encoder("h264_nvenc"):
                FFmpegStreamHandler.encoder = "h264_nvenc"
                FFmpegStreamHandler.hw_args = []
                return
            
            FFmpegStreamHandler.encoder = "libx264"
            FFmpegStreamHandler.hw_args = []

    def test_ffmpeg_encoder(self, encoder_name, extra_args=[]):
        test_cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x480", "-frames:v", "1"] + extra_args + ["-c:v", encoder_name, "-f", "null", "-"]
        try:
            res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
        except: return False

    def apply_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=FG_COLOR, font=('Helvetica', 10))
        style.configure("TLabelframe", background=BG_COLOR, foreground=ACCENT_COLOR)
        style.configure("TLabelframe.Label", background=BG_COLOR, foreground=ACCENT_COLOR, font=('Helvetica', 10, 'bold'))
        style.configure("TButton", background=SECONDARY_BG, foreground=FG_COLOR)
        style.map("TButton", background=[('active', ACCENT_COLOR)], foreground=[('active', BG_COLOR)])
        style.configure("TScale", background=BG_COLOR, troughcolor=SECONDARY_BG)
        style.configure("TCombobox", fieldbackground=SECONDARY_BG, background=SECONDARY_BG, foreground=FG_COLOR, arrowcolor=ACCENT_COLOR,bordercolor=SECONDARY_BG)  
        style.map("TCombobox", fieldbackground=[('readonly', SECONDARY_BG)],foreground=[('readonly', FG_COLOR)])

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="sakuraCast v1.0\n", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.CENTER)

        try:
            icon_image = tk.PhotoImage(file="sakura.png")
            self.root.iconphoto(False, icon_image)
            self.icon_img = tk.PhotoImage(file="sakura.png").subsample(5)
            self.icon_label = ttk.Label(main_frame, image=self.icon_img)
            self.icon_label.pack(anchor=tk.CENTER, pady=(0, 10))
    
        except Exception as e:
            print(f"Could not load sakura.png: {e}")

        ttk.Label(main_frame, text="Queue", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.CENTER)
        self.queue_listbox = tk.Listbox(main_frame, bg=SECONDARY_BG, fg=FG_COLOR, selectbackground=ACCENT_COLOR, selectforeground=BG_COLOR, borderwidth=0, height=6)
        self.queue_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        self.root.option_add("*TCombobox*Listbox.background", SECONDARY_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", FG_COLOR)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_COLOR)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG_COLOR)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Add to Queue", command=self.add_to_queue).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="Clear Queue", command=self.clear_queue).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        sub_frame = ttk.LabelFrame(main_frame, text="Subtitles (Optional)", padding=10, labelanchor='n')
        sub_frame.pack(fill=tk.X, pady=10)
        self.sub_var = tk.StringVar(value="No subtitles selected")
        ttk.Label(sub_frame, textvariable=self.sub_var, font=('Helvetica', 9, 'italic')).pack(side=tk.LEFT, expand=True)
        ttk.Button(sub_frame, text="Load SRT", command=self.load_subtitles).pack(side=tk.RIGHT)

        ttk.Label(main_frame, text="Chromecast", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.N, pady=(10,0))
        self.device_list = tk.Listbox(main_frame, bg=SECONDARY_BG, fg=FG_COLOR, borderwidth=0, height=3)
        self.device_list.pack(fill=tk.X, pady=5)

        ttk.Label(main_frame, text="Aspect Ratio", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.N, pady=(10,0))
        self.ar_options = {
            "4/3 (select for 4:3 on 16:9 displays)": "4/3",
            "16/9 (select for 4:3 on 4:3 displays)": "16/9"
        }
        
        self.ar_display_var = tk.StringVar(value="16/9 (select for 4:3 on 4:3 displays)")
        self.ar_combo = ttk.Combobox(main_frame, textvariable=self.ar_display_var, values=list(self.ar_options.keys()), state="readonly")
        self.ar_combo.pack(fill=tk.X, pady=5)
        self.ar_combo.bind("<<ComboboxSelected>>", self.update_ar)
        
        FFmpegStreamHandler.aspect_ratio = "4/3"

        play_frame = ttk.LabelFrame(main_frame, text="Playback Control", padding=10, labelanchor='n')
        play_frame.pack(fill=tk.X, pady=10)

        self.title_var = tk.StringVar(value="No file playing")
        ttk.Label(play_frame, textvariable=self.title_var, font=('Helvetica', 10, 'italic'), foreground=ACCENT_COLOR).pack(anchor=tk.W)

        time_frame = ttk.Frame(play_frame)
        time_frame.pack(fill=tk.X)
        self.time_elapsed_var = tk.StringVar(value="00:00:00")
        self.time_total_var = tk.StringVar(value="00:00:00")
        ttk.Label(time_frame, textvariable=self.time_elapsed_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, textvariable=self.time_total_var).pack(side=tk.RIGHT)

        self.seek_var = tk.DoubleVar()
        self.seek_slider = ttk.Scale(play_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.seek_var)
        self.seek_slider.pack(fill=tk.X, pady=5)
        self.seek_slider.bind("<Button-1>", self.on_seek_start)
        self.seek_slider.bind("<ButtonRelease-1>", self.on_seek_release)

        ctrl_buttons = ttk.Frame(play_frame)
        ctrl_buttons.pack(fill=tk.X)
        self.btn_cast = ttk.Button(ctrl_buttons, text="Cast", command=self.start_playback, state=tk.DISABLED)
        self.btn_cast.pack(side=tk.LEFT, padx=2)
        self.btn_stop = ttk.Button(ctrl_buttons, text="Stop", command=self.stop_cast, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_buttons, text="Skip", command=self.skip_video).pack(side=tk.LEFT, padx=2)


        ttk.Label(ctrl_buttons, text=" Vol:", foreground=FG_COLOR).pack(side=tk.LEFT)
        self.vol_scale = ttk.Scale(ctrl_buttons, from_=0, to=1, orient=tk.HORIZONTAL, command=self.set_volume)
        self.vol_scale.set(1)
        self.vol_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.status_var = tk.StringVar(value="Searching for device(s)...")
        ttk.Label(main_frame, textvariable=self.status_var, foreground="#F8C8DC").pack(pady=5)
        ttk.Label(main_frame, text="Made with love by faithvoid <3", foreground="#F8C8DC").pack(pady=5)

    def update_ar(self, event=None):
        display_val = self.ar_display_var.get()
        internal_val = self.ar_options.get(display_val, "4/3")
        
        FFmpegStreamHandler.aspect_ratio = internal_val
        
        if self.is_playing:
            self.on_seek_release(None)

    def get_duration(self, filename):
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
            return float(result.stdout.strip())
        except: return 0

    def add_to_queue(self):
        filenames = filedialog.askopenfilenames(filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov")])
        for f in filenames:
            self.queue.append(f)
            self.queue_listbox.insert(tk.END, os.path.basename(f))

    def clear_queue(self):
        self.queue.clear()
        self.queue_listbox.delete(0, tk.END)

    def discover_chromecasts(self):
        def task():
            self.chromecasts, self.browser = pychromecast.get_chromecasts()
            self.device_list.delete(0, tk.END)
            for cc in self.chromecasts: self.device_list.insert(tk.END, cc.name)
            self.status_var.set(f"Found {len(self.chromecasts)} device(s).")
            self.btn_cast.config(state=tk.NORMAL)
        threading.Thread(target=task, daemon=True).start()

    def on_seek_start(self, event):
        self.seeking = True

    def on_seek_release(self, event):
        if self.cast_device and self.is_playing:
            new_time = self.seek_var.get()
            FFmpegStreamHandler.seek_time = int(new_time)
            self.manual_seek_cooldown = time.time() + 5
            self.seek_lock_time = time.time() + 8
            local_ip = get_local_ip()
            stream_url = f"http://{local_ip}:8000/stream.mp4?t={time.time()}"
            display_title = os.path.basename(FFmpegStreamHandler.video_file)
            self.cast_device.media_controller.play_media(stream_url, content_type=VIDEO_MIME, title=display_title)
        self.seeking = False

    def skip_video(self):
        if self.cast_device:
            self.seek_lock_time = 0 
            self.cast_device.media_controller.stop()

    def set_volume(self, val):
        if self.cast_device: self.cast_device.set_volume(float(val))

    def stop_cast(self):
        self.is_playing = False
        self.title_var.set("No file playing")
        if self.cast_device: self.cast_device.media_controller.stop()
        if self.server: self.server.shutdown()
        self.status_var.set("Stopped.")
        self.btn_cast.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def start_playback(self):
        selection = self.device_list.curselection()
        if not selection or not self.queue: return
        self.cast_device = self.chromecasts[selection[0]]
        self.is_playing = True
        self.btn_cast.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        threading.Thread(target=self.playback_loop, daemon=True).start()

    def playback_loop(self):
        try:
            self.cast_device.wait()
            local_ip = get_local_ip()
            while self.is_playing and self.queue:
                video_path = self.queue.popleft()
                self.queue_listbox.delete(0)
                self.generate_thumbnail(video_path)
                self.title_var.set(f"Now Playing: {os.path.basename(video_path)}")
                self.current_video_duration = self.get_duration(video_path)
                self.root.after(0, lambda d=self.current_video_duration: self.seek_slider.config(to=int(d) if d > 0 else 100))
                self.root.after(0, lambda d=self.current_video_duration: self.time_total_var.set(format_time(d)))
                FFmpegStreamHandler.video_file = video_path
                FFmpegStreamHandler.seek_time = 0
                self.seek_var.set(0)
                if not self.server:
                    self.server = socketserver.ThreadingTCPServer(("0.0.0.0", 8000), FFmpegStreamHandler)
                    threading.Thread(target=self.server.serve_forever, daemon=True).start()
                mc = self.cast_device.media_controller
                mc.play_media(f"http://{local_ip}:8000/stream.mp4", content_type=VIDEO_MIME, title=os.path.basename(video_path), metadata={'metadataType': 1, 'title': os.path.basename(video_path), 'images': [{'url': f"http://{local_ip}:8000/thumb.jpg"}]})
                time.sleep(3) 
                while self.is_playing:
                    if mc.status.player_state == "IDLE" and time.time() > self.seek_lock_time: break
                    if not self.seeking and time.time() > self.manual_seek_cooldown:
                        cc_time = mc.status.current_time if mc.status.current_time else 0
                        current_pos = FFmpegStreamHandler.seek_time + cc_time
                        self.root.after(0, lambda p=current_pos: self.seek_var.set(p))
                        self.root.after(0, lambda p=current_pos: self.time_elapsed_var.set(format_time(p)))
                    time.sleep(1)
            if not self.queue: self.stop_cast()
        except Exception as e: print(f"Error in playback loop: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChromecastGui(root)
    root.mainloop()
