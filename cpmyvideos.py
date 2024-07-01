#!/usr/bin/env python3
"""
mass video copy/transcode/scale
"""

import argparse
from timeit import default_timer as timer
import os
import shutil
#import math
#from pprint import pprint
import magic
import dateparser
from mymediainfo import MyMediaInfo
from lib import format_time, run_cmd

RESOLUTIONS = (720, 1080, 1440, 2160)
DEF_RES = 1440
FF_PRESETS = ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast',
              'medium', 'slow', 'slower', 'veryslow')
FORMATS = ('dnxhr', 'h265', 'av1')
FORMAT_EXTENSIONS = {
    'av1': 'MP4',
    'h265': 'MOV',
    'dnxhr': 'MOV'
}
ENCODERS = ('sw', 'amf', 'vaapi', 'nv')

parser = argparse.ArgumentParser(description='Video Copy Script')
# parser.add_argument('-D', '--debug', action='store_true', help='Enable debug output')
parser.add_argument('-s', '--srcdir', help='Source directory')
parser.add_argument('-d', '--dstdir', help='Destination directory')
parser.add_argument('-n', '--newer', help='Newer than')
parser.add_argument('--copy', action='store_true', help='Copy as is')
parser.add_argument('--dns', action='store_true',
                    help=f'Do Not Scale to {DEF_RES}')
parser.add_argument('--res', default=DEF_RES, type=int,
                    help='Resolution (%(default)s)')
parser.add_argument('--fmt', default='h265',
                    help='Target format (%(default)s)')
parser.add_argument('--preset', default='slow',
                    help='ffmpeg preset (%(default)s)')
parser.add_argument('--crf', default='18',
                    help='ffmpeg crf (%(default)s)')
parser.add_argument('--pix_fmt', help='Set ffmpeg pix_fmt')
parser.add_argument('--enc', default='sw',
                    help='Encoder type (%(default)s)')
parser.add_argument('--fnparams', action='store_true',
                    help='Add params to dest file names')
parser.add_argument('--dry', action='store_true',
                    help='Dry run')
args = parser.parse_args()
#print(args) ; exit()

if args.srcdir is None:
    raise ValueError('Need source directory')
if args.dstdir is None:
    raise ValueError('Need target directory')
if not os.path.exists(args.srcdir):
    raise ValueError(f"Source dir '{args.srcdir}' doesn't exist")
if not os.path.exists(args.dstdir):
    raise ValueError(f"Destination dir '{args.dstdir}' doesn't exist")
if not args.res in RESOLUTIONS:
    raise ValueError(f"Bad resolution '{args.res}', use one of: {RESOLUTIONS}")
if not args.fmt in FORMATS:
    raise ValueError(f"Bad format '{args.fmt}', use one of: {FORMATS}")
if not args.preset in FF_PRESETS:
    raise ValueError(f"Bad ffmpeg preset '{args.preset}', use one of {FF_PRESETS}")
if not args.enc in ENCODERS:
    raise ValueError(f"Bad encoder '{args.enc}', use one of {ENCODERS}")

if args.newer:
    args.newer = dateparser.parse(args.newer).timestamp()

def get_pix_fmt_for_bit_depth(bit_depth):
    if bit_depth == 8:
        return 'yuv420p'  # 8-bit
    if bit_depth == 10:
        return 'yuv420p10le'  # 10-bit
    if bit_depth == 12:
        return 'yuv420p12le'  # 12-bit
    raise ValueError("Unsupported bit depth. Supported values are 8, 10, and 12.")


def v_transcode(src, dst, info):

    cmd = ['ffmpeg', '-hide_banner', '-nostdin']

    params_in = {}
    if info.is_hq():
        params = { 'c:v': 'copy' }
    elif args.fmt == 'dnxhr':
        # https://gist.github.com/dexeonify/ed31c7d85fcf7297719e2ec4740fafda
        # https://dovidenko.com/2019/999/ffmpeg-dnxhd-dnxhr-mxf-proxies-and-optimized-media.html
		# LB: dnxhr_lb - Low Bandwidth. 8-bit 4:2:2 (yuv422p). Offline Quality.
		# SQ: dnxhr_sq - Standard Quality. 8-bit 4:2:2 (yuv422p). Suitable for delivery format.
		# HQ: dnxhr_hq - High Quality. 8-bit 4:2:2 (yuv422p).
		# HQX: dnxhr_hqx - High Quality. 10-bit 4:2:2 (yuv422p10le). UHD/4K Broadcast-quality delivery.
		# 444: dnxhr_444 - Finishing Quality. 10-bit 4:4:4 (yuv444p10le). Cinema-quality delivery.
        params = {
            'c:v': 'dnxhd',
            'profile:v': 'dnxhr_hq', # 8 bit
            'pix_fmt': 'yuv422p'     # 4:2:2
        }
        if info.bit_depth() == 10:
            params['pix_fmt'] = 'yuv422p10le'
            params['profile:v'] = 'dnxhr_hqx'
    elif args.fmt == 'h265':
        # http://trac.ffmpeg.org/wiki/Encode/H.265
        # https://trac.ffmpeg.org/wiki/Hardware/AMF
        # https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/FFmpeg-and-AMF-HW-Acceleration
        if info.bit_depth() == 10:
            params['profile'] = 'main10'
        match args.enc:
            case 'amf':
                params = {
                    'c:v': 'hevc_amf',
                    'quality': 'quality',
                    'usage': 'lowlatency_high_quality',
                    'rc': 'cqp',
                    'qp_p': args.crf,
                    'qp_i': args.crf,
                }
            case 'vaapi':
                # https://trac.ffmpeg.org/wiki/Hardware/VAAPI
                # https://ffmpeg.org//ffmpeg-codecs.html#VAAPI-encoders
                params_in = {
                    'threads': '1',
                    'hwaccel': 'vaapi',
                    'hwaccel_output_format': 'vaapi',
                    'vaapi_device': '/dev/dri/renderD128',
                }
                params = {
                    'c:v': 'hevc_vaapi',
                    'compression_level': '29',
                    'rc_mode': 'CQP',
                    'qp': args.crf,
                    # 'async_depth': '4'
                }
            case 'nv':
                # https://docs.nvidia.com/video-technologies/video-codec-sdk/12.0/ffmpeg-with-nvidia-gpu/index.html
                params_in = {
                    'hwaccel': 'cuda',
                    'hwaccel_output_format': 'cuda'
                }
                params = {
                    'c:v': 'hevc_nvenc',
                    'fps_mode': 'passthrough',
                    'preset': 'p5', # p6,p7
                    'tune': 'hq',
                    # new
                    'rc': 'constqp',
                    'qp': args.crf
                }
            case 'sw':
                params = {
                    'c:v': 'libx265',
                    'preset': args.preset,
                    'crf': args.crf
                }

         #params['tag:v'] = 'hvc1' # apple/qt

    elif args.fmt == 'av1':
        # https://trac.ffmpeg.org/wiki/Encode/AV1
        # https://ottverse.com/analysis-of-svt-av1-presets-and-crf-values/
        # https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/master/Docs/CommonQuestions.md
        match args.enc:
            case 'amf':
                params = {
                    'c:v': 'av1_amf',
                    'quality': 'quality',
                    'usage': 'transcoding',
                }
            case 'vaapi':
                # https://trac.ffmpeg.org/wiki/Hardware/VAAPI
                params_in = {
                    'threads': '1',
                    'hwaccel': 'vaapi',
                    'hwaccel_output_format': 'vaapi',
                    'vaapi_device': '/dev/dri/renderD128',
                }
                params = {
                    'c:v': 'av1_vaapi',
                    'compression_level': '29',
                }
            case 'nv':
                params_in = {
                    'hwaccel': 'cuda',
                    'hwaccel_output_format': 'cuda'
                }
                params = {
                    'c:v': 'av1_nvenc',
                    'fps_mode': 'passthrough',
                    #'preset': 'slow',
                    #'preset': '6',
                    'tune': 'hq',
                }
            case 'sw':
                params = {
                    'c:v': 'libsvtav1',
                    #'preset': args.preset,
                    'preset': '6',
                    'crf': args.crf,
                    'svtav1-params': 'rc=0',
                }

    if args.pix_fmt:
        params.pix_fmt = args.pix_fmt

    if info.height() > args.res and not args.dns:
        new_width = int(info.width() * args.res / info.height())
        print(f'New resolution: {new_width} x {args.res}')
        match args.enc:
            case 'nv':
                params['vf'] = f'scale_cuda={new_width}:{args.res}'
            case 'vaapi':
                params['vf'] = f'scale_vaapi=w={new_width}:h={args.res}'
            case _:
                params['vf'] = f'scale=-1:{args.res}'
        if args.fmt != 'av1':
            params['movflags'] = 'write_colr+use_metadata_tags'

    for key, value in params_in.items():
        cmd.extend([f'-{key}', value])
    cmd.extend(['-i', src])

    # for panasonic xml meta: movflags=use_metadata_tags
    params['map_metadata'] = '0'
    params['map_metadata:s:v'] = '0:s:v'
    params['map_metadata:s:a'] = '0:s:a'

    match info.audio_format():
        case None:
            cmd.append('-an')
        case 'PCM Little / Signed':
            params['codec:a'] = 'copy'
        case _:
            if args.fmt == 'dnxhr':
                params['codec:a'] = 'pcm_s16le'
                params['ar']= '48000'
            else:
                params['codec:a'] = 'copy'

    for key, value in params.items():
        cmd.extend([f'-{key}', value])

    cmd.append(dst)
    run_cmd(cmd, args.dry)

def v_copy(src, dst):
    print(f"COPY {src} {dst}")
    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)


TOTAL_TIME = 0.0
for filename in os.listdir(args.srcdir):
    src_file = os.path.join(args.srcdir, filename)
    if os.path.isfile(src_file):

        ext = FORMAT_EXTENSIONS.get(args.fmt)
        base_name = os.path.splitext(filename)[0]
        if args.fnparams:
            base_name += f'_{args.fmt}_{args.enc}_crf{args.crf}'
        dst_file = os.path.join(args.dstdir, f'{base_name}.{ext}')
        if os.path.exists(dst_file):
            print(f'EXISTS {dst_file}')
            continue

        mime_type = magic.from_file(src_file, mime=True)
        if not mime_type or not mime_type.startswith('video'):
            continue
        print(f'FILE {src_file}')
        print(f'MIME {mime_type}')

        mi = MyMediaInfo(src_file)
        mi.print()

        if args.newer and os.path.getmtime(src_file) < args.newer:
            continue
        start_time = timer()

        if args.copy:
            v_copy(src_file, dst_file)
        else:
            v_transcode(src_file, dst_file, mi)

        end_time = timer() - start_time
        print(f"TIME {format_time(end_time)}\n")
        TOTAL_TIME += end_time

print(f"TOTAL TIME: {format_time(TOTAL_TIME)}")
