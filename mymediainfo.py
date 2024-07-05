"""
OO wrapper for pymediainfo
"""

from pymediainfo import MediaInfo

class MyMediaInfo:
    def __init__(self, file_name):
        self.media_info = MediaInfo.parse(file_name)
        self.video_track = None
        self.audio_track = None

        for track in self.media_info.tracks:
            if track.track_type == 'Video' and self.video_track is None:
                self.video_track = track
            elif track.track_type == 'Audio' and self.audio_track is None:
                self.audio_track = track

    def bit_rate(self):
        # Mbps float
        return (self.video_track.bit_rate/1000000.0) if self.video_track else None

    def bit_depth(self):
        return self.video_track.bit_depth if self.video_track else None

    def format(self):
        return self.video_track.format if self.video_track else None

    def format_profile(self):
        return self.video_track.format_profile if self.video_track else None

    def format_settings(self):
        return self.video_track.format_settings if self.video_track else None

    def color_space(self):
        return self.video_track.color_space if self.video_track else None

    def width(self):
        return self.video_track.width if self.video_track else None

    def height(self):
        return self.video_track.height if self.video_track else None

    def frame_rate(self):
        return self.video_track.frame_rate if self.video_track else None

    def video_data(self):
        return self.video_track.to_data()

    def has_audio(self):
        return self.audio_track is not None

    def audio_format(self):
        return self.audio_track.format if self.audio_track else None

    def audio_channels(self):
        return self.audio_track.channel_s if self.audio_track else None

    def audio_sampling_rate(self):
        return self.audio_track.sampling_rate if self.audio_track else None

    def audio_data(self):
        return self.audio_track.to_data()

    def is_hq(self):
        if self.format() in ['VC-3', 'FFV1', 'ProRes', 'HFYU']:
            return True
        return False

    def print(self):
        print(f'Video: {self.width()}x{self.height()} @ {self.frame_rate()}')
        print(f"Bit rate: {self.bit_rate()}")
        print(f'Bit depth: {self.bit_depth()}')
        print(f'Format: {self.format()}')
        print(f'Format profile: {self.format_profile()}')
        print(f'Format settings: {self.format_settings()}')
        print(f'Color space: {self.color_space()}')
        print(f'Chroma subsampling: {self.video_track.chroma_subsampling}')
        print(f"Audio format: {self.audio_format()}")
        print(f"Audio sampling rate: {self.audio_sampling_rate()}")
        print(f"Audio channels: {self.audio_channels()}")
