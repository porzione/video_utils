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

DEF_RES = 1440

parser = argparse.ArgumentParser(description='Video Copy Script')
# parser.add_argument('-D', '--debug', action='store_true', help='Enable debug output')
parser.add_argument('-s', '--srcdir', help='Source directory')
parser.add_argument('-d', '--dstdir', help='Destination directory')
parser.add_argument('-n', '--newer', help='Newer than')
parser.add_argument('--copy', action='store_true', help='Copy as is')
parser.add_argument('--keephr', action='store_true',
                    help=f'Keep hi-res, do not convert to {DEF_RES}')
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
    else:
        params = PARAMS_HQ

    if mi['height'] > DEF_RES and not args.keephr:
        params['vf'] = f'scale=-1:{DEF_RES}'
        params['movflags'] = 'write_colr+use_metadata_tags'
        if mi['bit_depth'] == 10:
            params['pix_fmt'] = 'yuv422p10le'
            params['profile:v'] = 'dnxhr_hqx'
        bit_rate = calculate_dnxhr_bitrate(DEF_RES,
                                           params['profile:v'],
                                           mi['frame_rate'],
                                           mi['bit_depth'])
        params['b:v'] = f'{int(bit_rate)}M'

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
