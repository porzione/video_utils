#!/usr/bin/env python3
"""
mass video copy/transcode/scale
"""

import argparse
from timeit import default_timer as timer
import os
import sys
import shutil
import magic
import dateparser
from mymediainfo import MyMediaInfo
from lib import format_time, run_cmd, ENCODERS, VAAPI_IN

# 1920x1080 2560x1440 3840x2160
RESOLUTIONS = ('1080', '1440', '2160')
DEF_RES = '1440'
HEVC_PRESETS = {
    '1080': 'fast',
    '1440': 'medium',
    '2160': 'slow'
}
SVTAV1_PRESETS = {
    '1080': '7',
    '1440': '6',
    '2160': '4'
}
NVENC_PRESETS = {
    '1080': 'p6',
    '1440': 'p6',
    '2160': 'p7'  # 2 pass, archiving
}
NVENC_DEF_TUNE='hq'
VAAPI_DEF_CL = '29' # 1 AMD
# VBAQ=16 (not with CQP), pre-encode=8, quality=4, preset=2, speed=0
# And at the end, the validity bit (bit0) is set to 1
DNXHR = {
    'lb':   'yuv422p',     # Offline Quality. 22:1
    'sq':   'yuv422p',     # Suitable for delivery. 7:1
    'hq':   'yuv422p',     # 4.5:1
    'hqx':  'yuv422p10le', # UHD/4K Broadcast-quality. 5.5:1
    '444':  'yuv444p10le', # Cinema-quality. 4.5:1
}
DNXHR_DEFAULT = 'hqx'
FORMATS = ('dnxhr', 'hevc', 'av1')
FORMAT_EXTENSIONS = {
    'av1': 'MP4',
    'hevc': 'MOV',
    'dnxhr': 'MOV',
}
CRF = {
    'hevc': '18',  # default 28, 0-51
    'av1': '20',   # default 35
    'nv': '19',    # default -1, vbr/cq
    'vaapi': '21', # default 0,25 for ~same size/br as sw, 0-52, CQP/qp
    'amf': '21',   # default -1, CQP/qp_X
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
parser.add_argument('--crf', help=f'crf/quality ({CRF})')
parser.add_argument('--params', help='Param HEVC/SVT-AV1')
parser.add_argument('--dnx', choices=DNXHR.keys(), help='DNxHR profile')
parser.add_argument('--enc', default='sw', choices=ENCODERS,
                    help='Encoder (%(default)s)')
parser.add_argument('--bit', choices=[8, 10], type=int,
                    help='Force bit depth')
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

crf = args.crf if args.crf else CRF.get(args.enc) or CRF.get(args.fmt)

if args.newer:
    args.newer = dateparser.parse(args.newer).timestamp()

def dnxhr_profile():
    """ return: short profile name """
    return (args.dnx if args.dnx else DNXHR_DEFAULT)

def transcode(src, dst, info):
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-ignore_editlist', '1']
    params_in = {}
    filter_v = {}
    if info.is_hq():
        params = { 'c:v': 'copy' }
    bit_depth = args.bit or 10
    if args.fmt == 'dnxhr':
        params = {'c:v': 'dnxhd'}
        profile = dnxhr_profile()
        filter_v['format'] = DNXHR[profile]
        params['profile:v'] = f'dnxhr_{profile}'

    elif args.fmt == 'hevc':
        # http://trac.ffmpeg.org/wiki/Encode/H.265
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
                    'preencode': '1',
                    'profile_tier': 'high',
                    # enforce_hrd
                }
                if bit_depth == 10:
                    filter_v['format'] = 'yuv420p10le'
            case 'vaapi':
                # https://trac.ffmpeg.org/wiki/Hardware/VAAPI
                # https://ffmpeg.org//ffmpeg-codecs.html#VAAPI-encoders
                # https://www.tauceti.blog/posts/linux-ffmpeg-amd-5700xt-hardware-video-encoding-hevc-h265-vaapi/
                params_in = VAAPI_IN
                params = {
                    'c:v': 'hevc_vaapi',
                    'rc_mode': 'CQP',
                    'compression_level': VAAPI_DEF_CL,
                    'qp': crf, # 0-52
                    'tier': 'high',
                }
                if bit_depth == 10:
                    params['profile:v'] = 'main10'
            case 'nv':
                # https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/ffmpeg-with-nvidia-gpu/index.html
                # https://docs.nvidia.com/video-technologies/video-codec-sdk/12.1/nvenc-preset-migration-guide/index.html
                # https://developer.nvidia.com/blog/calculating-video-quality-using-nvidia-gpus-and-vmaf-cuda/
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
                    'qmin:v': crf,
                    'qmax:v': crf,
                    'b:v': '0',
                    'tier': 'high',
                    #'profile:v': 'high',
                }
                if bit_depth == 10:
                    params['profile:v'] = 'main10'
            case 'sw':
                # https://x265.readthedocs.io/en/stable/
                params = {
                    'c:v': 'libx265',
                    'preset': preset,
                    'crf': crf, # default 28
                }
                x265params = []
                if bit_depth == 10:
                    params['profile:v'] = 'main10'
                    filter_v['format'] = 'yuv420p10le'
                if args.tune:
                    x265params.append(f'tune={args.tune}')
                if args.params:
                    x265params.append(f'{args.params}')
                if x265params:
                    params['x265-params'] = ':'.join(x265params)
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
                params_in = VAAPI_IN
                params = {
                    'c:v': 'av1_vaapi',
                    'compression_level': VAAPI_DEF_CL,
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
                }
                av1params = ['rc=0:film-grain-denoise=0:enable-overlays=1']
                if bit_depth == 8:
                    filter_v['format'] = 'yuv422p'
                elif bit_depth == 10:
                    filter_v['format'] = 'yuv420p10le'
                av1params.append(f'input-depth={bit_depth}')
                if args.tune:
                    av1params.append(f'tune={args.tune}')
                if args.params:
                    av1params.append(f'{args.params}')
                params['svtav1-params'] = ':'.join(av1params)

    scale = info.height() > int(args.res) and not args.dns
    flt = []
    match args.enc:
        case 'nv':
            # hevc_nvenc: yuv420p nv12 p010le cuda
            if scale:
                flt.append(f'w=-1:h={args.res}:interp_algo=lanczos')
            if bit_depth == 10:
                flt.append('format=p010le')
            filter_v['scale_cuda'] = ':'.join(flt)
        case 'vaapi':
            # hevc_vaapi: vaapi [nv12 yuv420p p010 yuy2]
            if scale:
                # mode=hq|nl_anamorphic
                flt.append(f'w=-1:h={args.res}:mode=hq:force_original_aspect_ratio=1')
            if bit_depth == 10:
                flt.append('format=p010')
            filter_v['scale_vaapi'] = ':'.join(flt)
        case _:
            if scale:
                # libx265: yuv420p yuv422p yuv420p10le yuv422p10le gray gray10le
                # libsvtav1: yuv420p yuv420p10le
                filter_v['scale'] = f'w=-1:h={args.res}:{DSCALE_FLAGS}'
        # hevc_amf: nv12 yuv420p
        # hevc_qsv: nv12 p010le

    if not args.nometa:
        params['movflags'] = 'use_metadata_tags' # mov, mp4

    # input
    for key, value in params_in.items():
        cmd.extend([f'-{key}', value])
    cmd.extend(['-i', src])

    if not args.nometa:
        params['map_metadata'] = '0:g' # global
        #params['map_metadata:s:v'] = '0:s:v'
        #params['map_metadata:s:a'] = '0:s:a'

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

def copy(src, dst):
    print(f"COPY {src} {dst}")
    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)


TOTAL_TIME = 0.0
for filename in os.listdir(args.srcdir):
    src_file = os.path.join(args.srcdir, filename)
    if os.path.isfile(src_file):

        mime_type = magic.from_file(src_file, mime=True)
        #print(f'MIME {mime_type}')
        if not mime_type or not mime_type.startswith('video'):
            continue
        print(f'FILE {src_file}')

        mi = MyMediaInfo(src_file)

        if args.dns:
            args.res = str(mi.height())
        print(f'> res: {args.res}')
        preset = None
        if args.preset:
            preset = args.preset
        elif args.enc == 'nv':
            preset = NVENC_PRESETS.get(args.res, 'p4')
        elif args.enc == 'sw':
            if args.fmt == 'hevc':
                preset = HEVC_PRESETS.get(args.res, 'medium')
            elif args.fmt == 'av1':
                preset = SVTAV1_PRESETS.get(args.res, '6')

        ext = FORMAT_EXTENSIONS.get(args.fmt)
        base_name = os.path.splitext(filename)[0]
        if args.fnparams:
            if args.fmt == 'dnxhr':
                dnxp = dnxhr_profile()
                base_name += f'_{args.fmt}_{dnxp}'
            else:
                base_name += f'_{args.fmt}_{args.enc}'
            if crf:
                base_name += f'_crf={crf}'
            if args.bit:
                base_name += f'_bit={args.bit}'
            base_name += f'_res={args.res}'
            if preset:
                base_name += f'_p={preset}'
            if args.tune:
                base_name += f'_tun={args.tune}'
        dst_file = os.path.join(args.dstdir, f'{base_name}.{ext}')
        if os.path.exists(dst_file):
            print(f'EXISTS {dst_file}')
            if not args.dry:
                continue

        if crf:
            print(f'> crf: {crf}')
        if preset:
            print(f'> preset: {preset}')
        if args.fmt == 'dnxhr' and dnxp:
            print(f'> DNxHR profile: {dnxp}')
        mi.print()

        if args.newer and os.path.getmtime(src_file) < args.newer:
            continue

        start_time = timer()
        if args.copy:
            copy(src_file, dst_file)
        else:
            rc = transcode(src_file, dst_file, mi)
            if rc != 0:
                print(f'transcode failed with code: {rc}')
                if os.path.exists(dst_file) and os.path.getsize(dst_file) == 0:
                    os.remove(dst_file)
                sys.exit(rc)

        end_time = timer() - start_time
        print(f"TIME {format_time(end_time)}\n")
        TOTAL_TIME += end_time
        if args.first:
            break

print(f"TOTAL TIME: {format_time(TOTAL_TIME)}")
