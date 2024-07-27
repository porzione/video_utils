"""
Apple ProRes (iCodec Pro)

https://support.apple.com/en-us/102207

Supported pixel formats: yuv422p10le yuv444p10le yuva444p10le
"""
import sys
from lib import BaseEncoder

PROFILES = ['proxy','lt','standard','hq','4444','4444xq']

class Encoder(BaseEncoder):

    can_scale = False

    def __init__(self, vid):
        if vid.profile and vid.profile not in PROFILES:
            sys.exit(f'bad profile {vid.profile} not: '
                     f'{" ".join(PROFILES)}')
        self.params = {
            'c:v': 'prores_ks',
            # alpha_bits bits for alpha plane (from 0 to 16) (default 16)
            'profile:v': vid.profile or 'auto'
        }

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        return [{'format': 'yuv422p10le'}]
