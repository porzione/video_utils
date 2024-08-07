"""
VA-API HEVC

https://trac.ffmpeg.org/wiki/Hardware/VAAPI
https://ffmpeg.org//ffmpeg-codecs.html#VAAPI-encoders
https://www.tauceti.blog/posts/linux-ffmpeg-amd-5700xt-hardware-video-encoding-hevc-h265-vaapi/

Supported pixel formats: vaapi, scale_vaapi format
nv12 yuv420p p010(420/10) yuy2(422/8)
"""
from lib import BaseEncoder

COMPLVL = 29 # 1 AMD
# VBAQ=16 (not with CQP), pre-encode=8, quality=4, preset=2, speed=0
# And at the end, the validity bit (bit0) is set to 1

PARAMS_IN = {
    'threads': '1',
    'hwaccel': 'vaapi',
    'hwaccel_output_format': 'vaapi',
    #'vaapi_device': '/dev/dri/renderD128',
}

class Encoder(BaseEncoder):
    can_scale = True

    def __init__(self, vid):
        self.params = {
                'c:v': 'hevc_vaapi',
                'rc_mode': 'CQP',
                'compression_level': COMPLVL,
                'qp': vid.crf,
                'tier': 'high',
                'profile:v': 'main10' if vid.bits == 10 else 'main',
        }
        self.bits = vid.bits
        self.res = vid.res

    def get_params_in(self):
        return PARAMS_IN

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        flt = ['hwupload']
        scale_vaapi = {}

        if scale:
            scale_vaapi = {
                'w': -1,
                'h': self.res,
                'mode': 'hq',
                'force_original_aspect_ratio': 1
            }

        if self.bits == 10:
            scale_vaapi['format'] = 'p010'

        flt.append({'scale_vaapi': scale_vaapi})
        return flt
