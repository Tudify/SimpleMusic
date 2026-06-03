import sys
import os
import random
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QDialog, QDialogButtonBox, QStyle
)
try:
    import sounddevice as sd
except:
    pass
from PyQt6.QtCore import Qt, QUrl, QTimer, QPoint
from PyQt6.QtGui import QKeySequence, QFont, QMouseEvent, QShortcut
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
# mutagen for metadata
try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

class FramelessMusicPlayer(QWidget):
    COLORS = ["#3b3424", "#3b243b", "#24363b"]

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setFixedSize(425, 140)
        self._drag_pos = None

        self.font = QFont("Hack", 10)

        # Qt 6: create QAudioOutput separately
        self.audio = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.playbackStateChanged.connect(self.on_state_changed)

        # Playlist and index
        self.playlist = []
        self.index = -1

        self.setup_ui()

        self.timer = QTimer()
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_slider)
        self.timer.start()

        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_file_or_folder)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.toggle_play_pause)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(self.open_devices_window)

        self.change_background_color_random()

    def open_devices_window(self):
        dlg = Devices(self)
        dlg.exec()

    def setup_ui(self):
        self.setStyleSheet("background-color: #202326; color: #ffffff;")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)
        self.title_label = QLabel("No track loaded")
        self.title_label.setFont(self.font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 22px; margin-top: 5px;")
        self.artist_label = QLabel("")
        self.artist_label.setFont(self.font)
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_label.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 11px;")
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.artist_label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.seek)
        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.setSingleStep(1000)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; }
            QSlider::handle:horizontal { width: 14px; margin: -4px 0; border-radius: 7px; background: #ffffff; }
            QSlider::sub-page:horizontal { background: rgba(255,255,255,0.16); border-radius: 4px; }
        """)
        self.main_layout.addWidget(self.slider)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.prev_btn = QPushButton("⏮")
        self.prev_btn.setFont(self.font)
        self.prev_btn.setFixedHeight(36)
        self.prev_btn.clicked.connect(self.prev_track)
        self.play_btn = QPushButton("▶")
        self.play_btn.setFont(self.font)
        self.play_btn.setFixedHeight(36)
        self.play_btn.clicked.connect(self.toggle_play_pause)
        self.next_btn = QPushButton("⏭")
        self.next_btn.setFont(self.font)
        self.next_btn.setFixedHeight(36)
        self.next_btn.clicked.connect(self.next_track)

        btn_style = """
            QPushButton {
                background-color: #292c30;
                color: #ffffff;
                border: 1px solid #414346;
                padding: 6px 10px;
                border-radius: 6px;
            }
            QPushButton:hover { border: 1px solid #0a6cff; }
        """
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.setStyleSheet(btn_style)

        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addStretch()
        self.main_layout.addLayout(controls)

        self.slider.mousePressEvent = self._slider_mouse_press_override(self.slider.mousePressEvent)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        event.accept()

    def _slider_mouse_press_override(self, original):
        def wrapper(event):
            if event.button() == Qt.MouseButton.LeftButton:
                slider = self.slider
                x = event.position().x()
                w = slider.width()
                ratio = min(max(0.0, x / w), 1.0)
                new_val = int(ratio * (slider.maximum() - slider.minimum()))
                slider.setValue(new_val)
                self.seek(new_val)
            original(event)
        return wrapper

    def _slider_pressed(self):
        self._slider_was_playing = (self.player.playbackState() == QMediaPlayer.PlayingState)
        if self._slider_was_playing:
            self.player.pause()

    def _slider_released(self):
        if getattr(self, "_slider_was_playing", False):
            self.player.play()

    def seek(self, msec):
        self.player.setPosition(int(msec))

    def update_slider(self):
        if not self.slider.isSliderDown():
            pos = self.player.position()
            self.slider.setValue(pos)

    def on_position_changed(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)

    def on_duration_changed(self, duration):
        self.slider.setRange(0, max(0, duration))

    def on_media_status_changed(self, status):
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia
        ):
            self.update_track_info()

    def on_state_changed(self, state):
        if self.player.playbackState() == QMediaPlayer.PlaybackState:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")

    def open_file_or_folder(self):
        options = QFileDialog.Option.ReadOnly
        file_path, _ = QFileDialog.getOpenFileName(self, "Open MP3 or Cancel to pick folder", "", "Audio Files (*.mp3);;All Files (*)", options=options)
        if file_path:
            if os.path.isdir(file_path):
                self.load_folder(file_path)
            else:
                self.playlist = [file_path]
                self.index = 0
                self.load_index_and_play(self.index)
            return

        folder = QFileDialog.getExistingDirectory(self, "Pick folder for playlist")
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder):
        files = []
        for name in os.listdir(folder):
            full = os.path.join(folder, name)
            if os.path.isfile(full) and name.lower().endswith(".mp3"):
                files.append(full)
        files.sort()
        if not files:
            self.title_label.setText("No mp3s found in folder")
            self.artist_label.setText("")
            return
        self.playlist = files
        self.index = 0
        self.load_index_and_play(self.index)

    def load_index_and_play(self, idx):
        if idx < 0 or idx >= len(self.playlist):
            return
        path = self.playlist[idx]
        self.index = idx
        url = QUrl.fromLocalFile(path)
        self.player.setSource(url)
        self.player.play()
        self.change_background_color_random()
        self.update_track_info()

    def prev_track(self):
        if not self.playlist:
            return
        self.index = (self.index - 1) % len(self.playlist)
        self.load_index_and_play(self.index)

    def next_track(self):
        if not self.playlist:
            return
        self.index = (self.index + 1) % len(self.playlist)
        self.load_index_and_play(self.index)

    def toggle_play_pause(self):
        if self.player.state() == QMediaPlayer.playbackState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.NoMedia and self.playlist:
                self.load_index_and_play(self.index if self.index >= 0 else 0)
            else:
                self.player.play()

    def update_track_info(self):
        title = ""
        artist = ""
        path = None
        if 0 <= self.index < len(self.playlist):
            path = self.playlist[self.index]
        if path and MutagenFile is not None:
            try:
                m = MutagenFile(path, easy=True)
                if m:
                    title = m.get("title", [""])[0] or ""
                    artist = m.get("artist", [""])[0] or ""
            except Exception:
                title = ""
                artist = ""
        if not title:
            if path:
                title = os.path.splitext(os.path.basename(path))[0]
        if not artist:
            artist = ""
        self.title_label.setText(title or "Unknown title")
        self.artist_label.setText(artist or "")

    def change_background_color_random(self):
        color = random.choice(self.COLORS)
        self.setStyleSheet(f"background-color: {color}; color: #ffffff;")
        btn_style = """
            QPushButton {
                background-color: rgba(41,44,48,0.9);
                color: #ffffff;
                border: 1px solid rgba(65,67,70,0.9);
                padding: 6px 10px;
                border-radius: 6px;
            }
            QPushButton:hover { border: 1px solid #0a6cff; }
        """
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.setStyleSheet(btn_style)

    # Ensure clean shutdown
    def closeEvent(self, event):
        try:
            self.player.stop()
        except Exception:
            pass
        return super().closeEvent(event)

class Devices(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Devices - SimpleMusic")
        self.setGeometry(100, 100, 400, 300)
        self.setStyleSheet("""
            QLabel#heading {
                font-size: 22px;
                font-weight: bold;
                margin-bottom: 7px;
            }
            *{font-family: hack, consolas, monospace;}
            """)
        layout = QVBoxLayout()
        self.heading_label = QLabel("Devices")
        self.heading_label.setObjectName("heading")
        layout.addWidget(self.heading_label, alignment=Qt.AlignmentFlag.AlignLeft)
        self.new_current_label = QLabel("Currently Available:")
        layout.addWidget(self.new_current_label)
        devices = self.getoutputdevices()
        for d in devices:
            device_label = QLabel(f"{d}")
            layout.addWidget(device_label)
        layout.addSpacing(20)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def getoutputdevices(self):
        devices = sd.query_devices()
        result = []

        for d in devices:
            if d['max_output_channels'] > 0:
                result.append(d["name"])

        return result

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = FramelessMusicPlayer()
    player.show()
    sys.exit(app.exec())