# Twitch-AFK-Watcher
A lightweight app that helps you to farm points or watchtime on twitch

## Project Aim

The **Twitch AFK Watcher** is a lightweight Python application designed to watch Twitch streams in the background with **minimal system resource consumption**. Its primary goal is to allow users to passively accrue Twitch channel points, drops, or watch streams without dedicating significant CPU, GPU, or memory to a full-fledged browser or streaming client.

It achieves this by leveraging:
* **Streamlink**: A command-line utility that extracts stream URLs and pipes them directly to a video player.
* **MPV Player**: A highly customizable and lightweight media player, configured to run silently and without a visible window.

The application features a simple Tkinter-based GUI for ease of use, allowing users to start watching streams immediately or schedule them for a later time, and integrates with the system tray for discreet background operation.

## Features

* **Low Resource Usage**: Utilizes Streamlink and MPV to minimize overhead compared to browser-based watching.
* **Background Operation**: Streams run silently and without a visible player window.
* **System Tray Integration**: Minimize to tray for unobtrusive operation.
* **Immediate Watching**: Start a stream on demand.
* **Scheduled Watching**: Schedule streams to start at a specific time daily.
* **Cookie Support**: Uses Twitch authentication cookies to ensure logged-in status and eligibility for channel points/drops.

## Setup & Installation

To get the Twitch AFK Watcher running, you'll need the following:

### Prerequisites

1.  **Python 3.x**: Download and install from [python.org](https://www.python.org/downloads/).
2.  **Streamlink**: Install via pip:
    ```bash
    pip install streamlink
    ```
    Alternatively, for the latest version, follow instructions on [Streamlink's GitHub](https://github.com/streamlink/streamlink).
3.  **MPV Player**: Download and install from [mpv.io](https://mpv.io/download/).
    * **Crucially**, ensure the directory containing `mpv.exe` is added to your system's **PATH environment variable**. This allows both Streamlink and the application to locate `mpv`.
4.  **Required Python Libraries**: Install using pip:
    ```bash
    pip install pystray schedule Pillow
    ```

### Project Files

Place the following files in the same directory:

* `twitch_afk_watcher.py` (or whatever you name your main Python script)
* `cookies.txt` (your Twitch authentication cookies)
* `streamlinkrc` (Streamlink configuration file)

#### `cookies.txt`

This file should contain your Twitch authentication cookies in **Netscape HTTP Cookie File format**. You can typically export these using browser extensions like "Cookie-Editor" (available for Chrome/Firefox).

**Example `cookies.txt` snippet (content will vary):**
