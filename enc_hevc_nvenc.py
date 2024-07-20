"""
Nvidia rigaya/NVEnc

https://github.com/rigaya/NVEnc/blob/master/NVEncC_Options.en.md

output-csp yuv420(default), yuv444
RTX 3060
RC Modes     CQP, CBR, CBRHQ, VBR, VBRHQ
Max Bframes  5
Max Level    186 (6.2)
4:4:4        yes
10bit depth  yes
"""

OUTPUT_BUFFER = 64

FORMATS_OUT = {
    'yuv420:8':  'yuv420',
    'yuv422:8':  'yuv444',
    'yuv420:10': 'yuv444',
    'yuv422:10': 'yuv444',
}

PROFILES = {
    'yuv420:8':  'main',
    'yuv422:8':  'main444',
    'yuv420:10': 'main10',
    'yuv422:10': 'main444',
}
COLORS = {
    'BT.709': 'bt709'
    # smpte2084 bt2020nc bt2020c
}

class Encoder:

    CMD = ['nvencc']

    def __init__(self, vid):
        #print(f'nvenc idx: {vid.idx()}')

        self.params = {
            'c': 'hevc',
            'u': 'quality',
            '-cqp': vid.crf,
            '-profile': PROFILES[vid.idx()],
            '-tier': 'high',
            '-output-csp': FORMATS_OUT[vid.idx()],
            '-output-depth': vid.bits,
            '-output-buf': OUTPUT_BUFFER,
            '-mv-precision': 'Q-pel',

        }
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
