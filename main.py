import asyncio
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import threading
from shazamio import Shazam
from shazamio.schemas.artists import ArtistQuery
from shazamio.schemas.enums import ArtistView
import wave
import pyaudio
import os
import tempfile
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import webbrowser
from dotenv import load_dotenv
from collections import deque


## REDO CONNECTION SPOTIFY

# Carissa's Weird is too niche for this app :(
# When playing a song, it will also think it's from the more popular album

class AudioPlayer:
    load_dotenv()

    def __init__(self, root):
        self.root = root
        self.root.title("AudioPlayer")
        self.root.geometry("700x900")
        self.root.configure(bg='#1a1a1a')
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')

        self.is_recording = False
        self.recording_thread = None
        self.audio_stream = None
        self.audio_p = pyaudio.PyAudio()  # Initialize audio_p here
        self.frames = []
        self.stop_recording_flag = threading.Event()
        self.live_audio_buffer = []
        self.buffer_lock = threading.Lock()
        self.recognition_thread = None
        self.recognition_interval = 5  # Try to identify every 5 seconds
        self.logged_songs = deque(maxlen=5)  # Song deque
        self.song_counter = 0

        # clear search flag
        self.clear_search_flag = False
        self.current_song_data = None

        self.spotify_client = None
        self.spotify_username = None
        self.spotify_auth_manager = None
        self.spotify_update_thread = None
        self.spotify_stop_flag = threading.Event()
        self.token_expired_shown = False

        # Get input devices
        self.devices, self.device_info_list = self.get_input_devices()

        # Main
        main_frame = tk.Frame(root, bg='#1a1a1a', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Search
        search_frame = tk.Frame(main_frame, bg='#1a1a1a')
        search_frame.pack(fill=tk.X, pady=(0, 20))

        # Search entry
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=('Poppins', 10),
            bg='#2a2a2a',
            fg='white',
            insertbackground='white',
            relief=tk.FLAT,
            bd=5
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.search_entry.bind('<Return>', lambda e: self.search_artist())
        self.search_entry.bind('<Button-1>', self.clear_search)

        # Search button
        self.search_button = tk.Button(
            search_frame,
            text="Search Artist",
            command=self.search_artist,
            font=('Poppins', 10, 'bold'),
            bg='#0d7377',
            fg='white',
            activebackground='#14a085',
            activeforeground='white',
            relief=tk.FLAT,
            bd=0,
            padx=15
        )
        self.search_button.pack(side=tk.RIGHT)

        # Recording section
        recording_frame = tk.Frame(main_frame, bg='#1a1a1a')
        recording_frame.pack(fill=tk.X, pady=(0, 5))

        # Recording button
        self.record_button = tk.Button(
            recording_frame,
            text="🎤 Check for song",
            command=self.toggle_recording,
            font=('Poppins', 12, 'bold'),
            bg='#d73527',
            fg='white',
            activebackground='#ff4444',
            activeforeground='white',
            relief=tk.FLAT,
            bd=0,
        )
        self.record_button.pack()

        # Sync button
        self.sync_button = tk.Button(
            recording_frame,
            text="🔄 Play",
            command=self.sync_and_play,
            font=('Poppins', 10, 'bold'),
            bg='#ff66b3',
            fg='white',
            activebackground='#8e44ad',
            activeforeground='white',
            relief=tk.FLAT,
            bd=0,
        )
        self.sync_button.pack(pady=(5, 0))
        self.sync_button.pack_forget()

        # Recording status label
        self.recording_status = tk.Label(
            recording_frame,
            text="",
            font=('Poppins', 10),
            bg='#1a1a1a',
            fg='#888888'
        )
        self.recording_status.pack(pady=(5, 0))

        recognition_frame = tk.Frame(main_frame, bg='#1a1a1a')
        recognition_frame.pack(fill=tk.X, pady=(0, 0))

        # Recognition status label
        self.recognition_status = tk.Label(
            recognition_frame,
            text="",
            font=('Poppins', 10),
            bg='#1a1a1a',
            fg='#888888'
        )
        self.recognition_status.pack(pady=(5, 0))

        # Display section
        self.display_frame = tk.Frame(main_frame, bg='#1a1a1a')
        self.display_frame.pack(fill=tk.BOTH, expand=True)

        # Image label
        self.image_label = tk.Label(
            self.display_frame,
            bg='#1a1a1a'
        )
        self.image_label.pack(pady=(0, 0))

        # Title label
        self.title_label = tk.Label(
            self.display_frame,
            text="",
            font=('Poppins', 16, 'bold'),
            bg='#1a1a1a',
            fg='white',
            wraplength=550
        )
        self.title_label.pack()

        # Subtitle label
        self.subtitle_label = tk.Label(
            self.display_frame,
            text="",
            font=('Poppins', 12),
            bg='#1a1a1a',
            fg='#cccccc',
            wraplength=450
        )
        self.subtitle_label.pack(pady=(0, 0))

        # Default search box test
        self.search_var.set("Search for an artist...")

        # Connect to spotify button
        self.spotify_button = tk.Button(
            recording_frame,
            text="🎵 Connect to Spotify",
            command=self.connect_spotify,
            font=('Poppins', 12, 'bold'),
            bg='#1db954',
            fg='#191414',
            activebackground='#1ed760',
            activeforeground='white',
            relief=tk.FLAT,
            bd=0,
        )
        self.spotify_button.pack(pady=(10, 0))

        # Spotify status
        self.spotify_status = tk.Label(
            recording_frame,
            text="",
            font=('Poppins', 10),
            bg='#1a1a1a',
            fg='#1db954'
        )
        self.spotify_status.pack(pady=(5, 0))

        # Combo box
        devices_max_length = max(len(device) for device in self.devices) if self.devices else 20
        self.combobox_menu = ttk.Combobox(
            recording_frame,
            values=self.devices,
            font=('Poppins', 8),
            state="readonly",
            background='#084b83',
            foreground='black',
            width=devices_max_length + 5

        )
        self.combobox_menu.current(0)
        self.combobox_menu.pack(pady=(5, 0))
        self.combobox_menu.bind("<<ComboboxSelected>>", self.update_device_label)

        # Current device label
        self.device_label = tk.Label(
            recording_frame,
            text="Current device:",
            font=('Poppins', 8),
            bg="#1a1a1a",
            fg='white',
            wraplength=550
        )
        self.device_label.pack(pady=(5, 0))

        self.update_device_label()

        # Logged songs listbox , too lazy to change name to listbox......!
        self.logged_songs_label = tk.Listbox(
            recording_frame,
            height=5,
            width=60,
            font=('Poppins', 10),
            bg='#1a1a1a',
            fg='white'
        )
        self.logged_songs_label.pack(pady=(5, 0))
        self.logged_songs_label.bind("<Double-Button-1>", self.click_song)

    ##################################################################################################################################

    # Link user to song
    def click_song(self, event):
        selected = self.logged_songs_label.curselection()
        if selected:
            i = selected[0]
            if i < len(self.logged_songs):
                # FIXED: Get the song data correctly from the deque
                song_text = list(self.logged_songs)[i]  # Convert deque to list to access by index
                # Parse the song text to extract title and artist
                if ' - ' in song_text:
                    title, artist = song_text.split(' - ', 1)  # Split only on first occurrence
                    song_data = {'title': title, 'artist': artist}
                    self.open_spotify_song(song_data)

    # Open spotify song
    def open_spotify_song(self, song_data):
        try:
            if self.spotify_client:
                search_query = f"track:{song_data['title']} artist:{song_data['artist']}"
                results = self.spotify_client.search(q=search_query, type='track', limit=1)

                if results['tracks']['items']:
                    track = results['tracks']['items'][0]
                    spotify_url = track['external_urls']['spotify']
                    webbrowser.open(spotify_url)
                else:
                    messagebox.showinfo("Not Found",
                                        f"Could not find '{song_data['title']}' by {song_data['artist']} on Spotify")
            else:
                search_url = f"https://open.spotify.com/search/{song_data['title']} {song_data['artist']}"
                webbrowser.open(search_url)
        except Exception as e:
            print(f"Error opening Spotify song: {e}")
            search_url = f"https://open.spotify.com/search/{song_data['title']} {song_data['artist']}"
            webbrowser.open(search_url)

    # Deque of latest tracked songs
    def track_latest_songs(self, song_data=None):
        if song_data:
            # Format son
            song = f"{song_data['title']} - {song_data['artist']}"

            # Avoid duplicate songs
            # check if deque is empty or if last song is different
            if not self.logged_songs or (self.logged_songs and self.logged_songs[-1] != song):
                self.logged_songs.append(song)
                self.refresh_listbox()

    def refresh_listbox(self):
        self.logged_songs_label.delete(0, tk.END)  # Clear listbox
        for song in self.logged_songs:
            self.logged_songs_label.insert(tk.END, song)  # Insert song

    # Update current device label
    def update_device_label(self, event=None):
        selected_device = self.combobox_menu.get()
        self.device_label.configure(text=f"Current device: {selected_device}")

    # Get all input devices
    def get_input_devices(self):
        devices = []
        device_info_list = []
        default_input = None

        # Go through devices
        for i in range(self.audio_p.get_device_count()):
            device_info = self.audio_p.get_device_info_by_index(i)
            # Get input devices only
            if device_info['maxInputChannels'] > 0:
                device_name = device_info['name']
                # Check for default input device
                if device_info.get('isDefaultInput', False):
                    default_input = device_name
                    # Add to beginning of dropdown
                    devices.insert(0, f"Default: {device_name}")
                    device_info_list.insert(0, device_info)
                else:
                    devices.append(device_name)
                    device_info_list.append(device_info)

        # No default devices found, use first one
        if not default_input and device_info_list:
            default_input = device_info_list[0]
            devices.insert(0, f"Default: {default_input['name']}")
            device_info_list.insert(0, default_input)

        return devices, device_info_list

    # Connect to spotify
    def connect_spotify(self):
        try:
            scope = "user-read-private user-read-email user-library-read user-library-modify user-read-playback-state user-read-currently-playing user-modify-playback-state"

            self.spotify_auth_manager = SpotifyOAuth(
                client_id=os.getenv('SPOTIFY_CLIENT_ID'),
                client_secret=os.getenv('SPOTIFY_CLIENT_SECRET'),
                redirect_uri="https://hamza2702.github.io/",
                scope=scope
            )

            auth_url = self.spotify_auth_manager.get_authorize_url()
            webbrowser.open(auth_url)

            self.spotify_button.config(text="Connecting...", state='disabled')

            auth_thread = threading.Thread(target=self.handle_spotify_auth)
            auth_thread.daemon = True
            auth_thread.start()

        except Exception as e:
            messagebox.showerror("Spotify Error", f"Failed to connect to Spotify: {str(e)}")
            self.spotify_button.config(text="🎵 Connect to Spotify", state='normal')

    # Spotify authentication
    def handle_spotify_auth(self):
        try:
            token_info = self.spotify_auth_manager.get_access_token(as_dict=False)

            if token_info:
                self.spotify_client = spotipy.Spotify(auth=token_info)
                user_info = self.spotify_client.current_user()
                self.spotify_username = user_info['display_name'] or user_info['id']
                self.token_expired_shown = False
                self.root.after(0, self.update_spotify_ui, True)
                self.start_current_song_monitoring()
            else:
                self.root.after(0, self.update_spotify_ui, False)

        except Exception as e:
            print(f"Spotify auth error: {e}")
            self.root.after(0, self.update_spotify_ui, False)

    # Update spotify on success/failure
    def update_spotify_ui(self, success):
        if success:
            self.spotify_button.config(
                text="🎵 Connected to Spotify",
                state='disabled',
                bg='#14a085'
            )
            self.spotify_status.config(text=f"{self.spotify_username} connected")
            self.spotify_button.pack_forget()
        else:
            self.spotify_button.config(
                text="🎵 Connect to Spotify",
                state='normal',
                bg='#1db954'
            )
            self.spotify_status.config(text="Connection failed")

    def handle_spotify_token_expiry(self):
        if not self.token_expired_shown:
            self.token_expired_shown = True
            messagebox.showwarning("Connection Expired", "Please reconnect to Spotify as the access token expired")

        self.spotify_client = None
        self.spotify_stop_flag.set()

        self.spotify_button.config(
            text="🎵 Connect to Spotify",
            state='normal',
            bg='#1db954'
        )
        self.spotify_status.config(text="Token expired - Please reconnect")
        self.spotify_button.pack(pady=(10, 0))

    # Current song monitoring
    def start_current_song_monitoring(self):
        self.spotify_stop_flag.clear()
        self.spotify_update_thread = threading.Thread(target=self.monitor_current_song)
        # Daemon threads = run in the background
        self.spotify_update_thread.daemon = True
        self.spotify_update_thread.start()

    # Monitor current song
    def monitor_current_song(self):
        while not self.spotify_stop_flag.is_set():
            try:
                current_track = self.spotify_client.current_playback()
                # Get current song
                if current_track and current_track['is_playing']:
                    track_item = current_track['item']
                    track_name = track_item['name']
                    artist_name = track_item['artists'][0]['name']
                    song_info = f"♪ {track_name} • {artist_name}"

                    cover_url = None
                    # If it is in an album
                    if 'album' in track_item and 'images' in track_item['album']:
                        images = track_item['album']['images']
                        if images:
                            cover_url = images[0]['url']

                    song_data = {
                        'title': track_name,
                        'artist': artist_name,
                        'image_url': cover_url,
                        'album': track_item.get('album', {}).get('name', ''),
                        'spotify_uri': track_item.get('uri', '')
                    }

                    self.root.after(0, self.update_song_display, song_data)
                else:
                    # Not playing
                    song_info = "♪ Not playing anything"
                    self.root.after(0, lambda: self.recognition_status.config(text=song_info))
                    # self.root.after(0, self.clear_display)
                    # Clear display if not showing search results
                    if not hasattr(self, 'showing_artist_search') or not self.showing_artist_search:
                        self.root.after(0, self.clear_display)


            except spotipy.exceptions.SpotifyException as e:
                # Token expired
                if e.http_status == 401:
                    self.root.after(0, self.handle_spotify_token_expiry)
                    break

                else:
                    print(f"Spotify API error: {e}")
            except Exception as e:
                print(f"Error in monitor_current_song: {e}")

            self.spotify_stop_flag.wait(2)

    # Clear display / set to placeholder
    def clear_display(self):
        self.title_label.config(text="")
        self.subtitle_label.config(text="")
        self.show_placeholder_image()

    # Update song info
    def update_song_display(self, song_data):
        self.showing_artist_search = False
        self.current_song_data = song_data
        self.track_latest_songs(song_data)

        if self.spotify_client:
            try:
                curr_track = self.spotify_client.current_playback()
                repeat_state = curr_track.get('repeat_state') if curr_track else None
                rep_state = "Off"

                # If song is looped etc
                if repeat_state == "off":
                    rep_state = ""
                elif repeat_state == "context":
                    rep_state = "• (Album repeat)"
                elif repeat_state == "track":
                    rep_state = "• (Looped)"

                # Identified song
                self.recognition_status.config(
                    text=f"Song playing: {song_data['title']} {rep_state}",
                    fg='#14a085'
                )
            except Exception as e:
                print(f"Error getting Spotify playback info: {e}")
                self.recognition_status.config(
                    text=f"Song recognized: {song_data['title']}",
                    fg='#14a085'
                )
        else:
            self.recognition_status.config(
                text=f"Song recognized: {song_data['title']}",
                fg='#14a085'
            )

        self.title_label.config(text=song_data['title'])

        # If in album
        if 'album' in song_data and song_data['album']:
            subtitle_text = f"by {song_data['artist']} • {song_data['album']}"
        else:
            subtitle_text = f"by {song_data['artist']}"

        self.subtitle_label.config(text=subtitle_text)

        # Load and display image
        if song_data['image_url']:
            try:
                response = requests.get(song_data['image_url'], timeout=10)
                if response.status_code == 200:
                    image = Image.open(BytesIO(response.content))
                    # Resize image to fit
                    image = image.resize((300, 300), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.image_label.config(image=photo)
                    self.image_label.image = photo  # Reference
                else:
                    self.show_placeholder_image()
            except Exception as e:
                print(f"Error loading image: {e}")
                self.show_placeholder_image()
        else:
            self.show_placeholder_image()

    # Sync with spotify
    def sync_and_play(self):
        # Need to connect w/ spotify
        if not self.spotify_client:
            messagebox.showwarning("Spotify Required", "Please connect to Spotify to play the song")
            return

        # No song detected
        if not self.current_song_data:
            messagebox.showwarning("No Song", "No song detected to sync")
            return

        # Start background process
        thread = threading.Thread(target=self.sync_and_play_thread)
        thread.daemon = True
        thread.start()

    # Sync and play
    def sync_and_play_thread(self):
        try:
            # Get song data
            song_title = self.current_song_data['title']
            artist_name = self.current_song_data['artist']

            search_query = f"track:{song_title} artist:{artist_name}"
            results = self.spotify_client.search(q=search_query, type='track', limit=1)

            print(results)

            # Play on device
            if results['tracks']['items']:
                track_uri = results['tracks']['items'][0]['uri']

                devices = self.spotify_client.devices()
                active_device = None

                for device in devices['devices']:
                    if device['is_active']:
                        active_device = device
                        break

                if not active_device and devices['devices']:
                    active_device = devices['devices'][0]

                if active_device:
                    self.spotify_client.start_playback(
                        device_id=active_device['id'],
                        uris=[track_uri]
                    )
                    self.root.after(0, lambda: self.recognition_status.config(
                        text=f"Synced and playing: {song_title}",
                        fg='#1db954'
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showwarning("No Device", "No active Spotify device found"))
            else:
                # Can't find song
                self.root.after(0, lambda: messagebox.showinfo("Not Found",
                                                               f"Could not find '{song_title}' by {artist_name} on Spotify"))


        except spotipy.exceptions.SpotifyException as e:
            # Token expired
            if e.http_status == 401:
                self.root.after(0, self.handle_spotify_token_expiry)
            else:
                self.root.after(0, lambda: messagebox.showerror("Spotify Error", f"Spotify API error: {str(e)}"))
        except Exception as e:
            print(f"Error in sync_and_play_thread: {e}")
            self.root.after(0, lambda: messagebox.showerror("Sync Error", f"Failed to sync and play: {str(e)}"))

    ## Clear search
    def clear_search(self, event):
        if not self.clear_search_flag:
            self.search_var.set("")
            self.clear_search_flag = True

    # Toggle recording
    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    # Start recording
    def start_recording(self):
        try:
            # Get selected device from dropdown
            selected_device_name = self.combobox_menu.get()
            selected_device_info = None

            # Find the device info
            for i, device_name in enumerate(self.devices):
                if device_name == selected_device_name:
                    selected_device_info = self.device_info_list[i]
                    break

            if selected_device_info is None:
                messagebox.showerror("Error", "No input device found")
                return

            # Audio format
            format = pyaudio.paInt16
            channels = 1
            rate = 44100
            chunk = 1024

            # Open audio stream
            self.audio_stream = self.audio_p.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk
            )

            # Reset variables
            self.frames = []
            self.live_audio_buffer = []
            self.stop_recording_flag.clear()
            self.is_recording = True

            # Update UI
            self.record_button.config(
                text="⏹️ Stop checking",
                bg='#666666',
                activebackground='#888888'
            )
            self.recording_status.config(
                text=f"Recording from: {selected_device_info['name']}",
                fg='#ff4444'
            )

            self.sync_button.pack(pady=(5, 0))

            # Start recording in background
            self.recording_thread = threading.Thread(target=self.record_audio_thread)
            self.recording_thread.daemon = True
            self.recording_thread.start()

            # Start recognition loop
            self.recognition_thread = threading.Thread(target=self.recognition_loop)
            self.recognition_thread.daemon = True
            self.recognition_thread.start()

        except Exception as e:
            messagebox.showerror("Recording Error", f"Failed to start recording: {str(e)}")
            self.cleanup_recording()

    def record_audio_thread(self):
        chunk = 1024
        buffer_duration = 10  # 10 seconds of audio in buffer
        max_frames = int(44100 * buffer_duration / chunk)

        try:
            while not self.stop_recording_flag.is_set() and self.is_recording:
                try:
                    data = self.audio_stream.read(chunk, exception_on_overflow=False)
                    with self.buffer_lock:
                        self.live_audio_buffer.append(data)
                        # Keep only last 10 seconds
                        if len(self.live_audio_buffer) > max_frames:
                            self.live_audio_buffer.pop(0)

                except Exception as e:
                    print(f"Stream read error: {e}")
                    break
        except Exception as e:
            print(f"Recording thread error: {e}")
        finally:
            self.root.after(0, self.finalise_recording)

    # Stop recording
    def stop_recording(self):
        if self.is_recording:
            self.stop_recording_flag.set()
            self.is_recording = False

    # Finish recording
    def finalise_recording(self):
        try:
            # Clean up audio stream
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()

            # Update status
            self.recording_status.config(text="")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to finalise recording: {str(e)}")
        finally:
            self.cleanup_recording()

    def cleanup_recording(self):
        # Reset UI
        self.record_button.config(
            text="🎤 Check for song",
            bg='#d73527',
            activebackground='#ff4444'
        )
        self.sync_button.pack_forget()

        # Add to listbox
        self.track_latest_songs()

        # Clear variables
        self.is_recording = False
        self.audio_stream = None
        self.frames = []
        self.recognition_thread = None

    def recognition_loop(self):
        while self.is_recording and not self.stop_recording_flag.is_set():
            try:
                # Wait for recognition interval
                if self.stop_recording_flag.wait(self.recognition_interval):
                    break

                # Skip if not recording anymore
                if not self.is_recording:
                    break

                # Check if enough audio data
                with self.buffer_lock:
                    if len(self.live_audio_buffer) < 100: # Need at least some audio data
                        continue

                # Update status
                self.root.after(0, lambda: self.recognition_status.config(text="Identifying song...", fg='#ffaa00'))

                # Create temporary file from live buffer
                temp_file = self.create_temp_file_from_buffer()

                if not temp_file:
                    continue

                # Run the async recognition
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                song_data = loop.run_until_complete(self.recognise_song_from_file(temp_file))

                # Clean up temp file
                try:
                    os.unlink(temp_file)
                except:
                    pass

                if song_data:
                    # Update GUI in main
                    self.root.after(0, self.update_song_display, song_data)
                else:
                    # Only show error if recording
                    if self.is_recording:
                        self.root.after(0, lambda: self.recognition_status.config(text="Listening for music...",
                                                                                  fg='#888888'))

            except Exception as e:
                print(f"Recognition loop error: {e}")
                if self.is_recording:
                    self.root.after(0, lambda: self.recognition_status.config(text="Recognition error, retrying...",
                                                                              fg='#ff4444'))

    def create_temp_file_from_buffer(self):
        try:
            with self.buffer_lock:
                if not self.live_audio_buffer:
                    return None

                # Copy current buffer
                buffer_copy = self.live_audio_buffer.copy()

            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)

            # Write audio data to temp file
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1) # mono
                wf.setsampwidth(2) # 16-bit
                wf.setframerate(44100)
                wf.writeframes(b''.join(buffer_copy))

            return temp_path

        except Exception as e:
            print(f"Error creating temp file: {e}")
            return None

    async def recognise_song_from_file(self, file_path):
        try:
            shazam = Shazam()
            # Identify song from file
            out = await shazam.recognize(file_path)
            track = out['track']

            song_data = {
                'title': track.get('title', track.get('name', 'Unknown Title')),
                'artist': track.get('subtitle', track.get('artist', track.get('artistName', 'Unknown Artist'))),
                'image_url': None
            }

            # Get cover art in different ways
            image_url = None
            if 'images' in track and track['images']:
                images = track['images']
                if 'coverart' in images:
                    image_url = images['coverart']
                elif 'coverarthq' in images:
                    image_url = images['coverarthq']
                elif 'background' in images:
                    image_url = images['background']
            elif 'artwork' in track:
                # Apparently its in the track ?!
                artwork = track['artwork']
                if isinstance(artwork, dict):
                    image_url = artwork.get('url')
                elif isinstance(artwork, str):
                    image_url = artwork
            elif 'albumArt' in track:
                image_url = track['albumArt']
            elif 'coverArt' in track:
                image_url = track['coverArt']

            if image_url:
                song_data['image_url'] = image_url
            return song_data

        except KeyError as e:
            print(f"Error in recognition: {e}")
            return None
        except Exception as e:
            print(f"Recognition error: {e}")
            return None

    # Search artist
    def search_artist(self):
        artist_name = self.search_var.get().strip()
        if not artist_name or artist_name == "Search for an artist...":
            messagebox.showwarning("Warning", "Enter an artist name")
            return
        current_track = self.spotify_client.current_playback()
        if current_track and current_track['is_playing']:
            messagebox.showwarning("Warning", "Pause the current song to search for an artist")
            return

        thread = threading.Thread(target=self.search_artist_thread, args=(artist_name,))
        thread.daemon = True
        thread.start()

    # Search artist ui
    def search_artist_thread(self, artist_name):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            artist_data = loop.run_until_complete(self.find_and_get_artist(artist_name))

            if artist_data:
                self.root.after(0, lambda: self.recognition_status.config(text=""))
                self.root.after(0, self.update_artist_display, artist_data)
            else:
                self.root.after(0, self.show_error, f"Artist '{artist_name}' not found")

        except Exception as e:
            self.root.after(0, self.show_error, f"Error: {str(e)}")

    # Find artists
    async def find_and_get_artist(self, artist_name):
        shazam = Shazam()

        # Find artist
        search_results = await shazam.search_artist(artist_name)

        if not search_results.get('artists', {}).get('hits'):
            return None

        first_artist = search_results['artists']['hits'][0]['artist']
        artist_id = first_artist['adamid']

        # Artist info
        about_artist = await shazam.artist_about(
            artist_id,
            query=ArtistQuery(views=[ArtistView.TOP_SONGS])
        )

        artist_data = about_artist['data'][0]
        artist_info = {
            'name': artist_data['attributes']['name'],
            'image_url': None
        }

        # If there's an image
        if 'artwork' in artist_data['attributes']:
            artwork = artist_data['attributes']['artwork']
            if artwork and 'url' in artwork:
                image_url = artwork['url'].replace('{w}', '200').replace('{h}', '200')
                artist_info['image_url'] = image_url

        return artist_info

    # Update info
    def update_artist_display(self, artist_data):
        self.showing_artist_search = True
        self.title_label.config(text=artist_data['name'])
        self.subtitle_label.config(text="Artist")

        if artist_data['image_url']:
            try:
                response = requests.get(artist_data['image_url'], timeout=10)
                if response.status_code == 200:
                    image = Image.open(BytesIO(response.content))
                    image = image.resize((300, 300), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.image_label.config(image=photo)
                    self.image_label.image = photo
                else:
                    self.show_placeholder_image()
            except Exception as e:
                print(f"Error loading image: {e}")
                self.show_placeholder_image()
        else:
            self.show_placeholder_image()

    # Placeholder image for album/artist
    def show_placeholder_image(self):
        placeholder = Image.new('RGB', (350, 350), color='#2a2a2a')
        photo = ImageTk.PhotoImage(placeholder)
        self.image_label.config(image=photo)
        self.image_label.image = photo

    def show_error(self, message):
        self.title_label.config(text="Error occurred")
        self.subtitle_label.config(text="")
        messagebox.showerror("Error", message)

def main():
    root = tk.Tk()
    app = AudioPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()