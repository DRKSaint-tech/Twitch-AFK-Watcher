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

# --- Custom Dialog Class ---
class CustomQuitDialog(tk.Toplevel):
    """
    A custom Tkinter Toplevel window to serve as a confirmation dialog
    with custom button texts for closing or minimizing the application.
    """
    def __init__(self, parent):
        """
        Initializes the custom dialog window.

        Args:
            parent (tk.Tk or tk.Toplevel): The parent window for this dialog.
        """
        super().__init__(parent)
        self.transient(parent)  # Make the dialog transient to the parent window
        self.grab_set()         # Make the dialog modal (user must interact with it)

        self.title("Exit Application")
        self.result = None      # Stores the user's choice: "close_completely" or "minimize_to_tray"

        # Position the dialog relative to the parent window
        # Get parent's geometry and calculate center
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        # Calculate a rough center position
        dialog_width = 350 # Approximate width for the dialog
        dialog_height = 120 # Approximate height for the dialog
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        self.resizable(False, False) # Prevent resizing the dialog

        # Message Label
        tk.Label(self, text="Do you want to close the application completely, or minimize it to the system tray?",
                 wraplength=300, justify=tk.CENTER).pack(pady=15, padx=10)

        # Button Frame
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=5)

        # Custom Buttons
        ttk.Button(button_frame, text="Close Completely", command=self.close_completely).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Minimize to Tray", command=self.minimize_to_tray).pack(side=tk.LEFT, padx=10)

        # Bind the window close (X) button to the minimize action as a default "cancel"
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # Start the dialog's event loop and wait for it to close
        self.wait_window(self)

    def close_completely(self):
        """Sets the result to close and destroys the dialog."""
        self.result = "close_completely"
        self.destroy()

    def minimize_to_tray(self):
        """Sets the result to minimize and destroys the dialog."""
        self.result = "minimize_to_tray"
        self.destroy()

# --- Main Application Class ---
class TwitchAFKWatcher:
    """
    A Tkinter-based application for watching Twitch streams in the background
    using Streamlink and MPV, designed for AFK viewing with minimal resource usage.
    It supports immediate watching, scheduling, and system tray integration.
    """

    def __init__(self, master):
        """
        Initializes the application, sets up the main window,
        determines the cookie file path, creates widgets,
        and starts background threads.
        """
        self.master = master
        master.title("Twitch AFK Watcher")
        master.geometry("400x300")  # Slightly increased size for better layout
        # Handle the window close event to ensure proper cleanup (tray icon, threads)
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Determine the base path for the cookie file, whether running as script or EXE
        if getattr(sys, 'frozen', False):
            # Running as a compiled executable (e.g., PyInstaller)
            self.base_path = os.path.dirname(sys.executable)
        else:
            # Running as a Python script
            self.base_path = os.path.abspath(".")
        self.cookie_file = os.path.join(self.base_path, "cookies.txt")

        # Global lists/variables for managing scheduled jobs and current processes
        self.scheduled_jobs = []  # Stores info about scheduled jobs, including the schedule.Job object
        self.current_stream_process = None  # To hold the Popen object if we want to terminate a running stream (not fully implemented in this version)
        self.icon = None # Placeholder for the pystray icon object

        # Initialize the GUI widgets
        self.create_widgets()
        # Start the background thread for the scheduler
        self.start_scheduler_thread()
        # Start the background thread for the system tray icon
        self.start_tray_icon_thread()

    def create_widgets(self):
        """
        Creates and packs all the Tkinter widgets for the main application window.
        """
        # --- Channel Input ---
        tk.Label(self.master, text="Twitch Channel:").pack(pady=(10, 0))
        self.channel_entry = tk.Entry(self.master, width=35)
        self.channel_entry.pack(pady=5)
        self.channel_entry.focus_set() # Set focus to the channel entry on startup

        # --- Quality Selection ---
        tk.Label(self.master, text="Stream Quality:").pack(pady=(10, 0))
        self.quality_var = tk.StringVar(self.master)
        self.quality_var.set("best")  # Default quality
        quality_options = ["best", "high", "medium", "low", "worst"]
        # ttk.Combobox provides a more modern looking dropdown
        quality_menu = ttk.Combobox(self.master, textvariable=self.quality_var, values=quality_options, state="readonly")
        quality_menu.pack(pady=5)

        # --- Action Buttons ---
        ttk.Button(self.master, text="Start Watching Now", command=self.on_click_start, width=25).pack(pady=5)
        ttk.Button(self.master, text="Schedule Watching", command=self.schedule_watch, width=25).pack(pady=5)
        ttk.Button(self.master, text="Show/Cancel Scheduled Jobs", command=self.show_scheduled_jobs, width=25).pack(pady=5)
        ttk.Button(self.master, text="Hide to Tray", command=self.hide_window, width=25).pack(pady=5)

        # Info on cookies.txt location
        tk.Label(self.master, text=f"Place 'cookies.txt' (NETSCAPE format) and 'streamlinkrc' in:\n{self.base_path}",
                 font=("Arial", 8), fg="gray").pack(pady=(10, 0))


    def afk_watch(self, channel, quality):
        """
        Core function to start watching a Twitch channel using Streamlink and MPV.
        Configured for AFK viewing with minimal resource consumption.

        Args:
            channel (str): The Twitch channel name to watch.
            quality (str): The desired stream quality (e.g., "best", "1080p", "720p").
        """
        url = f"https://twitch.tv/{channel}"

        # Define MPV player arguments as a list
        # We will pass these to Streamlink's --player-args option
        mpv_args = [
            "--mute=yes",
            "--really-quiet",
            "--no-border",
            "--geometry=0x0+0x0",
            "--no-osc",
            "--idle=once"
        ]
        # Join MPV arguments into a single string for Streamlink's --player-args option
        mpv_args_string = " ".join(mpv_args)

        try:
            self.master.after(0, lambda: messagebox.showinfo("Starting Stream", f"Attempting to watch {channel} at {quality} quality... This window may hide temporarily."))

            streamlink_command = [
                "streamlink",
                # Streamlink 7.0.0+ automatically loads cookies from streamlinkrc
                # if streamlinkrc is in the current working directory, and streamlinkrc
                # contains 'twitch-cookies-path = cookies.txt'.
                # The old '--cookies' argument is no longer used.

                "--player-no-close",
                "--player", "mpv", # <--- Tell Streamlink *just* the player executable name
                "--player-args", mpv_args_string, # <--- Pass other MPV arguments via --player-args
                "--retry-streams", "5",
                "--twitch-disable-ads",
                url, quality
            ]

            result = subprocess.run(
                streamlink_command,
                capture_output=True,
                text=True,
                check=True # Raise CalledProcessError if Streamlink returns non-zero exit code
            )

            self.master.after(0, lambda: messagebox.showinfo("Success", f"Successfully started watching {channel} at {quality} quality."))

        except subprocess.CalledProcessError as e:
            # THIS IS WHERE STREAMLINK'S ERROR OUTPUT WILL BE SHOWN
            error_message = f"Streamlink exited with error code {e.returncode}:\n{e.stderr}"
            self.master.after(0, lambda: messagebox.showerror("Streamlink Error", error_message))
        except FileNotFoundError:
            # This error occurs if 'streamlink' or 'mpv' executables are not found in system PATH.
            self.master.after(0, lambda: messagebox.showerror("Error", "Streamlink or mpv not found. Please ensure they are installed and in your system's PATH."))
        except Exception as e:
            # Catch any other unexpected errors during the process.
            self.master.after(0, lambda: messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}"))

    def on_click_start(self):
        """
        Handles the 'Start Watching Now' button click.
        Validates input and starts the `afk_watch` function in a new thread
        to prevent the GUI from freezing.
        """
        channel = self.channel_entry.get().strip()
        quality = self.quality_var.get()
        if channel:
            # Run afk_watch in a daemon thread so it doesn't prevent app exit
            threading.Thread(target=self.afk_watch, args=(channel, quality), daemon=True).start()
        else:
            messagebox.showwarning("Input Error", "Please enter a channel name.")

    def schedule_watch(self):
        """
        Handles the 'Schedule Watching' button click.
        Prompts for a time, validates input, and schedules the `afk_watch` function
        using the `schedule` library.
        """
        channel = self.channel_entry.get().strip()
        quality = self.quality_var.get()
        if not channel:
            messagebox.showwarning("Input Error", "Please enter a channel name.")
            return

        # Ask the user for the time to schedule
        time_input = simpledialog.askstring("Schedule", "Enter time to start (HH:MM in 24h format):")
        if time_input: # Check if the user entered anything (didn't click cancel)
            try:
                # Validate the time format
                datetime.datetime.strptime(time_input, "%H:%M")
                # Schedule the job. The 'schedule' library returns a Job object.
                job = schedule.every().day.at(time_input).do(self.afk_watch, channel=channel, quality=quality)
                # Store job details along with the job object for later cancellation
                self.scheduled_jobs.append({"time": time_input, "channel": channel, "quality": quality, "job": job})
                messagebox.showinfo("Scheduled", f"Watching {channel} at {quality} scheduled for {time_input}.")
            except ValueError:
                messagebox.showerror("Invalid Time", "Please enter time in HH:MM 24h format (e.g., 14:30).")
        else:
            messagebox.showinfo("Cancelled", "Scheduling cancelled.")

    def show_scheduled_jobs(self):
        """
        Displays a list of currently scheduled jobs and provides an option to cancel one.
        """
        if not self.scheduled_jobs:
            messagebox.showinfo("Scheduled Jobs", "No jobs currently scheduled.")
            return

        job_list_str = "Currently Scheduled Jobs:\n"
        # Create a display string for all scheduled jobs
        for i, job_info in enumerate(self.scheduled_jobs):
            job_list_str += f"{i+1}. Channel: {job_info['channel']}, Quality: {job_info['quality']}, Time: {job_info['time']}\n"

        messagebox.showinfo("Scheduled Jobs", job_list_str)

        # Allow the user to cancel a job
        if len(self.scheduled_jobs) > 0:
            cancel_choice = simpledialog.askinteger("Cancel Job", "Enter the number of the job to cancel (0 to skip):",
                                                   minvalue=0, maxvalue=len(self.scheduled_jobs))
            if cancel_choice is not None and cancel_choice != 0:
                # Adjust for 0-based indexing
                index_to_cancel = cancel_choice - 1
                if 0 <= index_to_cancel < len(self.scheduled_jobs):
                    job_to_cancel = self.scheduled_jobs.pop(index_to_cancel)
                    schedule.cancel_job(job_to_cancel['job']) # Use schedule.cancel_job with the stored job object
                    messagebox.showinfo("Job Cancelled", f"Job for {job_to_cancel['channel']} at {job_to_cancel['time']} cancelled.")
                else:
                    messagebox.showwarning("Invalid Input", "Invalid job number.")
            elif cancel_choice == 0:
                messagebox.showinfo("Cancelled", "Job cancellation skipped.")

    def run_scheduler(self):
        """
        This function runs in a separate thread and continuously checks for
        pending scheduled jobs using the 'schedule' library.
        It sleeps for 1 second to prevent high CPU usage.
        """
        while True:
            schedule.run_pending()
            time.sleep(1) # Sleep to avoid busy-waiting and consuming CPU

    def start_scheduler_thread(self):
        """
        Starts the `run_scheduler` function in a daemon thread.
        Daemon threads automatically terminate when the main program exits.
        """
        scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        scheduler_thread.start()

    # --- System Tray Icon Functions (using pystray) ---
    def create_image(self, width, height, color1, color2):
        """
        Creates a simple square image for the system tray icon.
        """
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
        dc.rectangle((0, height // 2, width // 2, height), fill=color2)
        return image

    def setup_tray_icon(self, icon):
        """
        Callback function for pystray to make the icon visible.
        """
        icon.visible = True

    def exit_application(self, icon, item):
        """
        Exits the entire application gracefully from the system tray menu.
        Stops the tray icon and quits the Tkinter main loop.
        """
        icon.stop() # Stop the pystray icon thread
        self.master.quit() # Quit the Tkinter main loop
        sys.exit(0) # Ensure the process fully exits

    def show_window(self, icon, item):
        """
        Restores the main Tkinter window from the system tray.
        """
        self.master.deiconify() # Show the window

    def hide_window(self, icon=None, item=None): # icon/item are passed by pystray if called from menu
        """
        Hides the main Tkinter window to the system tray.
        """
        self.master.withdraw() # Hide the window

    def start_tray_icon_thread(self):
        """
        Starts the system tray icon in a separate daemon thread.
        """
        image = self.create_image(64, 64, 'blue', 'white') # Create a simple blue/white icon
        self.icon = pystray.Icon(
            "Twitch AFK Watcher",
            image,
            "Twitch AFK Watcher",
            menu=pystray.Menu(
                pystray.MenuItem("Show Window", self.show_window),
                pystray.MenuItem("Hide Window", self.hide_window),
                pystray.Menu.SEPARATOR, # Add a separator in the menu
                pystray.MenuItem("Exit", self.exit_application)
            )
        )
        # Run the pystray icon in a daemon thread
        threading.Thread(target=self.icon.run, args=(self.setup_tray_icon,), daemon=True).start()

    def on_closing(self):
        """
        Handles the main window's 'X' (close) button event.
        Uses a custom dialog to ask the user whether to quit the app or hide it to the system tray,
        with custom button texts.
        Ensures proper cleanup on exit.
        """
        # Create an instance of our custom dialog
        dialog = CustomQuitDialog(self.master)
        # The .result attribute will be set by the dialog when a button is clicked

        if dialog.result == "close_completely":
            if self.icon:
                self.icon.stop() # Stop the pystray icon thread
            self.master.destroy() # Destroy the Tkinter window
            sys.exit(0) # Ensure the Python process fully exits
        elif dialog.result == "minimize_to_tray":
            self.hide_window() # Hide the window to the system tray


# --- Main Execution Block ---
if __name__ == "__main__":
    # Create the main Tkinter window
    root = tk.Tk()
    # Instantiate our application class
    app = TwitchAFKWatcher(root)
    # Start the Tkinter event loop. This keeps the GUI running.
    root.mainloop()