"""
AMD VCE

https://github.com/rigaya/VCEEnc/blob/master/VCEEncC_Options.en.md

Rembrandt Radeon 680M H.265/HEVC encode features
10bit depth:     yes
max profile:     main10
max bitrate:     1000000 kbps
ref frames:      1-16
pre analysis:    yes
max streams:     16
timeout support: yes
smart access:    no
"""

OUTPUT_BUFFER = 32
PROFILES = {
    'yuv420:8':  'main',
    'yuv422:8':  'main',
    'yuv420:10': 'main10',
    'yuv422:10': 'main10',
}
COLORS = {
    'BT.709': 'bt709'
    # smpte2084 bt2020nc bt2020c
}


class Encoder:

    CMD = ['vceencc', '--avsw']

    def __init__(self, vid):
        #print(f'hevc_vceenc idx:{vid.idx()}')

        self.params = {
            'c': 'hevc',
            'u': 'slow',
            '-cqp': vid.crf,
            '-profile': PROFILES[vid.idx()],
            '-tier': 'high',
            '-output-depth': vid.bits,
            '-output-buf': OUTPUT_BUFFER,
        }
        if vid.gop:
            self.params['-gop-len'] = vid.gop
        if vid.color_primaries:
            self.params['-colorprim'] = COLORS[vid.color_primaries]
        if vid.transfer_characteristics:
            self.params['-transfer'] = COLORS[vid.transfer_characteristics]
        if vid.matrix_coefficients:
            self.params['-colormatrix'] = COLORS[vid.matrix_coefficients]
        self.res = vid.res

    def get_params(self):
        return self.params

    def scale(self):
        return ['--output-res', f'-2x{self.res}', '--vpp-resize', 'lanczos3']
