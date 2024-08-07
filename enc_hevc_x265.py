"""
x265
https://x265.readthedocs.io/en/stable/
http://trac.ffmpeg.org/wiki/Encode/H.265

lut: file=path:interp=mode

intra: x265-params "intra-refresh=1:keyint=1
or -g:v 0|1

Supported pixel formats: yuv420p yuvj420p yuv422p yuvj422p yuv444p yuvj444p
gbrp yuv420p10le yuv422p10le yuv444p10le gbrp10le yuv420p12le yuv422p12le yuv444p12le
gbrp12le gray gray10le gray12le
"""
from lib import BaseEncoder

PRESETS = {
    1080: 'slower',
    1440: 'medium',
    2160: 'slow'
}
PRESET_DEFAULT = 'medium'
FORMATS = {
    'yuv420:8':  'yuv420p',
    'yuv422:8':  'yuv422p',
    'yuv420:10': 'yuv420p10le',
    'yuv422:10': 'yuv422p10le',
#   'bw:8':      'gray',
#   'bw:10':     'gray10le'
}
PROFILES = {
    'yuv420:8':  'main',
    'yuv422:8':  'main444-8', # 'main422',
    'yuv420:10': 'main10',
    'yuv422:10': 'main422-10',
}

class Encoder(BaseEncoder):

    can_scale = False

    def __init__(self, vid):
        print(f'x265 idx: {vid.idx()}')

        self.params = {
            'c:v': 'libx265',
            'preset': vid.preset or PRESETS.get(vid.res, PRESET_DEFAULT),
            'crf': vid.crf,
        }
        if vid.idx() in PROFILES:
            self.params['profile:v'] = PROFILES[vid.idx()]
        if vid.tune:
            self.params['tune'] = vid.tune
        x265params = ['open-gop=1']
        if vid.gop:
            x265params.append(f'keyint={vid.gop}')
        if vid.params:
            x265params.append(f'{vid.params}')
        if vid.all_i:
            self.params['g:v'] = 1
        self.params['x265-params'] = ':'.join(x265params)

        self.idx = vid.idx()

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        if self.idx in PROFILES:
            return [{'format': FORMATS[self.idx]}]
        return []
