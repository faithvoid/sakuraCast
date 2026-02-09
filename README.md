# sakuraCast
Chromecast casting program written in Python, with focus on custom aspect ratio support (ie; for casting 4:3 content properly on 4:3 devices). 

![](screenshots/1.png)

## How to use:
- Download the latest release of sakuraCast
- Install ffmpeg if not already installed
- Open it and select your video file(s)
- Select your subtitles, if required
- Select the Chromecast you'd like to cast the video to, and the aspect ratio you'd like to cast in (select 16/9 if you're using a 16/9 display or casting 4:3 content to a 4:3 display, use 4/3 if you're casting 4:3 content to a 16:9 display)
- Select "Cast" and you're all set! This script will detect if you have hardware acceleration and use that to transcode the video, otherwise, will fall back to software transcoding.

## Bugs:
- Seeking is a bit glitchy in the UI, but works. Seeking doesn't work in Google Home, unfortunately.
- Thumbnail image doesn't work in Google Home
- Sometimes stopping a stream requires a restart of the script.

## TODO:
- Fix Google Home images
- Add more customization options for ffmpeg backend
- Modify to be OS-agnostic for Windows + macOS + BSD users
- Video URL + yt-dlp support
