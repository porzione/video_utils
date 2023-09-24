#!/usr/bin/env python3
"""
copy / dnxhd encode videos to dnxhd
"""

import argparse
from timeit import default_timer as timer
import os
import mimetypes
import shutil
#from pprint import pprint
import dateparser
from pymediainfo import MediaInfo
from lib import format_time, run_cmd

# HD FHD 2K UHD 4K
# dnxhr_resolutions = ['1280x720', '1920x1080', '2048x1080', '3840x2160', '4096x2160']

parser = argparse.ArgumentParser(description='Video Copy Script')
# parser.add_argument('-D', '--debug', action='store_true', help='Enable debug output')
parser.add_argument('-s', '--srcdir', help='Source directory')
parser.add_argument('-d', '--dstdir', help='Destination directory')
parser.add_argument('-n', '--newer', help='Newer than')
parser.add_argument('--copy', action='store_true', help='Copy as is')
args = parser.parse_args()

if args.srcdir is None:
    raise ValueError('Need source directory')
if args.dstdir is None:
    raise ValueError('Need target directory')
if not os.path.exists(args.srcdir):
    raise ValueError(f"Source dir '{args.srcdir}' doesn't exist")
if not os.path.exists(args.dstdir):
    raise ValueError(f"Destination dir '{args.dstdir}' doesn't exist")

if args.newer:
    newer_time = dateparser.parse(args.newer).timestamp()

def get_minfo(in_filename):
    minfo = {
        'is_hq': False,
        'audio_fmt': None
    }
    # print(f'INF {in_filename}')
    for track in MediaInfo.parse(in_filename).tracks:
        if track.track_type == 'Video':
            print(f'Video: {track.width}x{track.height} {track.frame_rate} fps')
            print(f'Bit rate: {track.bit_rate/1000000:.2f}')
            print(f'Bit depth: {track.bit_depth}')
            print(f'Format: {track.format}')
            print(f'Color: {track.color_space} {track.chroma_subsampling}')
            if track.format in ['VC-3', 'FFV1', 'ProRes', 'HFYU']:
                minfo['is_hq'] = True
        elif track.track_type == 'Audio':
            minfo['audio_fmt'] = f'{track.format} {track.format_settings}'
            print(f"Audio: {minfo['audio_fmt']} {track.bit_depth} bit")
    return minfo

def v_transcode(src, dst, info):
    cmd = ['ffmpeg', '-i', src]

    params = {
        'vcodec': 'dnxhd',
        'profile:v': 'dnxhr_hq',
        'pix_fmt': 'yuv422p',
        'map_metadata': '0'
    }

    if info['audio_fmt'] is None:
        cmd.append('-an')
    elif info['audio_fmt'] == 'PCM Little / Signed':
        params['acodec'] = 'copy'
    else:
        params['acodec'] = 'pcm_s16le'
        params['ar']= '48000'

    for key, value in params.items():
        cmd.extend([f'-{key}', value])

    cmd.append(dst)
    run_cmd(cmd)

def v_copy(src, dst):
    print(f"COPY {src} {dst}")
    shutil.copy2(src, dst)
    os.chmod(dst_file, 0o644)

TOTAL_TIME = 0.0
for filename in os.listdir(args.srcdir):
    src_file = os.path.join(args.srcdir, filename)
    if os.path.isfile(src_file):

        base_name = os.path.splitext(filename)[0]
        dst_file = os.path.join(args.dstdir, f'{base_name}.MOV')
        if os.path.exists(dst_file):
            print(f'EXISTS {dst_file}')
            continue

        mime_type, _enc = mimetypes.guess_type(src_file)
        if not mime_type or not mime_type.startswith('video'):
            continue
        print(f'FILE {src_file}')
        print(f'MIME {mime_type}')

        mi = get_minfo(src_file)
        if mi['is_hq']:
            print('already HQ video')
            continue

        mod_time = os.path.getmtime(src_file)
        if args.newer and mod_time < newer_time:
            continue
        start_time = timer()

        if args.copy:
            v_copy(src_file, dst_file)
        else:
            v_transcode(src_file, dst_file, mi)

        end_time = timer() - start_time
        print(f"TIME {format_time(end_time)}")
        TOTAL_TIME += end_time

print(f"TOTAL TIME: {format_time(TOTAL_TIME)}")
