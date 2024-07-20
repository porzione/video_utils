"""
Avid DNXHR

https://dovidenko.com/2019/999/ffmpeg-dnxhd-dnxhr-mxf-proxies-and-optimized-media.html
https://avidtech.my.salesforce-sites.com/pkb/articles/en_US/White_Paper/DNxHR-Codec-Bandwidth-Specifications
https://kb.avid.com/pkb/articles/en_US/Knowledge/Avid-Qualified-Video-Rates-Rasters-and-Codecs-for-Pro-Tools

https://web.archive.org/web/20240110012221/https://avidtech.my.salesforce-sites.com/pkb/articles/en_US/White_Paper/DNxHR-Codec-Bandwidth-Specifications
https://web.archive.org/web/20240511153722/https://avidtech.my.salesforce-sites.com/pkb/articles/en_US/Knowledge/DNxHR-Codec-Bandwidth-Specifications?retURL=%2Fpkb%2Farticles%2Fen_US%2FWhite_Paper%2FDNxHR-Codec-Bandwidth-Specifications&popup=true

Supported pixel formats: yuv422p yuv422p10le yuv444p10le gbrp10le
"""
PROFILES = {
    'lb':   'yuv422p',     # Offline Quality. 22:1
    'sq':   'yuv422p',     # Suitable for delivery. 7:1
    'hq':   'yuv422p',     # 4.5:1
    'hqx':  'yuv422p10le', # UHD/4K Broadcast-quality. 5.5:1
    '444':  'yuv444p10le', # Cinema-quality. 4.5:1
}
DEFAULT_PROFILE = 'hqx'

class Encoder:

    def __init__(self, vid):
        self.profile = vid.dnx if vid.dnx else DEFAULT_PROFILE
        self.params = {
            'c:v': 'dnxhd',
            'profile:v': f'dnxhr_{self.profile}'
        }

    def get_params(self):
        return self.params

    def get_profile(self):
        return self.profile

    def get_filter(self):
        return f'format={PROFILES[self.profile]}'
