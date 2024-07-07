#!/usr/bin/env python3
"""
mass video copy/transcode/scale
"""

import argparse
from timeit import default_timer as timer
import os
import sys
import shutil
#from pprint import pprint
import magic
import dateparser
from mymediainfo import MyMediaInfo
from lib import format_time, run_cmd, ENCODERS, VAAPI_IN

RESOLUTIONS = ('720', '1080', '1440', '1620', '2160')
DEF_RES = '1440'
HEVC_DEF_PRESET = 'medium'
SVTAV1_PRESETS = (0,13) # range
SVTAV1_DEF_PRESET = '6'
DNXHR = ('lb', 'sq', 'hq', 'hqx', '444')
NVENC_DEF_PRESET='p5' # p7=2pass
NVENC_DEF_TUNE='hq'
FORMATS = ('dnxhr', 'hevc', 'av1')
FORMAT_EXTENSIONS = {
    'av1': 'MP4',
    'hevc': 'MOV',
    'dnxhr': 'MOV',
}
BIT_DEPTHS = {'8', '10'}
CRF = {
    'hevc': '18', # 20
    'av1': '28', # 30, default 35
    'nv': '19',
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
parser.add_argument('--res', default=DEF_RES, choices=RESOLUTIONS,
                    help='Resolution (%(default)s)')
parser.add_argument('--fmt', default='hevc', choices=FORMATS,
                    help='Target format (%(default)s)')
parser.add_argument('--preset', help='Preset HEVC/SVT-AV1/NVENC')
parser.add_argument('--tune', help='Tune HEVC/SVT-AV1/NVENC')
parser.add_argument('--crf', help=f'CRF/quality ({CRF})')
parser.add_argument('--params', help='Param HEVC/SVT-AV1')
parser.add_argument('--dnx', choices=DNXHR, help='DNxHR profile')
parser.add_argument('--enc', default='sw', choices=ENCODERS,
                    help='Encoder (%(default)s)')
parser.add_argument('--bits', choices=BIT_DEPTHS, help='Force bit depth')
parser.add_argument('--nometa', action='store_true',
                    help='Do not map metadata')
parser.add_argument('--fnparams', action='store_true',
                    help='Add params to dest file names')
parser.add_argument('-t', dest='duration')
parser.add_argument('-1', dest='first', action='store_true',
                    help='only 1st found file')
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
#print(args) ; exit()

crf = args.crf if args.crf else CRF.get(args.enc) or CRF[args.fmt]
if crf:
    print(f'CRF: {crf}')

preset = None
if args.preset:
    preset = args.preset
else:
    if args.enc == 'nv':
        preset = NVENC_DEF_PRESET
    elif args.enc == 'sw':
        if args.fmt == 'hevc':
            preset = HEVC_DEF_PRESET
        elif args.fmt == 'av1':
            preset = SVTAV1_DEF_PRESET
if preset:
    print(f'Preset: {preset}')

if args.newer:
    args.newer = dateparser.parse(args.newer).timestamp()

def v_transcode(src, dst, info):
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-ignore_editlist', '1']
    params_in = {}
    filter_v = {}
    if info.is_hq():
        params = { 'c:v': 'copy' }
    elif args.fmt == 'dnxhr':
        # dnxhr_lb   Low Bandwidth. 8-bit 4:2:2 (yuv422p). Offline Quality. 22:1
        # dnxhr_sq   Standard Quality. 8-bit 4:2:2 (yuv422p). Suitable for delivery. 7:1
        # dnxhr_hq   High Quality. 8-bit 4:2:2 (yuv422p). 4.5:1
        # dnxhr_hqx  High Quality. 10-bit 4:2:2 (yuv422p10le). UHD/4K Broadcast-quality. 5.5:1
        # dnxhr_444  Finishing Quality. 10-bit 4:4:4 (yuv444p10le). Cinema-quality. 4.5:1
        bit_depth = args.bits or str(info.bit_depth())
        params = {'c:v': 'dnxhd'}
        filter_v['format'] = 'yuv422p' if bit_depth == '8' else 'yuv422p10le'
        default_profile = 'dnxhr_hq' if bit_depth == '8' else 'dnxhr_hqx'
        params['profile:v'] = f'dnxhr_{args.dnx}' if args.dnx else default_profile

    elif args.fmt == 'hevc':
        # http://trac.ffmpeg.org/wiki/Encode/H.265
        bit_depth = args.bits or '10'
        match args.enc:
            # https://trac.ffmpeg.org/wiki/Hardware/AMF
            # https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/FFmpeg-and-AMF-HW-Acceleration
            case 'amf':
                params = {
                    'c:v': 'hevc_amf',
                    'usage': 'lowlatency_high_quality',
                    'quality': 'quality',
                    'rc:v': 'cqp',
                    'qp_p': crf,
                    'qp_i': crf,
                }
                if bit_depth == '10':
                    filter_v['format'] = 'yuv420p10le'
            case 'vaapi':
                # https://trac.ffmpeg.org/wiki/Hardware/VAAPI
                # https://ffmpeg.org//ffmpeg-codecs.html#VAAPI-encoders
                params_in = VAAPI_IN
                params = {
                    'c:v': 'hevc_vaapi',
                    'rc_mode': 'CQP',
                    'compression_level': '29',
                    'qp': crf,
                    'tier': 'high',
                }
            case 'nv':
                # https://docs.nvidia.com/video-technologies/video-codec-sdk/12.0/ffmpeg-with-nvidia-gpu/index.html
                # https://developer.nvidia.com/blog/nvidia-ffmpeg-transcoding-guide/
                params_in = {
                    'hwaccel': 'cuda',
                    # keeps the decoded frames in GPU memory
                    'hwaccel_output_format': 'cuda'
                }
                params = {
                    'c:v': 'hevc_nvenc',
                    'preset:v': preset,
                    'tune:v': args.tune or NVENC_DEF_TUNE,
                    'rc:v': 'vbr',
                    'cq:v': crf,
                    'b:v': '0',
                    'tier': 'high',
                    #'profile:v': 'high',
                }
                if bit_depth == '10':
                    params['profile:v'] = 'main10'
            case 'sw':
                # https://x265.readthedocs.io/en/stable/
                params = {
                    'c:v': 'libx265',
                    'preset': preset,
                    'crf': crf, # default 28
                    'x265-params': 'level-idc=5.1'
                }
                if bit_depth == '10':
                    params['profile:v'] = 'main10'
                    filter_v['format'] = 'yuv420p10le'
                if args.tune:
                    params['x265-params'] += f':tune={args.tune}'
                if args.params:
                    params['x265-params'] += f':{args.params}'
    elif args.fmt == 'av1':
        # https://trac.ffmpeg.org/wiki/Encode/AV1
        bit_depth = args.bits or '10'
        match args.enc:
            case 'amf':
                params = {
                    'c:v': 'av1_amf',
                    'quality': 'quality',
                    'usage': 'transcoding',
                }
            case 'vaapi':
                params_in = VAAPI_IN
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
                    'preset': preset,
                    'tune': 'hq',
                }
            case 'sw':
                params = {
                    'c:v': 'libsvtav1',
                    'preset': preset,
                    'crf': crf,
                    'svtav1-params': 'rc=0:film-grain-denoise=0:enable-overlays=1',
                }
                if bit_depth == '8':
                    filter_v['format'] = 'yuv422p'
                elif bit_depth == '10':
                    filter_v['format'] = 'yuv420p10le'
                    params['svtav1-params'] += ':input-depth=10'
                if args.tune:
                    params['svtav1-params'] += f':tune={args.tune}'
                if args.params:
                    params['svtav1-params'] += f':{args.params}'

    if info.height() > int(args.res) and not args.dns:
        match args.enc:
            case 'nv':
                # scale_cuda | scale_npp (`--enable-cuda-nvcc`)
                filter_v['scale_cuda'] = f'w=-1:h={args.res}:interp_algo=lanczos'
                if bit_depth == '10':
                    filter_v['scale_cuda'] += ':format=p010le'
            case 'vaapi':
                # mode=hq|nl_anamorphic
                filter_v['scale_vaapi'] = f'w=-1:h={args.res}:mode=hq:force_original_aspect_ratio=1'
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
    return run_cmd(cmd, args.dry)

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
            if args.res and not args.dns:
                base_name += f'_res{args.res}'
            if args.preset:
                base_name += f'_pr{args.preset}'
            if args.tune:
                base_name += f'_tun{args.tune}'
            if args.dnx:
                base_name += f'_dnx{args.dnx}'
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
            rc = v_transcode(src_file, dst_file, mi)
            if rc != 0:
                print(f'v_transcode failed with code: {rc}')
                if os.path.exists(dst_file) and os.path.getsize(dst_file) == 0:
                    os.remove(dst_file)
                    sys.exit(1)

        end_time = timer() - start_time
        print(f"TIME {format_time(end_time)}\n")
        TOTAL_TIME += end_time
        if args.first:
            break

print(f"TOTAL TIME: {format_time(TOTAL_TIME)}")
