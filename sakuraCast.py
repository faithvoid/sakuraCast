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
import platform
import yt_dlp
import webbrowser
import requests
import glob

VIDEO_MIME = "video/mp4"

BG_COLOR = "#1e1e1e"
FG_COLOR = "#e0e0e0"
ACCENT_COLOR = "#F8C8DC"
SECONDARY_BG = "#2d2d2d"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(SCRIPT_DIR, "sakura.png")
VERSION = "0.99"

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
    headers_dict = {}
    encoder = "libx264"
    hw_args = []
    aspect_ratio = "16/9"
    resolution = "640x480"

    def do_GET(self):
        clean_path = self.path.split('?')[0]

        if clean_path == "/thumb.jpg":
            thumb_path = os.path.join(SCRIPT_DIR, "thumb.jpg")
            if os.path.exists(thumb_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(thumb_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404)
                return

        if not clean_path.startswith("/stream.mp4"):
            self.send_error(404)
            return
        
        sub_filter = ""
        sub_file = self.subtitle_file
        
        if sub_file:
            offset = self.seek_time
            crt_style = ("force_style='Alignment=2,Outline=1,Shadow=1,BorderStyle=4,""BackColour=&H80000000,Spacing=0.2,MarginV=15,FontSize=20,Bold=1'")
            
            if sub_file.startswith("internal:"):
                stream_idx = sub_file.split(":")[1]
                escaped_vid = self.video_file.replace("\\", "/").replace(":", "\\:")
                sub_filter = f"setpts=PTS+{offset}/TB,subtitles='{escaped_vid}':si={stream_idx}:{crt_style},setpts=PTS-{offset}/TB,"
            elif os.path.exists(sub_file):
                escaped_path = sub_file.replace("\\", "/").replace(":", "\\:")
                sub_filter = f"setpts=PTS+{offset}/TB,subtitles='{escaped_path}':{crt_style},setpts=PTS-{offset}/TB,"

        res = FFmpegStreamHandler.resolution
        target_dar = self.aspect_ratio
        res_w, res_h = res.split('x')

        if "vaapi" in self.encoder:
            v_filter = f"format=nv12,{sub_filter}hwupload,scale_vaapi=w={res_w}:h={res_h},setsar=1,setdar={target_dar}"
        elif "videotoolbox" in self.encoder:
            v_filter = f"{sub_filter}scale={res_w}:{res_h},setsar=1,setdar={target_dar}"
            v_filter = f"{sub_filter}scale={res_w}:{res_h},setsar=1,setdar={target_dar},format=yuv420p"

        extra_input_args = []
        if self.headers_dict:
            header_str = "".join([f"{k}: {v}\r\n" for k, v in self.headers_dict.items()])
            
            extra_input_args = [
                "-headers", header_str,
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5"
            ]

        ffmpeg_cmd = [
            "ffmpeg", "-ss", str(self.seek_time)
        ] + self.hw_args + extra_input_args + [
            "-i", self.video_file,
            "-vf", v_filter,
            "-c:v", self.encoder,
            "-preset", "ultrafast" if "libx264" in self.encoder else "fast",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "mp4", 
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"
        ]

        self.send_response(200)
        self.send_header("Content-Type", VIDEO_MIME)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        proc = subprocess.Popen(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            bufsize=10**6
        )

        def log_reader(pipe):
            with pipe:
                for line in iter(pipe.readline, b''):
                    print(f"[FFmpeg Log]: {line.decode('utf-8', errors='replace').strip()}")

        threading.Thread(target=log_reader, args=(proc.stderr,), daemon=True).start()
        
        try:
            while True:
                chunk = proc.stdout.read(64*1024)
                if not chunk: break
                self.wfile.write(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            proc.terminate()

class ChromecastGui:
    def __init__(self, root):
        self.root = root
        self.root.title(f"sakuraCast")
        self.root.geometry("600x940")
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
        self.check_for_update()
        self.discover_chromecasts()
        self.detect_hardware_acceleration()
        self.detected_subs = {"None": None}
        self.selected_subtitles = None

    def check_for_update(self):
        version_url = "https://raw.githubusercontent.com/faithvoid/sakuraCast/refs/heads/main/version.txt"
        try:
            response = requests.get(version_url)
            if response.status_code == 200:
                remote_version = response.text.strip()
                if remote_version != VERSION:
                    self.display_update_available()
                    print(f"Remote version: {remote_version}")

        except Exception as e:
            print(f"Error checking for update: {e}")

    def display_update_available(self):
        update_frame = ttk.Frame(self.root)
        update_frame.pack(anchor=tk.CENTER)

        update_label = ttk.Label(update_frame, text="Update Available!", foreground=ACCENT_COLOR, font=('Helvetica', 10, 'bold'))
        update_label.pack()

        update_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/faithvoid/sakuraCast"))


    def generate_thumbnail(self, video_path):
        thumb_path = os.path.join(SCRIPT_DIR, "thumb.jpg")
        cmd = ["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:05", "-vframes", "1", "-q:v", "2", thumb_path]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass

    def detect_hardware_acceleration(self):
        system = platform.system()
        found_hw = False

        if system == "Windows":
            for enc in ["h264_nvenc", "h264_qsv", "h264_amf"]:
                if self.test_ffmpeg_encoder(enc):
                    FFmpegStreamHandler.encoder = enc
                    found_hw = True
                    break
        
        elif system == "Darwin":
            if self.test_ffmpeg_encoder("h264_videotoolbox"):
                FFmpegStreamHandler.encoder = "h264_videotoolbox"
                found_hw = True

        elif system in ["Linux", "FreeBSD"]:
            va_args = ["-vaapi_device", "/dev/dri/renderD128", "-vf", "format=nv12,hwupload"]
            if os.path.exists("/dev/dri/renderD128"):
                if self.test_ffmpeg_encoder("h264_vaapi", va_args):
                    FFmpegStreamHandler.encoder = "h264_vaapi"
                    FFmpegStreamHandler.hw_args = ["-vaapi_device", "/dev/dri/renderD128"]
                    found_hw = True
            
            if not found_hw and self.test_ffmpeg_encoder("h264_nvenc"):
                FFmpegStreamHandler.encoder = "h264_nvenc"
                found_hw = True

        if not found_hw:
            FFmpegStreamHandler.encoder = "libx264"
            FFmpegStreamHandler.hw_args = []
        
        self.status_var.set(f"Encoder: {FFmpegStreamHandler.encoder}")
        print(f"OS: {system} | Selected: {FFmpegStreamHandler.encoder}")

    def test_ffmpeg_encoder(self, encoder_name, extra_args=[]):
        test_cmd = [
            "ffmpeg", "-y", 
            "-f", "lavfi", "-i", "color=c=black:s=640x480", 
            "-frames:v", "1"
        ] + extra_args + ["-c:v", encoder_name, "-f", "null", "-"]
        
        try:
            res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
        except: 
            return False

    def scan_for_subtitles(self, video_path):
        self.detected_subs = {"None": None}
        if not video_path or isinstance(video_path, dict):
            self.update_sub_combo()
            return

        internal_subs = self.get_internal_subtitles(video_path)
        for idx, label in internal_subs:
            self.detected_subs[label] = f"internal:{idx}"

        base_path = os.path.splitext(video_path)[0]
        files = glob.glob(f"{glob.escape(base_path)}*.srt")
        for f in files:
            self.detected_subs[os.path.basename(f)] = f
        
        self.update_sub_combo()

    def get_internal_subtitles(self, video_path):
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "s", 
            "-show_entries", "stream=index:stream_tags=language,title", 
            "-of", "csv=p=0", video_path
        ]
        subs = []
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=5)
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(',')
                    index = parts[0]
                    label = next((p for p in parts[1:] if p), f"Stream {index}")
                    subs.append((index, f"Internal: {label}"))
        except: pass
        return subs

    def update_sub_combo(self):
        self.sub_combo['values'] = list(self.detected_subs.keys())
        if len(self.detected_subs) > 1:
            subs_only = [k for k in self.detected_subs.keys() if k != "None"]
            first_sub = subs_only[0]
            self.sub_selection_var.set(first_sub)
            FFmpegStreamHandler.subtitle_file = self.detected_subs[first_sub]
        else:
            self.sub_selection_var.set("None")
            FFmpegStreamHandler.subtitle_file = None

    def on_subtitle_selected(self, event=None):
        selected = self.sub_selection_var.get()
        FFmpegStreamHandler.subtitle_file = self.detected_subs.get(selected)
        if self.is_playing:
            self.on_seek_release(None)

    def load_subtitles(self):
        file = filedialog.askopenfilename(filetypes=[("Subtitle files", "*.srt *.ass")])
        if file:
            label = f"[Manual] {os.path.basename(file)}"
            self.detected_subs[label] = file
            self.update_sub_combo()
            self.sub_selection_var.set(label)
            FFmpegStreamHandler.subtitle_file = file
            if self.is_playing:
                self.on_seek_release(None)

    def apply_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=FG_COLOR, font=('Helvetica', 10))
        style.configure("TLabelframe", background=BG_COLOR, foreground=ACCENT_COLOR)
        style.configure("TLabelframe.Label", background=BG_COLOR, foreground=ACCENT_COLOR, font=('Helvetica', 10, 'bold'))
        style.configure("TButton", background=SECONDARY_BG, foreground=FG_COLOR)
        style.map("TButton", background=[('active', ACCENT_COLOR)], foreground=[('active', BG_COLOR)])
        style.configure("TScale", background=BG_COLOR, troughcolor=SECONDARY_BG)
        style.configure("TCombobox", fieldbackground=SECONDARY_BG, background=SECONDARY_BG, foreground=FG_COLOR, arrowcolor=ACCENT_COLOR,bordercolor=SECONDARY_BG)  
        style.map("TCombobox", fieldbackground=[('readonly', SECONDARY_BG)],foreground=[('readonly', FG_COLOR)])
        style.configure("TEntry", fieldbackground=SECONDARY_BG, foreground=FG_COLOR, insertcolor=ACCENT_COLOR, bordercolor=SECONDARY_BG)
        style.configure("TLabelframe", background=BG_COLOR, foreground=ACCENT_COLOR)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text=f"sakuraCast [v{VERSION}]", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.CENTER)

        try:
            icon_image = tk.PhotoImage(file=ICON)
            self.root.iconphoto(False, icon_image)
            self.icon_img = tk.PhotoImage(file=ICON).subsample(5)
            self.icon_label = ttk.Label(main_frame, image=self.icon_img)
            self.icon_label.pack(anchor=tk.CENTER)
    
        except Exception as e:
            print(f"Could not load sakura.png: {e}")

        ttk.Label(main_frame, text="Queue", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.CENTER)
        self.queue_listbox = tk.Listbox(main_frame, bg=SECONDARY_BG, fg=FG_COLOR, selectbackground=ACCENT_COLOR, selectforeground=BG_COLOR, borderwidth=0, height=6)
        self.queue_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        url_frame = ttk.LabelFrame(main_frame, text="Video URL (Direct link or YouTube)", labelanchor='n')
        url_frame.pack(fill=tk.X, pady=5)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        ttk.Button(url_frame, text="Add URL", command=self.add_url_to_queue).pack(side=tk.RIGHT, padx=5)

        self.root.option_add("*TCombobox*Listbox.background", SECONDARY_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", FG_COLOR)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_COLOR)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG_COLOR)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Add to Queue", command=self.add_to_queue).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="Clear Queue", command=self.clear_queue).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        sub_frame = ttk.LabelFrame(main_frame, text="Subtitles", labelanchor='n')
        sub_frame.pack(fill=tk.X, pady=10)
        
        self.detected_subs = {"None": None}
        self.sub_selection_var = tk.StringVar(value="None")
        self.sub_combo = ttk.Combobox(sub_frame, textvariable=self.sub_selection_var, state="readonly")
        self.sub_combo.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.sub_combo.bind("<<ComboboxSelected>>", self.on_subtitle_selected)

        ttk.Button(sub_frame, text="Browse...", command=self.load_subtitles).pack(side=tk.RIGHT)

        ttk.Label(main_frame, text="Chromecast", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.N)
        self.device_list = tk.Listbox(main_frame, bg=SECONDARY_BG, fg=FG_COLOR, borderwidth=0, height=3)
        self.device_list.pack(fill=tk.X, pady=5)

        ttk.Label(main_frame, text="Resolution", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.N)
        
        self.res_options = ["640x480", "1280x720", "1920x1080"]
        self.res_display_var = tk.StringVar(value=self.res_options[0])
        self.res_combo = ttk.Combobox(main_frame, textvariable=self.res_display_var, values=self.res_options, state="readonly")
        self.res_combo.pack(fill=tk.X, pady=5)
        self.res_combo.bind("<<ComboboxSelected>>", self.update_res)
        
        FFmpegStreamHandler.resolution = self.res_display_var.get()

        ttk.Label(main_frame, text="Aspect Ratio", font=('Helvetica', 10, 'bold'), foreground=ACCENT_COLOR).pack(anchor=tk.N)
        self.ar_options = {
            "Widescreen (16:9)": "16/9",
            "Fullscreen (4:3)": "4/3",
            "Vertical (9:16)": "9/16"
        }
        self.ar_display_var = tk.StringVar(value="Widescreen (16:9)")
        self.ar_combo = ttk.Combobox(main_frame, textvariable=self.ar_display_var, values=list(self.ar_options.keys()), state="readonly")
        self.ar_combo.pack(fill=tk.X, pady=5)
        self.ar_combo.bind("<<ComboboxSelected>>", self.update_ar)
        
        FFmpegStreamHandler.aspect_ratio = self.ar_options[self.ar_display_var.get()]

        play_frame = ttk.LabelFrame(main_frame, text="Playback Control",labelanchor='n')
        play_frame.pack(fill=tk.X, pady=5)

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
        ctrl_buttons.pack(fill=tk.X, pady=5)
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
        line_frame = ttk.Frame(main_frame)
        line_frame.pack(pady=5)

        ttk.Label(line_frame, text="made with love by faithvoid @", foreground="#F8C8DC").pack(side="left")

        url_label = ttk.Label(line_frame, text="faithvoid.github.io", foreground="#F8C8DC", cursor="hand2")
        url_label.pack(side="left")

        kofi_frame = ttk.Frame(main_frame)
        kofi_frame.pack()

        url_label_ko_fi = ttk.Label(kofi_frame, text="ko-fi", foreground="#F8C8DC", cursor="hand2")
        url_label_ko_fi.pack()

        url_label_ko_fi.bind("<Button-1>", lambda e: webbrowser.open("https://ko-fi.com/videogirl95"))

    def update_ar(self, event=None):
        display_val = self.ar_display_var.get()
        internal_val = self.ar_options.get(display_val, "16/9")
        
        FFmpegStreamHandler.aspect_ratio = internal_val
        
        if self.is_playing:
            self.on_seek_release(None)

    def update_res(self, event=None):
        FFmpegStreamHandler.resolution = self.res_display_var.get()
        print(f"Resolution updated to: {FFmpegStreamHandler.resolution}")

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

    def add_url_to_queue(self):
        url = self.url_var.get().strip()
        if not url: return
        
        def process_url():
            self.status_var.set("Processing URL...")
            try:
                ydl_opts = {
                    'format': 'bestvideo+bestaudio/best/b',
                    'ignoreerrors': True,
                    'nocheckcertificate': True,
                    'quiet': False,
                    'no_warnings': False,
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'extractor_args': {
                        'youtube': {'player_client': ['android', 'web']},
                        'nicovideo': {'player_client': ['watch_os', 'pc']}
                    }
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                    if 'formats' in info:
                        best_format = max(info['formats'], key=lambda f: f.get('height', 0) or 0)
                        video_url = best_format['url']
                    else:
                        video_url = info['url']

                    self.queue.append({
                        'path': video_url,
                        'title': info.get('title', 'Web Video'),
                        'duration': info.get('duration', 0)
                    })

                    self.root.after(0, lambda t=info.get('title', 'Web Video'): self.queue_listbox.insert(tk.END, f"[URL] {t}"))
                    self.url_var.set("")
                    self.status_var.set("URL added to queue.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not process URL: {e}")
                self.status_var.set("URL processing failed.")

        threading.Thread(target=process_url, daemon=True).start()

    def clear_queue(self):
        self.queue.clear()
        self.queue_listbox.delete(0, tk.END)

    def discover_chromecasts(self):
        def task():
            self.chromecasts, self.browser = pychromecast.get_chromecasts()
            self.device_list.delete(0, tk.END)
            for cc in self.chromecasts: self.device_list.insert(tk.END, cc.name)
            self.status_var.set(f"Found {len(self.chromecasts)} Chromecast(s).")
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

        self.root.title(f"sakuraCast")
    
        self.status_var.set("Stopped.")
        self.btn_cast.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def start_playback(self):
        if self.is_playing:
            self.stop_cast()
            time.sleep(0.5)
        
        selection = self.device_list.curselection()
        if not selection or not self.queue: return
    
        self.cast_device = self.chromecasts[selection[0]]
        self.is_playing = True
        self.btn_cast.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        threading.Thread(target=self.playback_loop, daemon=True).start()

        display_name = self.queue[0]['title'] if isinstance(self.queue[0], dict) else os.path.basename(self.queue[0])
        self.root.title(f"sakuraCast - {display_name}")

    def playback_loop(self):
        try:
            self.cast_device.wait()
            local_ip = get_local_ip()
            while self.is_playing and self.queue:
                item = self.queue.popleft()
                self.queue_listbox.delete(0)

                FFmpegStreamHandler.subtitle_file = None
                FFmpegStreamHandler.seek_time = 0
                self.root.after(0, lambda: self.sub_selection_var.set("None"))

                if isinstance(item, dict):
                    video_path = item['path']
                    display_name = item['title']
                    duration = item.get('duration', 0)
                    FFmpegStreamHandler.headers_dict = item.get('headers', {}) 
                else:
                    video_path = item
                    display_name = os.path.basename(item)
                    self.root.after(0, lambda p=video_path: self.scan_for_subtitles(p))
                    duration = self.get_duration(item)
                    FFmpegStreamHandler.headers_dict = {}

                if not isinstance(item, dict):
                    self.generate_thumbnail(video_path)
                
                self.title_var.set(f"Now Playing: {display_name}")
                self.current_video_duration = duration
                
                self.root.after(0, lambda d=self.current_video_duration: self.seek_slider.config(to=int(d) if d > 0 else 100))
                self.root.after(0, lambda d=self.current_video_duration: self.time_total_var.set(format_time(d)))

                FFmpegStreamHandler.video_file = video_path
                FFmpegStreamHandler.seek_time = 0
                self.seek_var.set(0)

                if not self.server:
                    self.server = socketserver.ThreadingTCPServer(("0.0.0.0", 8000), FFmpegStreamHandler)
                    threading.Thread(target=self.server.serve_forever, daemon=True).start()

                mc = self.cast_device.media_controller
                mc.play_media(
                    f"http://{local_ip}:8000/stream.mp4", 
                    content_type=VIDEO_MIME, 
                    title=display_name, 
                    metadata={
                        'metadataType': 1, 
                        'title': display_name, 
#                        'images': [{'url': f"http://{local_ip}:8000/thumb.jpg"}]
                    }
                )

                time.sleep(3) 
                while self.is_playing:
                    if mc.status.player_state == "IDLE" and time.time() > self.seek_lock_time: 
                        break
                    if not self.seeking and time.time() > self.manual_seek_cooldown:
                        cc_time = mc.status.current_time if mc.status.current_time else 0
                        current_pos = FFmpegStreamHandler.seek_time + cc_time
                        self.root.after(0, lambda p=current_pos: self.seek_var.set(p))
                        self.root.after(0, lambda p=current_pos: self.time_elapsed_var.set(format_time(p)))
                    time.sleep(1)

            if not self.queue: 
                self.stop_cast()
        except Exception as e: 
            print(f"Error in playback loop: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChromecastGui(root)
    root.mainloop()
