import subprocess
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image, ImageDraw
import pystray
import schedule
import threading
import time
import datetime
import os
import sys

# --- Current Known Issue & Troubleshooting Context for Collaborators ---
# Despite efforts, the application currently exits with a generic "Streamlink exited with error code 1:"
# when attempting to watch a stream. The subprocess.CalledProcessError.stderr is consistently blank,
# meaning Streamlink itself is not providing a detailed error message to stderr.
#
# Past troubleshooting has confirmed:
# 1. Streamlink version 7.5.0 is used (verified via `streamlink --version` and debug pop-up).
# 2. The deprecated `--cookies` argument has been REMOVED from the Streamlink command.
#    Cookies are now handled via `streamlinkrc` (located in the same directory as this script),
#    which points to `cookies.txt` (`twitch-cookies-path = cookies.txt` in streamlinkrc).
# 3. MPV is correctly installed and in the system's PATH (verified via `mpv` in CMD).
# 4. The MPV player command in Streamlink is now split, using `--player mpv` and `--player-args "..."`
#    to improve robustness in passing arguments, as a previous error indicated "Player executable not found"
#    even when MPV was in PATH with the old `--player "mpv args"` syntax.
# 5. The `cookies.txt` file format is confirmed to be standard Netscape.
#
# Potential areas for collaboration to investigate:
# - Why Streamlink 7.5.0 is exiting with code 1 without stderr output.
# - Possible issues with specific Twitch cookies (e.g., expiration, insufficient permissions for stream type).
# - Subtle interactions between Streamlink's arguments and certain system configurations.
# - If Streamlink is logging more verbose errors elsewhere (e.g., a Streamlink log file if configured).
# - A more robust way to handle the subprocess call to capture *all* Streamlink output, not just stderr.

# --- CustomQuitDialog Class ---
class CustomQuitDialog(tk.Toplevel):
    """
    A custom Tkinter Toplevel window providing a confirmation dialog
    for closing or minimizing the application. Offers distinct options
    to either terminate the application completely or minimize it to the system tray.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Exit Application")
        self.result = None

        # Position dialog centrally relative to its parent window
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        dialog_width, dialog_height = 350, 120
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        self.resizable(False, False)

        tk.Label(self, text="Do you want to close the application completely, or minimize it to the system tray?",
                 wraplength=300, justify=tk.CENTER).pack(pady=15, padx=10)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=5)

        ttk.Button(button_frame, text="Close Completely", command=self._close_completely).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Minimize to Tray", command=self._minimize_to_tray).pack(side=tk.LEFT, padx=10)

        # Default action for window close (X) button
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        self.wait_window(self)

    def _close_completely(self):
        """Sets result to 'close_completely' and destroys the dialog."""
        self.result = "close_completely"
        self.destroy()

    def _minimize_to_tray(self):
        """Sets result to 'minimize_to_tray' and destroys the dialog."""
        self.result = "minimize_to_tray"
        self.destroy()

# --- Main Application Class ---
class TwitchAFKWatcher:
    """
    A Tkinter-based application for watching Twitch streams in the background
    using Streamlink and MPV. Designed for AFK viewing with minimal resource usage,
    supporting immediate watching, scheduling, and system tray integration.
    """
    def __init__(self, master):
        self.master = master
        master.title("Twitch AFK Watcher")
        master.geometry("400x300")
        master.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Determine the base path for external files (cookies.txt, streamlinkrc)
        # Handles both script execution and compiled executables (e.g., PyInstaller)
        self.base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(".")
        self.cookie_file = os.path.join(self.base_path, "cookies.txt")

        self.scheduled_jobs = []
        self.current_stream_process = None
        self.icon = None # pystray icon object

        self._create_widgets()
        self._start_scheduler_thread()
        self._start_tray_icon_thread()

    def _create_widgets(self):
        """Initializes and packs all Tkinter widgets for the main application window."""
        tk.Label(self.master, text="Twitch Channel:").pack(pady=(10, 0))
        self.channel_entry = tk.Entry(self.master, width=35)
        self.channel_entry.pack(pady=5)
        self.channel_entry.focus_set()

        tk.Label(self.master, text="Stream Quality:").pack(pady=(10, 0))
        self.quality_var = tk.StringVar(self.master)
        self.quality_var.set("best")
        quality_options = ["best", "high", "medium", "low", "worst"]
        quality_menu = ttk.Combobox(self.master, textvariable=self.quality_var, values=quality_options, state="readonly")
        quality_menu.pack(pady=5)

        ttk.Button(self.master, text="Start Watching Now", command=self._on_click_start, width=25).pack(pady=5)
        ttk.Button(self.master, text="Schedule Watching", command=self._schedule_watch, width=25).pack(pady=5)
        ttk.Button(self.master, text="Show/Cancel Scheduled Jobs", command=self._show_scheduled_jobs, width=25).pack(pady=5)
        ttk.Button(self.master, text="Hide to Tray", command=self._hide_window, width=25).pack(pady=5)

        tk.Label(self.master, text=f"Ensure 'cookies.txt' (NETSCAPE format) and 'streamlinkrc' are in:\n{self.base_path}",
                 font=("Arial", 8), fg="gray", wraplength=350).pack(pady=(10, 0))

    def _afk_watch(self, channel, quality):
        """
        Core function to start watching a Twitch channel using Streamlink and MPV.
        Configured for AFK viewing with minimal resource consumption.

        Collaborator Note: This function currently triggers the "exit code 1" error.
        The subprocess call to Streamlink is the primary area to investigate.
        """
        url = f"https://twitch.tv/{channel}"

        # MPV player arguments defined as a list, to be passed via Streamlink's --player-args
        mpv_args = [
            "--mute=yes",
            "--really-quiet",
            "--no-border",
            "--geometry=0x0+0x0", # Sets window to 0x0 size at 0,0 position
            "--no-osc",           # No on-screen controller
            "--idle=once"         # Exit immediately if no file is given on command line
        ]
        mpv_args_string = " ".join(mpv_args)

        try:
            self.master.after(0, lambda: messagebox.showinfo("Starting Stream", f"Attempting to watch {channel} at {quality} quality... This window may hide temporarily."))

            streamlink_command = [
                "streamlink",
                # Streamlink 7.0.0+ automatically handles cookies via streamlinkrc.
                # The --cookies argument is deprecated and removed.
                # Ensure streamlinkrc exists and contains: twitch-cookies-path = cookies.txt

                "--player-no-close",         # Keep the player open even if Streamlink exits
                "--player", "mpv",           # Specify MPV as the player executable
                "--player-args", mpv_args_string, # Pass MPV's specific arguments
                "--retry-streams", "5",      # Retry connection to stream up to 5 times
                "--twitch-disable-ads",      # Attempt to disable Twitch ads (note: this argument is deprecated in Streamlink 7.x)
                url, quality                 # The Twitch URL and desired stream quality
            ]

            result = subprocess.run(
                streamlink_command,
                capture_output=True, # Capture stdout and stderr
                text=True,           # Decode stdout/stderr as text
                check=True           # Raise CalledProcessError if Streamlink returns a non-zero exit code
            )

            self.master.after(0, lambda: messagebox.showinfo("Success", f"Successfully started watching {channel} at {quality} quality."))

        except subprocess.CalledProcessError as e:
            # Capture and display Streamlink's stderr output if it exists.
            # Currently, e.stderr is often empty for exit code 1.
            error_message = f"Streamlink exited with error code {e.returncode}:\n{e.stderr}"
            self.master.after(0, lambda: messagebox.showerror("Streamlink Error", error_message))
        except FileNotFoundError:
            # Catch if 'streamlink' or 'mpv' executables are not found in the system PATH.
            self.master.after(0, lambda: messagebox.showerror("Error", "Streamlink or mpv not found. Please ensure they are installed and in your system's PATH."))
        except Exception as e:
            # Catch any other unexpected errors during execution.
            self.master.after(0, lambda: messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}"))

    def _on_click_start(self):
        """
        Handles the 'Start Watching Now' button click.
        Validates input and starts the `_afk_watch` function in a new daemon thread
        to prevent the GUI from freezing.
        """
        channel = self.channel_entry.get().strip()
        quality = self.quality_var.get()
        if channel:
            threading.Thread(target=self._afk_watch, args=(channel, quality), daemon=True).start()
        else:
            messagebox.showwarning("Input Error", "Please enter a channel name.")

    def _schedule_watch(self):
        """
        Handles the 'Schedule Watching' button click.
        Prompts for a time, validates input, and schedules the `_afk_watch` function
        using the `schedule` library.
        """
        channel = self.channel_entry.get().strip()
        quality = self.quality_var.get()
        if not channel:
            messagebox.showwarning("Input Error", "Please enter a channel name.")
            return

        time_input = simpledialog.askstring("Schedule", "Enter time to start (HH:MM in 24h format):")
        if time_input:
            try:
                datetime.datetime.strptime(time_input, "%H:%M")
                job = schedule.every().day.at(time_input).do(self._afk_watch, channel=channel, quality=quality)
                self.scheduled_jobs.append({"time": time_input, "channel": channel, "quality": quality, "job": job})
                messagebox.showinfo("Scheduled", f"Watching {channel} at {quality} scheduled for {time_input}.")
            except ValueError:
                messagebox.showerror("Invalid Time", "Please enter time in HH:MM 24h format (e.g., 14:30).")
        else:
            messagebox.showinfo("Cancelled", "Scheduling cancelled.")

    def _show_scheduled_jobs(self):
        """
        Displays a list of currently scheduled jobs and provides an option to cancel one.
        """
        if not self.scheduled_jobs:
            messagebox.showinfo("Scheduled Jobs", "No jobs currently scheduled.")
            return

        job_list_str = "Currently Scheduled Jobs:\n"
        for i, job_info in enumerate(self.scheduled_jobs):
            job_list_str += f"{i+1}. Channel: {job_info['channel']}, Quality: {job_info['quality']}, Time: {job_info['time']}\n"

        messagebox.showinfo("Scheduled Jobs", job_list_str)

        if self.scheduled_jobs:
            cancel_choice = simpledialog.askinteger("Cancel Job", "Enter the number of the job to cancel (0 to skip):",
                                                   minvalue=0, maxvalue=len(self.scheduled_jobs))
            if cancel_choice is not None and cancel_choice != 0:
                index_to_cancel = cancel_choice - 1
                if 0 <= index_to_cancel < len(self.scheduled_jobs):
                    job_to_cancel = self.scheduled_jobs.pop(index_to_cancel)
                    schedule.cancel_job(job_to_cancel['job'])
                    messagebox.showinfo("Job Cancelled", f"Job for {job_to_cancel['channel']} at {job_to_cancel['time']} cancelled.")
                else:
                    messagebox.showwarning("Invalid Input", "Invalid job number.")
            elif cancel_choice == 0:
                messagebox.showinfo("Cancelled", "Job cancellation skipped.")

    def _run_scheduler(self):
        """
        Continuously checks for and runs pending scheduled jobs in a separate thread.
        Sleeps for 1 second to prevent high CPU usage.
        """
        while True:
            schedule.run_pending()
            time.sleep(1)

    def _start_scheduler_thread(self):
        """Starts the `_run_scheduler` function in a daemon thread."""
        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()

    # --- System Tray Icon Functions (using pystray) ---
    def _create_image(self, width, height, color1, color2):
        """Creates a simple square image for the system tray icon."""
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
        dc.rectangle((0, height // 2, width // 2, height), fill=color2)
        return image

    def _setup_tray_icon(self, icon):
        """Callback for pystray to make the icon visible."""
        icon.visible = True

    def _exit_application(self, icon, item):
        """Exits the entire application gracefully from the system tray menu."""
        icon.stop()
        self.master.quit()
        sys.exit(0)

    def _show_window(self, icon, item):
        """Restores the main Tkinter window from the system tray."""
        self.master.deiconify()

    def _hide_window(self, icon=None, item=None):
        """Hides the main Tkinter window to the system tray."""
        self.master.withdraw()

    def _start_tray_icon_thread(self):
        """Starts the system tray icon in a separate daemon thread."""
        image = self._create_image(64, 64, 'blue', 'white')
        self.icon = pystray.Icon(
            "Twitch AFK Watcher",
            image,
            "Twitch AFK Watcher",
            menu=pystray.Menu(
                pystray.MenuItem("Show Window", self._show_window),
                pystray.MenuItem("Hide Window", self._hide_window),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._exit_application)
            )
        )
        threading.Thread(target=self.icon.run, args=(self._setup_tray_icon,), daemon=True).start()

    def _on_closing(self):
        """
        Handles the main window's 'X' (close) button event.
        Uses a custom dialog to ask the user whether to quit or hide to tray.
        Ensures proper cleanup on exit.
        """
        dialog = CustomQuitDialog(self.master)
        if dialog.result == "close_completely":
            if self.icon:
                self.icon.stop()
            self.master.destroy()
            sys.exit(0)
        elif dialog.result == "minimize_to_tray":
            self._hide_window()

# --- Main Execution Block ---
if __name__ == "__main__":
    root = tk.Tk()
    app = TwitchAFKWatcher(root)
    root.mainloop()