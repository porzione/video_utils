#!/usr/bin/env python3
"""
mass video copy/transcode/scale
"""

import argparse
from timeit import default_timer as timer
import os
import shutil
#from pprint import pprint
import magic
import dateparser
from mymediainfo import MyMediaInfo
from lib import format_time, run_cmd, ENCODERS

RESOLUTIONS = (720, 1080, 1440, 2160) # 1620 1800
DEF_RES = 1440
FF_PRESETS = ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast',
              'medium', 'slow', 'slower', 'veryslow')
FORMATS = ('dnxhr', 'hevc', 'av1')
FORMAT_EXTENSIONS = {
    'av1': 'MP4',
    'hevc': 'MOV',
    'dnxhr': 'MOV',
}
BIT_DEPTHS = {'8', '10'}
CRF = {
    'hevc': '18',
    'av1': '28',
    'dnxhr': None,
}

# downscale: Lanczos/Spline, upscale: Bicubic/Lanczos
# error diffusion dithering to minimize banding +dither=error_diffusion
# http://trac.ffmpeg.org/wiki/Scaling
DSCALE_FLAGS = 'flags=lanczos+accurate_rnd+full_chroma_int'

parser = argparse.ArgumentParser(description='Video copy/scale/convert')
parser.add_argument('-s', '--srcdir', help='Source directory')
parser.add_argument('-d', '--dstdir', help='Destination directory')
parser.add_argument('-n', '--newer', help='Newer than')
parser.add_argument('--copy', action='store_true', help='Copy as is')
#parser.add_argument('-y', action='store_true', help='Overwrite')
parser.add_argument('--dns', action='store_true',
                    help=f'Do Not Scale to {DEF_RES}')
parser.add_argument('--res', default=DEF_RES, type=int,
                    help='Resolution (%(default)s)')
parser.add_argument('--fmt', default='hevc',
                    help='Target format (%(default)s)')
parser.add_argument('--preset', default='slow',
                    help='ffmpeg preset (%(default)s)')
parser.add_argument('--svtav1preset', default='4',
                    help='svtav1 preset (%(default)s)')
parser.add_argument('--crf',
                    help=f'ffmpeg crf ({CRF})')
parser.add_argument('--enc', default='sw',
                    help='Encoder type (%(default)s)')
parser.add_argument('--bits', help='Target bit depth 8|10')
parser.add_argument('--nometa', action='store_true',
                    help='Do not map metadata')
parser.add_argument('--fnparams', action='store_true',
                    help='Add params to dest file names')
parser.add_argument('-t', dest='duration')
parser.add_argument('--dry', action='store_true',
                    help='Dry run')
args = parser.parse_args()

if args.srcdir is None:
    raise ValueError('Need source directory')
if args.dstdir is None:
    raise ValueError('Need target directory')
if not os.path.exists(args.srcdir):
    raise ValueError(f"Source dir '{args.srcdir}' doesn't exist")
if not os.path.exists(args.dstdir):
    raise ValueError(f"Destination dir '{args.dstdir}' doesn't exist")
if not args.res in RESOLUTIONS:
    raise ValueError(f"Bad resolution '{args.res}', use one of: "
                     f"{', '.join(map(str,RESOLUTIONS))}")
if not args.fmt in FORMATS:
    raise ValueError(f"Bad format '{args.fmt}', use one of: {', '.join(FORMATS)}")
if not args.preset in FF_PRESETS:
    raise ValueError(f"Bad preset '{args.preset}', use one of:"
                     f"{', '.join(FF_PRESETS)}")
if not args.enc in ENCODERS:
    raise ValueError(f"Bad encoder '{args.enc}', use one of: {', '.join(ENCODERS)}")
if args.bits and args.bits not in BIT_DEPTHS:
    raise ValueError(f"Bad bit depth '{args.bits}', use one of: "
                     f"{', '.join(BIT_DEPTHS)}")
#print(args) ; exit()

crf = args.crf if args.crf else CRF[args.fmt]

if args.newer:
    args.newer = dateparser.parse(args.newer).timestamp()

def v_transcode(src, dst, info):
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-ignore_editlist', '1']
    params_in = {}
    filter_v = {}
    bit_depth = args.bits or str(info.bit_depth())
    if info.is_hq():
        params = { 'c:v': 'copy' }
    elif args.fmt == 'dnxhr':
        # https://dovidenko.com/2019/999/ffmpeg-dnxhd-dnxhr-mxf-proxies-and-optimized-media.html
		# dnxhr_lb - Low Bandwidth. 8-bit 4:2:2 (yuv422p). Offline Quality.
		# dnxhr_sq - Standard Quality. 8-bit 4:2:2 (yuv422p). Suitable for delivery format.
		# dnxhr_hq - High Quality. 8-bit 4:2:2 (yuv422p).
		# dnxhr_hqx - High Quality. 10-bit 4:2:2 (yuv422p10le). UHD/4K Broadcast-quality delivery.
		# dnxhr_444 - Finishing Quality. 10-bit 4:4:4 (yuv444p10le). Cinema-quality delivery.
        params = {'c:v': 'dnxhd'}
        if bit_depth == '8':
            filter_v['format'] = 'yuv422p'
            params['profile:v'] = 'dnxhr_hq'
        elif bit_depth == '10':
            filter_v['format'] = 'yuv420p10le'
            params['profile:v'] = 'dnxhr_hqx'
    elif args.fmt == 'hevc':
        # http://trac.ffmpeg.org/wiki/Encode/H.265
        # https://trac.ffmpeg.org/wiki/Hardware/AMF
        # https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/FFmpeg-and-AMF-HW-Acceleration
        # Panasonic 420/8 420/10 422/10
        match args.enc:
            case 'amf':
                params = {
                    'c:v': 'hevc_amf',
                    'usage': 'lowlatency_high_quality',
                    # 'profile:v': 'main' # only main
                    'profile_tier': 'high',
                    'quality': 'quality',
                    'rc': 'cqp',
                    'qp_p': crf,
                    'qp_i': crf,
                }
                if bit_depth == '10':
                    filter_v['format'] = 'yuv420p10le'
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
                    'rc_mode': 'CQP',
                    'compression_level': '29',
                    'qp': crf,
                    # 'async_depth': '4'
                    'tier': 'high',
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
                    'tier': 'high',
                    'tune': 'hq',
                    # new
                    'rc': 'constqp',
                    'qp': crf
                }
                if bit_depth == '10':
                    params['profile:v'] = 'main10'
            case 'sw':
                params = {
                    'c:v': 'libx265',
                    'preset': args.preset,
                    'crf': crf, # default 28
                    'x265-params': 'level-idc=5.1'
                }
                if bit_depth == '10':
                    params['profile:v'] = 'main10'
                    #params['x265-params'] += ':profile=main10'
                    filter_v['format'] = 'yuv420p10le'

         # params['tag:v'] = 'hvc1' # apple/qt
    elif args.fmt == 'av1':
        # https://trac.ffmpeg.org/wiki/Encode/AV1
        match args.enc:
            case 'amf':
                params = {
                    'c:v': 'av1_amf',
                    'quality': 'quality',
                    'usage': 'transcoding',
                }
            case 'vaapi':
                params_in = {
                    'threads': '1',
                    'hwaccel': 'vaapi',
                    'hwaccel_output_format': 'vaapi',
                    'vaapi_device': '/dev/dri/renderD128',
                }
                params = {
                    'c:v': 'av1_vaapi',
                    'compression_level': '29',
                    'tier': 'high',
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
                    'preset': args.svtav1preset,
                    'crf': crf, # default 35
                    # 'qp': '35'
                    'svtav1-params': 'rc=0:level=5.2',
                }
                if bit_depth == '8':
                    filter_v['format'] = 'yuv422p'
                elif bit_depth == '10':
                    filter_v['format'] = 'yuv420p10le'
                    # input-depth 8|10
                    params['svtav1-params'] += 'input-depth=10'

    if info.height() > args.res and not args.dns:
        match args.enc:
            case 'nv':
                filter_v['scale_cuda'] = f'w=-1:h={args.res}:interp_algo=lanczos'
                if bit_depth == '10':
                    filter_v['scale_cuda'] += ':format=p010le'
            case 'vaapi':
                # mode=hq|nl_anamorphic
                filter_v['scale_vaapi'] = f'w=-1:h={args.res}:mode=hq'
                if bit_depth == '10':
                    filter_v['scale_vaapi'] += ':format=p010'
            case _:
                # dst_format yuv420p|10
                filter_v['scale'] = f'w=-1:h={args.res}:{DSCALE_FLAGS}'

    if args.fmt != 'av1':
        params['movflags'] = 'write_colr'
        if not args.nometa:
            params['movflags'] += '+use_metadata_tags'

    # input
    for key, value in params_in.items():
        cmd.extend([f'-{key}', value])
    cmd.extend(['-i', src])

    # for panasonic xml meta: movflags=use_metadata_tags
    if not args.nometa:
        params['map_metadata'] = '0'
        params['map_metadata:s:v'] = '0:s:v'
        params['map_metadata:s:a'] = '0:s:a'

    # audio
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

    # filters
    if filter_v:
        vf = [f"{key}={value}" for key, value in filter_v.items()]
        cmd.extend(['-filter:v', ','.join(vf)])

    # output
    if args.duration:
        params['t'] = args.duration
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
            base_name += f'_{args.fmt}_{args.enc}'
            if crf:
                base_name += f'_crf{crf}'
            if args.bits:
                base_name += f'_bits{args.bits}'
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
