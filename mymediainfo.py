""" OO wrapper for pymediainfo """

from dataclasses import dataclass
from typing import Optional
from pymediainfo import MediaInfo

@dataclass
class MyMediaInfo:
    # pylint: disable=too-many-instance-attributes

    file_name: str
    bit_rate: float = None # Mbps
    bit_depth: int = None
    format: str = None
    format_profile: Optional[str] = None
    format_settings: Optional[str] = None
    color_primaries: Optional[str] = None
    color_format: Optional[str] = None
    transfer_characteristics: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frame_rate: Optional[float] = None
    color_primaries: Optional[str] = None
    color_range: Optional[str] = None
    matrix_coefficients: Optional[str] = None
    is_interlaced: Optional[bool] = None
    is_hq: Optional[bool] = None
    has_audio: Optional[bool] = None
    audio_format: Optional[str] = None
    audio_channels: Optional[int] = None
    audio_sampling_rate: Optional[str] = None

    def __post_init__(self):
        self.media_info = MediaInfo.parse(self.file_name)
        self.video_track = None
        self.audio_track = None

        for track in self.media_info.tracks:
            if track.track_type == 'Video' and self.video_track is None:
                self.video_track = track
            elif track.track_type == 'Audio' and self.audio_track is None:
                self.audio_track = track

        if self.video_track:
            # Mbps float
            self.bit_rate = self.video_track.bit_rate / 1000000.0
            self.bit_depth = self.video_track.bit_depth
            self.format = self.video_track.format

            self.format_profile = self.video_track.format_profile
            self.format_settings = self.video_track.format_settings
            self.color_primaries = self.video_track.color_space

            cf = []
            if self.video_track.color_space:
                cf.append(self.video_track.color_space.lower())
            if self.video_track.chroma_subsampling:
                cf.append(self.video_track.chroma_subsampling.replace(':', ''))
            self.color_format = ''.join(cf)

            self.width = self.video_track.width
            self.height = self.video_track.height
            self.frame_rate = self.video_track.frame_rate
            self.color_primaries = self.video_track.color_primaries
            self.matrix_coefficients = self.video_track.matrix_coefficients
            self.transfer_characteristics = self.video_track.transfer_characteristics
            self.color_range = self.video_track.color_range
            self.is_interlaced = self.video_track.scan_type != 'Progressive'
            self.is_hq = self.format in ['VC-3', 'FFV1', 'ProRes', 'HFYU']
            self.has_audio = self.audio_track is not None

        if self.audio_track:
            self.audio_format = self.audio_track.format
            self.audio_channels = self.audio_track.channel_s
            self.audio_sampling_rate = self.audio_track.sampling_rate


    def video_data(self):
        return self.video_track.to_data()

    def audio_data(self):
        return self.audio_track.to_data()

    def print(self):
        print(f'Video: {self.width}x{self.height} @ {self.frame_rate}')
        print(f'Bit rate: {self.bit_rate}')
        if self.bit_depth:
            print(f'Bit depth: {self.bit_depth}')
        fmt = self.format
        if self.video_track.codec_id_info:
            fmt = f'{fmt} ({self.video_track.codec_id_info})'
        print(f'Format: {fmt}')
        if self.format_profile:
            print(f'Format profile: {self.format_profile}')
        if self.format_settings:
            print(f'Format settings: {self.format_settings}')
        if self.color_format:
            print(f'Color format: {self.color_format}')
        if self.color_primaries:
            print(f'Color primaries: {self.color_primaries}')
        if self.matrix_coefficients:
            print(f'Matrix coefficients: {self.matrix_coefficients}')
        if self.transfer_characteristics:
            print(f'Transfer characteristics: {self.transfer_characteristics}')
        if self.color_range:
            print(f'Color range: {self.color_range}')
        print(f'Scan: {self.video_track.scan_type}')
        if self.audio_track:
            print(f'Audio format: {self.audio_format}')
            print(f'Audio sampling rate: {self.audio_sampling_rate}')
            print(f'Audio channels: {self.audio_channels}')
