"""
Avid DNXHR

https://dovidenko.com/2019/999/ffmpeg-dnxhd-dnxhr-mxf-proxies-and-optimized-media.html
https://avidtech.my.salesforce-sites.com/pkb/articles/en_US/Knowledge/DNxHR-Codec-Bandwidth-Specifications
https://kb.avid.com/pkb/articles/en_US/Knowledge/Avid-Qualified-Video-Rates-Rasters-and-Codecs-for-Pro-Tools

Supported pixel formats: yuv422p yuv422p10le yuv444p10le gbrp10le
"""
import sys
from lib import BaseEncoder

PROFILES = {
    'lb':   'yuv422p',     # Offline Quality. 22:1
    'sq':   'yuv422p',     # Suitable for delivery. 7:1
    'hq':   'yuv422p',     # 4.5:1
    'hqx':  'yuv422p10le', # UHD/4K Broadcast-quality. 5.5:1
    '444':  'yuv444p10le', # Cinema-quality. 4.5:1
}
PROFILES_AUTO = {
    'yuv420:8':  'hq',
    'yuv422:8':  'hq',
    'yuv420:10': 'hqx',
    'yuv422:10': 'hqx',
}

class Encoder(BaseEncoder):

    can_scale = False

    def __init__(self, vid):
        if vid.profile:
            if vid.profile not in PROFILES:
                sys.exit(f'bad profile {vid.profile} not: '
                         f'{" ".join(PROFILES.keys())}')
            self.profile = vid.profile
        else:
            self.profile =PROFILES_AUTO[vid.idx()]
        self.params = {
            'c:v': 'dnxhd',
            'profile:v': f'dnxhr_{self.profile}'
        }

    def get_params(self):
        return self.params

    def get_profile(self):
        return self.profile

    def get_filter(self, *args, scale=None, **kwargs):
        return [{'format': PROFILES[self.profile]}]
