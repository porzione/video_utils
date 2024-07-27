"""
GoPro CineForm HD

https://gopro.github.io/cineform-sdk/

Supported pixel formats: yuv422p10le gbrp12le gbrap12le
"""
import sys
from lib import BaseEncoder

PROFILES = [
    'film3+','film3','film2+','film2','film1.5','film1+','film1',
    'high+','high','medium+','medium','low+','low']
PROFILE_DEFAULT = 'film1.5'

class Encoder(BaseEncoder):

    can_scale = False

    def __init__(self, vid):
        self.params = { 'c:v': 'cfhd' }
        if vid.profile:
            if vid.profile not in PROFILES:
                sys.exit(f'bad profile {vid.profile} not: '
                         f'{" ".join(PROFILES)}')
            self.params['quality:v'] = vid.profile
        else:
            self.params['quality:v'] = PROFILE_DEFAULT

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        return [{'format': 'yuv422p10le'}]
