"""Inline audio preview player used by the cache UI."""

import os
import time

import pygame
from mutagen import File as MutagenFile
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel, QFrame, QHBoxLayout, QPushButton, QSlider
)


class AudioPlayer:
    def __init__(self, parent, filepath, preview_frame):
        self.parent = parent
        self.filepath = filepath
        self.preview_frame = preview_frame
        self.is_playing = False
        self.position = 0
        self.duration = 0
        self.active = True
        self.start_time = 0

        try:
            audio = MutagenFile(filepath)
            self.duration = audio.info.length if audio else 0
            print(
                f"Audio loaded: {self.filepath}, Duration: {self.format_time(self.duration)}")
        except Exception as e:
            print(f"Failed to load audio duration {self.filepath}: {e}")
            self.duration = 0

        pygame.mixer.init()
        self.setup_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(100)

    def setup_ui(self):
        layout = self.preview_frame.layout()
        if not layout:
            print("No layout found in preview_frame for AudioPlayer")
            return

        file_name = os.path.basename(self.filepath)
        size = os.path.getsize(self.filepath)
        layout.addWidget(QLabel(f"File: {file_name}"))
        ftype = "MP3" if self.filepath.endswith('.mp3') else "OGG"
        layout.addWidget(QLabel(
            f"Type: {ftype}, Size: {self.format_size(size)}, Duration: {self.format_time(self.duration)}"))

        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)

        self.play_pause_button = QPushButton(
            "Play" if not self.is_playing else "Pause")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        controls_layout.addWidget(self.play_pause_button)

        controls_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.parent.persistent_volume * 100))
        self.volume_slider.valueChanged.connect(self.set_volume)
        controls_layout.addWidget(self.volume_slider)

        layout.addWidget(controls_frame)

        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setFocusPolicy(Qt.NoFocus)
        self.progress_slider.setRange(0, int(self.duration * 1000))
        self.progress_slider.sliderPressed.connect(self.start_scrub)
        self.progress_slider.sliderReleased.connect(self.seek_audio)
        layout.addWidget(self.progress_slider)

        self.time_label = QLabel(f"00:00 / {self.format_time(self.duration)}")
        layout.addWidget(self.time_label)

        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.addWidget(QPushButton(
            "Close Preview", clicked=lambda: self.parent.close_preview(self.preview_frame, deselect=True)))
        button_layout.addWidget(QPushButton(
            "Open Externally", clicked=lambda: self.open_externally(self.filepath)))
        layout.addWidget(button_frame)

        self.preview_frame.show()
        self.preview_frame.update()

    def toggle_play_pause(self):
        if not self.active:
            return
        if not self.is_playing:
            if self.position >= self.duration:
                self.position = 0
                self.progress_slider.setValue(0)
            try:
                pygame.mixer.music.load(self.filepath)
            except pygame.error as e:
                print(f"Failed to load audio {self.filepath}: {e}")
                return
            pygame.mixer.music.play(loops=0)
            pygame.mixer.music.set_pos(self.position)
            pygame.mixer.music.set_volume(self.parent.persistent_volume)
            self.start_time = time.time() - self.position
            self.is_playing = True
            self.play_pause_button.setText("Pause")
        else:
            self.position = self.get_current_position()
            try:
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                pass
            self.is_playing = False
            self.play_pause_button.setText("Play")

    def set_volume(self, value):
        if not self.active:
            return
        volume = value / 100
        pygame.mixer.music.set_volume(volume)
        self.parent.persistent_volume = volume

    def start_scrub(self):
        if not self.active or not self.is_playing:
            return
        self.position = self.get_current_position()
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_pause_button.setText("Play")

    def seek_audio(self):
        if not self.active:
            return
        self.position = self.progress_slider.value() / 1000
        self.position = max(0, min(self.position, self.duration))
        self.time_label.setText(
            f"{self.format_time(self.position)} / {self.format_time(self.duration)}")
        if self.is_playing:
            try:
                pygame.mixer.music.load(self.filepath)
            except pygame.error as e:
                print(f"Failed to load audio {self.filepath}: {e}")
                return
            pygame.mixer.music.play(loops=0)
            pygame.mixer.music.set_pos(self.position)
            self.start_time = time.time() - self.position

    def get_current_position(self):
        if self.is_playing:
            return time.time() - self.start_time
        return self.position

    def update_progress(self):
        if not self.active or not self.preview_frame.isVisible():
            return
        if self.is_playing:
            current_pos = self.get_current_position()
            if current_pos >= self.duration:
                pygame.mixer.music.stop()
                self.is_playing = False
                self.position = self.duration
                self.progress_slider.setValue(int(self.duration * 1000))
                self.time_label.setText(
                    f"{self.format_time(self.duration)} / {self.format_time(self.duration)}")
                self.play_pause_button.setText("Play")
            else:
                self.progress_slider.setValue(int(current_pos * 1000))
                self.time_label.setText(
                    f"{self.format_time(current_pos)} / {self.format_time(self.duration)}")

    def stop(self):
        self.active = False
        if self.is_playing:
            self.position = self.get_current_position()
            pygame.mixer.music.stop()
        self.timer.stop()

    def format_time(self, seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def format_size(self, size_in_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:.2f} {unit}"
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:.2f} TB"

    def open_externally(self, filepath):
        if not os.path.exists(filepath):
            print(f"File does not exist: {filepath}")
            return
        try:
            os.startfile(filepath)
        except Exception as e:
            print(f"Failed to open {filepath} externally: {e}")
