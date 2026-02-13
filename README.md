# sakuraCast
### Cast the Planet!
Multiplatform Chromecast casting program written in Python using pychromecast, ffmpeg + yt-dlp, with a focus on casting local and online content in custom aspect ratios (ie; casting 4:3 content properly on 4:3 devices).

![](screenshots/1.png)

## Features:
- Support for custom aspect ratios, video resolutions, and framerates for local and online videos!
- Audio support! Cast music from your favourite (free) audio websites and local files!
- True 4:3 video support for Chromecast devices connected to 4:3 displays, no more letterboxing! (Select 640x480 + Widescreen for the best results on a CRT!)
- Overscan support!
- Queue local and online videos so you can sit back, relax, and marathon your favourite movies and shows hassle-free!
- Casting support from any yt-dlp supported site, with resolution-specific video grabbing, meaning you can save bandwith and computational resources at lower resolutions! (WIP)
- Integrate subtitles directly into any video being cast, including a mode optimized for 4:3 CRTs when set to 640x480!
- Multiplatform support! (Tested in Linux & macOS, should work on Windows!)

## Requirements:
- Decent PC capable of transcoding (will fall back to software if hardware transcoding isn't available, but it won't be pretty). With h264_vaapi on Linux, casting 640x480 Widescreen 30FPS video to a 1st Gen Chromecast, uses approximately 10% of my i7-6500U CPU.
- Google Chromecast (made with first-gen Chromecasts in mind, but will work on any model!)

## How to use:
- Download the latest release of sakuraCast
- Install ffmpeg if not already installed (macOS: ``` brew install ffmpeg ``` or ``` sudo port install ffmpeg ``` ) (Arch: ``` sudo pacman -S ffmpeg ```) (Debian/Ubuntu: ``` sudo apt install ffmpeg ```)
- Install python-tk, python-pychromecast & yt-dlp (``` pip install pychromecast ``` + ``` pip install tk ``` + ``` pip install yt-dlp ```)
- Open it and select your video file(s) or enter your video URL (URLs that end with file extensions or YouTube only!)
- Select your subtitles, if required. If subtitles are found in the video container or share the same name as the video file, they'll show up automatically!
- Select the Chromecast you'd like to cast the video to, and the aspect ratio you'd like to cast in (select 16/9 if you're using a 16/9 display or casting 4:3 content to a 4:3 display, use 4/3 if you're casting 4:3 content to a 16:9 display) as well as the resolution (and framerate if applicable). Note that the higher the resolution/framerate, the higher the system usage on your host PC.
- Select "Cast" and you're all set! This script will detect if you have hardware acceleration and use that to transcode the video, otherwise, will fall back to software transcoding.

## FAQ:
- "How do I properly cast to my 4:3 display?"
- Select "640x480" for the resolution (optional, but recommended) and set "Widescreen" as the aspect ratio. It sounds counter-intuitive, but by default, the CC displays a 16:9 image and puts black bars around 4:3 content, so "Widescreen" transcodes 4:3 to 16:9, therefore making it 4:3 again 4:3 displays.
- "How do I import a playlist?"
- Copy the URL and it'll automatically populate the playlist queue! Alternatively, you can import m3u/m3u8 playlists or manually select all the files you'd like to add to queue, set your cast settings, and enjoy!
- "How do I improve my video quality?"
- You can select a higher resolution and framerate in the settings! Note that higher resolutions/framerates will require more network bandwidth and processing power, and may lead to buffering issues on weaker hardware.
- "My yt-dlp video failed to cast!"
- Try again. Sometimes, randomly, yt-dlp videos fail to cast the first time, restart the app and try again.
- "Can this use (XYZ service)?"
- Nope, only local files and DRM-free websites supported by yt-dlp are supported, sorry!

## Bugs:
- Seeking is a bit glitchy in the UI, but works. Seeking doesn't work in Google Home, unfortunately.
- Thumbnail image doesn't work in Google Home
- Sometimes stopping a stream requires a restart of the script.

## TODO:
- [ ] Fix Google Home images (fixed for audio, still buggy for video)
- [ ] Add more customization options for ffmpeg backend
- [ ] Add more subtitle options
- [ ] Improve video URL + yt-dlp support and auth challenges (working: YouTube, Tumblr, Reddit)
- [ ] Optimizations and bugfixes
- [ ] Fix cast metadata overall
- [ ] Implement a webserver for sending files and URLs and commands to(?)
