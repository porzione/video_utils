""" helpers lib """

import subprocess
import threading
from dataclasses import dataclass
from typing import Optional

ENCODERS = ('x265', 'amf', 'vaapi', 'nv', 'nvenc', 'vceenc')

# 1920x1080 2560x1440 3840x2160
RESOLUTIONS = (1080, 1440, 2160)

FORMATS = ('dnxhr', 'prores', 'cineform', 'hevc')

CRF = {
    'hevc': 19,    # default 28, 0-51, slow 19: 98.39, 20.2: 97.95, 21.2: 97.53, 22: 97.16
    'nv': 19,      # default -1, vbr/cq
    'nvenc': 19,   # default 23
    'vaapi': 21,   # default 0, 21: 99.16, 24: 98.12, 25: 97.79
                   # QCP 22: 98.94, 19: 99.49, 20: 99.34
    'amf': 18,     # default -1,
    'vceenc': 20,  # default 22:24:27
    # svt-av1: 21, # 21: 98.56, 29: 97.22
}

# downscale: Lanczos/Spline, upscale: Bicubic/Lanczos
# error diffusion dithering to minimize banding +dither=error_diffusion
DSCALE_FLAGS = 'flags=lanczos+accurate_rnd+full_chroma_int'

# FRAME_RATES = (23.98 24 25 29.97 30 50 59.94 60 120 150 180)

class BaseEncoder:

    ERROR = "Method should be overridden in subclasses"

    def get_filter(self, *args, scale=None, **kwargs):
        raise NotImplementedError(self.ERROR)

    def get_params(self):
        raise NotImplementedError(self.ERROR)

@dataclass
class Video:
    # pylint: disable=too-many-instance-attributes
    color_format: str
    res: Optional[int] = None
    frame_rate: Optional[float] = None
    bits: Optional[int] = None
    bits_in: Optional[int] = None
    crf: Optional[int] = None
    gop: Optional[int] = None
    preset: Optional[str] = None
    params: Optional[str] = None
    tune: Optional[str] = None
    profile: Optional[str] = None
    color_primaries: Optional[str] = None
    matrix_coefficients: Optional[str] = None
    transfer_characteristics: Optional[str] = None
    all_i: Optional[bool] = None

    def idx(self):
        return f'{self.color_format}:{self.bits}'

def gop(frame_rate, gop_mul):
    if gop_mul:
        return int(float(frame_rate) * gop_mul)
    return None

def join_filters(filters):
    result = []
    for filter_item in filters:
        if isinstance(filter_item, str):
            result.append(filter_item)
        elif isinstance(filter_item, dict):
            for key, value in filter_item.items():
                if isinstance(value, dict):
                    sub_items = [f"{k}={v}" for k, v in value.items()]
                    result.append(f"{key}=" + ":".join(sub_items))
                else:
                    result.append(f"{key}={value}")
    return ",".join(result)

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.3f}s"

    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:06.3f}"

def run_cmd(cmd1, cmd2=None, dry=False):
    if cmd2:
        print(f"COMMAND: {' '.join(cmd1)} | {' '.join(cmd2)}")
    else:
        print(f"COMMAND: {' '.join(cmd1)}")
    if dry:
        return 0

    def reader_thread(pipe, process):
        for line in iter(pipe.readline, b''):
            if line:
                print(f'{line.decode().strip()}')
            if process.poll() is not None:
                break

    with subprocess.Popen(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc1:
        if cmd2:
            with subprocess.Popen(cmd2, stdin=proc1.stdout, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE) as proc2:
                proc1.stdout.close()  # Allow proc1 to receive a SIGPIPE if proc2 exits.

                stdout_thread = threading.Thread(target=reader_thread, args=(proc2.stdout, proc2))
                stderr_thread = threading.Thread(target=reader_thread, args=(proc2.stderr, proc2))

                stdout_thread.start()
                stderr_thread.start()

                proc2.wait()
                return_code = proc2.returncode

                stdout_thread.join()
                stderr_thread.join()
        else:
            stdout_thread = threading.Thread(target=reader_thread, args=(proc1.stdout, proc1))
            stderr_thread = threading.Thread(target=reader_thread, args=(proc1.stderr, proc1))

            stdout_thread.start()
            stderr_thread.start()

            proc1.wait()
            return_code = proc1.returncode

            stdout_thread.join()
            stderr_thread.join()

    return return_code
