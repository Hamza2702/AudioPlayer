import asyncio
import tkinter
import tkinter as tk
from tkinter import ttk, messagebox
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
import glob
import tempfile


class AudioPlayer:
    def __init__(self, root):
        # UI
        self.root = root
        self.root.title("AudioPlayer")
        self.root.geometry("700x700")
        self.root.configure(bg='#1a1a1a')
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')

        # Recording
        self.is_recording = False
        self.recording_thread = None
        self.audio_stream = None
        self.audio_p = None
        self.frames = []
        self.stop_recording_flag = threading.Event()
        self.latest_recording = None
        self.live_audio_buffer = []
        self.buffer_lock = threading.Lock()
        self.recognition_thread = None
        self.recognition_interval = 5  # Try to identify every 5 seconds

        # clear search flag
        self.clear_search_flag = False

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

        # Recording status label
        self.recording_status = tk.Label(
            recording_frame,
            text="",
            font=('Poppins', 10),
            bg='#1a1a1a',
            fg='#888888'
        )
        self.recording_status.pack(pady=(5, 0))

        # Song recognition section
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
            bg='#1a1a1a',
            width=300,
            height=300
        )
        self.image_label.pack(pady=(0, 0))

        # Title label
        self.title_label = tk.Label(
            self.display_frame,
            text="🎤 Check for song",
            font=('Poppins', 16, 'bold'),
            bg='#1a1a1a',
            fg='white',
            wraplength=350
        )
        self.title_label.pack()

        # Subtitle label
        self.subtitle_label = tk.Label(
            self.display_frame,
            text="",
            font=('Poppins', 12),
            bg='#1a1a1a',
            fg='#cccccc',
            wraplength=150
        )
        self.subtitle_label.pack(pady=(0, 0))

        # Default search box test
        self.search_var.set("Search for an artist...")

        # Spotify button
        self.spotify_button = tk.Button(
            recording_frame,
            text="🎤 Listen on spotify",
            command=self.toggle_spotify,
            font=('Poppins', 12, 'bold'),
            bg='#1db954',
            fg='#191414',
            activebackground='#1ed760',
            activeforeground='white',
            relief=tk.FLAT,
            bd=0,
        )
        self.spotify_button.pack()

    # Listen on spotify
    def toggle_spotify(self):
        if not self.is_listening:
            self.start_listening()
        else:
            self.stop_listening()

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
            # Get default input device
            self.audio_p = pyaudio.PyAudio()
            default_input = None
            ## Maybe add these to a drop down to select which device?
            for i in range(self.audio_p.get_device_count()):
                device_info = self.audio_p.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    default_input = device_info
                    break

            if default_input is None:
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
                text=f"Recording from: {default_input['name']}",
                fg='#ff4444'
            )

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
            self.root.after(0, self.finalize_recording)

    # Stop recording
    def stop_recording(self):
        if self.is_recording:
            self.stop_recording_flag.set()
            self.is_recording = False

    # Finish recording
    def finalize_recording(self):
        try:
            # Clean up audio stream
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()

            if self.audio_p:
                self.audio_p.terminate()

            # Update status
            self.recording_status.config(text="Checking stopped", fg='#888888')

        except Exception as e:
            messagebox.showerror("Error", f"Failed to finalize recording: {str(e)}")
        finally:
            self.cleanup_recording()

    def cleanup_recording(self):
        # Reset UI
        self.record_button.config(
            text="🎤 Check for song",
            bg='#d73527',
            activebackground='#ff4444'
        )

        # Clear variables
        self.is_recording = False
        self.audio_stream = None
        self.audio_p = None
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
                    if len(self.live_audio_buffer) < 100:  # Need at least some audio data
                        continue

                # Update status
                self.root.after(0, lambda: self.recognition_status.config(text="Identifying song...",
                                                                          fg='#ffaa00'))

                # Create temporary file from live buffer
                temp_file = self.create_temp_file_from_buffer()

                if not temp_file:
                    continue

                # Run the async recognition
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                song_data = loop.run_until_complete(self.recognize_song_from_file(temp_file))

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
                wf.setnchannels(1)  # mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(44100)
                wf.writeframes(b''.join(buffer_copy))

            return temp_path

        except Exception as e:
            print(f"Error creating temp file: {e}")
            return None

    async def recognize_song_from_file(self, file_path):
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
            print(f"KeyError in recognition: {e}")
            print(f"Available data: {out if 'out' in locals() else 'No response'}")
            return None
        except Exception as e:
            print(f"Recognition error: {e}")
            return None

    # Update song info
    def update_song_display(self, song_data):
        self.title_label.config(text=song_data['title'])
        self.subtitle_label.config(text=f"by {song_data['artist']}")

        # Identified song
        self.recognition_status.config(
            text=f"Song identified: {song_data['title']}",
            fg='#14a085'
        )

        # Load and display image
        if song_data['image_url']:
            try:
                response = requests.get(song_data['image_url'], timeout=10)
                if response.status_code == 200:
                    image = Image.open(BytesIO(response.content))
                    # Resize image to fit
                    image = image.resize((350, 350), Image.Resampling.LANCZOS)
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

    def show_recognition_error(self, message):
        self.recognition_status.config(text=message, fg='#ff4444')
        self.title_label.config(text="Song not recognized")
        self.subtitle_label.config(text="Try again or check audio quality")

    def search_artist(self):
        artist_name = self.search_var.get().strip()
        if not artist_name or artist_name == "Search for an artist...":
            messagebox.showwarning("Warning", "Enter an artist name")
            return

        # Run search in background
        thread = threading.Thread(target=self.search_artist_thread, args=(artist_name,))
        thread.daemon = True
        thread.start()

    def search_artist_thread(self, artist_name):
        try:
            # Run async search
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            artist_data = loop.run_until_complete(self.find_and_get_artist(artist_name))

            if artist_data:
                # Update GUI in main
                self.root.after(0, self.update_artist_display, artist_data)
            else:
                self.root.after(0, self.show_error, f"Artist '{artist_name}' not found")

        except Exception as e:
            self.root.after(0, self.show_error, f"Error: {str(e)}")

    async def find_and_get_artist(self, artist_name):
        shazam = Shazam()

        # Search for artist
        search_results = await shazam.search_artist(artist_name)

        if not search_results.get('artists', {}).get('hits'):
            return None

        # Get first artist
        first_artist = search_results['artists']['hits'][0]['artist']
        artist_id = first_artist['adamid']

        # Get artist details
        about_artist = await shazam.artist_about(
            artist_id,
            query=ArtistQuery(views=[ArtistView.TOP_SONGS])
        )

        artist_data = about_artist['data'][0]
        artist_info = {
            'name': artist_data['attributes']['name'],
            'image_url': None
        }

        # Try to get artist image
        if 'artwork' in artist_data['attributes']:
            artwork = artist_data['attributes']['artwork']
            if artwork and 'url' in artwork:
                # Actual dimensions
                image_url = artwork['url'].replace('{w}', '200').replace('{h}', '200')
                artist_info['image_url'] = image_url

        return artist_info

    def update_artist_display(self, artist_data):
        # Update artist name
        self.title_label.config(text=artist_data['name'])
        self.subtitle_label.config(text="Artist")

        # Load and display image
        if artist_data['image_url']:
            try:
                response = requests.get(artist_data['image_url'], timeout=10)
                if response.status_code == 200:
                    image = Image.open(BytesIO(response.content))
                    # Resize image
                    image = image.resize((350, 350), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.image_label.config(image=photo)
                    self.image_label.image = photo  # Keep a reference
                else:
                    self.show_placeholder_image()
            except Exception as e:
                print(f"Error loading image: {e}")
                self.show_placeholder_image()
        else:
            self.show_placeholder_image()

    def show_placeholder_image(self):
        # Placeholder image
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