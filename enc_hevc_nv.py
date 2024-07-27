"""
Nvidia NVENC

https://trac.ffmpeg.org/wiki/HWAccelIntro#CUDANVENCNVDEC
https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/ffmpeg-with-nvidia-gpu/index.html
https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/nvenc-preset-migration-guide/index.html
https://developer.nvidia.com/blog/calculating-video-quality-using-nvidia-gpus-and-vmaf-cuda/
https://developer.nvidia.com/blog/nvidia-ffmpeg-transcoding-guide/

hwupload_cuda filter: uploading the data from system to GPU memory using

NVDec H.264/AVC: nv12, yv12 ONLY

Supported pixel formats: yuv420p nv12 p010le yuv444p p016le yuv444p16le
bgr0 bgra rgb0 rgba x2rgb10le x2bgr10le gbrp gbrp16le cuda
"""
from lib import BaseEncoder, DSCALE_FLAGS

PRESETS = {
    1080: 'p6',
    1440: 'p6',
    2160: 'p7'  # 2 pass, archiving
}
DEFAULT_PRESET = 'p6'
DEFAULT_TUNE='hq'
PARAMS_IN_CUDA = {
    # vdpau cuda vaapi qsv drm opencl vulkan
    'hwaccel': 'cuda',
    # keeps the decoded frames in GPU memory
    'hwaccel_output_format': 'cuda',
    # allow to output YUV pixel formats with a different chroma sampling than 4:2:0
    # and/or other than 8 bits per component
    'hwaccel_flags': 'allow_high_depth',
}
FORMATS = {
    'yuv420:8':  'yuv420p',
    'yuv422:8':  'yuv420p',
    'yuv420:10': 'p010le',
    'yuv422:10': 'yuv444p16le',
}
HWACCELS = {
    'yuv420:8':  'vaapi',
    'yuv422:8':  'vaapi',
    'yuv420:10': 'vdpau',
    'yuv422:10': 'vaapi',
}
PROFILES = {
    'yuv420:8':  'main',
    'yuv422:8':  'rext',
    'yuv420:10': 'main10',
    'yuv422:10': 'rext',
}

class Encoder(BaseEncoder):
    can_scale = True

    def __init__(self, vid):
        print(f'hevc_nvenc idx: {vid.idx()}')

        self.params = {
            'c:v': 'hevc_nvenc',
            'preset:v': vid.preset or PRESETS.get(vid.res, DEFAULT_PRESET),
            'tune:v': vid.tune or DEFAULT_TUNE,
            'rc:v': 'vbr',
            'cq:v': vid.crf,
            'qmin:v': vid.crf,
            'qmax:v': vid.crf,
            'b:v': '0',
            'tier': 'high',
            'profile:v': PROFILES[f'{vid.color_format}:{vid.bits_in}'],
        }
        #self.bits_in = vid.bits_in
        self.res = vid.res
        self.idx = vid.idx()
        self.best_fmt = f'{vid.color_format}p{vid.bits}le'

    def get_params_in(self):
        if self.idx == 'yuv420:8':
            params = PARAMS_IN_CUDA
        else:
            params = {
                'hwaccel': HWACCELS[self.idx],
                #'hwaccel_output_format': self.best_fmt
            }
        return params

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        flt = []
        sparams = []
        if self.idx == 'yuv420:8':
            #if self.bits_in == 10:
            #    flt.append('hwupload_cuda')
            if scale:
                sparams.append(f'w=-1:h={self.res}:interp_algo=lanczos')
            sparams.append(f'format={FORMATS[self.idx]}')
            flt.append({'scale_cuda': ':'.join(sparams)})
        else:
            if scale:
                flt.append({'scale': f'w=-1:h={self.res}:{DSCALE_FLAGS}'})
            flt.append(f'format={self.best_fmt}')
        return flt
