"""
AMD AMF HEVC

https://trac.ffmpeg.org/wiki/Hardware/AMF
https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/FFmpeg-and-AMF-HW-Acceleration

Supported pixel formats: nv12 yuv420p
"""

class Encoder:

    def __init__(self, vid):
        self.params = {
            'c:v': 'hevc_amf',
            'usage': 'lowlatency_high_quality',
            'quality': 'quality',
            'rc:v': 'cqp',
            'qp_p': vid.crf,
            'qp_i': vid.crf,
            'profile_tier': 'high',
            'level': '5.2',
        }
        self.bits = vid.bits
        self.fmt = f'{vid.color_format}p'
        if vid.bits == 10:
            self.fmt += '10le'

    def get_params(self):
        return self.params

    def get_filter(self):
        return f'format={self.fmt}'
