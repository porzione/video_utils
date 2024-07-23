"""
Nvidia NVENC

https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/ffmpeg-with-nvidia-gpu/index.html
https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/nvenc-preset-migration-guide/index.html
https://developer.nvidia.com/blog/calculating-video-quality-using-nvidia-gpus-and-vmaf-cuda/
https://developer.nvidia.com/blog/nvidia-ffmpeg-transcoding-guide/

hwupload_cuda filter: uploading the data from system to GPU memory using

Supported pixel formats: yuv420p nv12 p010le yuv444p p016le yuv444p16le
bgr0 bgra rgb0 rgba x2rgb10le x2bgr10le gbrp gbrp16le cuda
"""
from lib import BaseEncoder

PRESETS = {
    1080: 'p6',
    1440: 'p6',
    2160: 'p7'  # 2 pass, archiving
}
DEFAULT_PRESET = 'p6'
DEFAULT_TUNE='hq'
PARAMS_IN = {
    # vdpau cuda vaapi qsv drm opencl vulkan
    'hwaccel': 'cuda',
    # keeps the decoded frames in GPU memory
    'hwaccel_output_format': 'cuda'
}
FORMATS = {
    'yuv420:8':  'yuv420p',
    'yuv422:8':  'yuv420p',
    'yuv420:10': 'p010le',
    'yuv422:10': 'yuv444p16le',
}

class Encoder(BaseEncoder):
    can_scale = True

    def __init__(self, vid):
        print(f'hevc_nvenc idx:{vid.idx()}')

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
            'profile:v': 'main10' if vid.bits == 10 else 'main',
        }
        self.bits_in = vid.bits_in
        self.res = vid.res
        self.idx = vid.idx()

    def get_params_in(self):
        return PARAMS_IN

    def get_params(self):
        return self.params

    def get_filter(self, *args, scale=None, **kwargs):
        flt = []
        # NVDec H.264/AVC: nv12, yv12 ONLY
        if self.bits_in == 10:
            flt.append('hwupload_cuda')
        sparams = []
        if scale:
            sparams.append(f'w=-1:h={self.res}:interp_algo=lanczos')
        sparams.append(f'format={FORMATS[self.idx]}')
        flt.append({'scale_cuda': ':'.join(sparams)})
        return flt
