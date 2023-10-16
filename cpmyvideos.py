#!/usr/bin/env python3
"""
copy / dnxhd encode videos to dnxhd
"""

import argparse
from timeit import default_timer as timer
import os
import shutil
#from pprint import pprint
import magic
import dateparser
from pymediainfo import MediaInfo
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
            minfo['height'] = track.height
            minfo['bit_depth'] = track.bit_depth
            minfo['frame_rate'] = track.frame_rate
            if track.format in ['VC-3', 'FFV1', 'ProRes', 'HFYU']:
                minfo['is_hq'] = True
        elif track.track_type == 'Audio':
            minfo['audio_fmt'] = f'{track.format} {track.format_settings}'
            print(f"Audio: {minfo['audio_fmt']} {track.bit_depth} bit")
    return minfo


def calculate_dnxhr_bitrate(resolution, profile, frame_rate, bit_depth):
    base_bitrates = {
        'dnxhr_lb': 92,
        'dnxhr_sq': 410,
        'dnxhr_hq': 880,
        'dnxhr_hqx': 1100,
        'dnxhr_444': 1900
    }

    if profile not in base_bitrates:
        raise ValueError("Invalid DNxHR profile")
    if profile == 'dnxhr_hq' and bit_depth != 8:
        raise ValueError("HQ profile supports only 8-bit depth")
    if (profile in ['dnxhr_hqx', 'dnxhr_444']) and bit_depth != 10:
        raise ValueError("HQX and 444 profiles support only 10-bit depth")

    base_resolution = 1080
    resolution_scale = resolution / base_resolution
    frame_rate_scale = float(frame_rate) / 30
    final_bitrate_mbps = base_bitrates[profile] * resolution_scale * frame_rate_scale
    final_bitrate_MB = final_bitrate_mbps / 8

    print(f"Calculated bit rate: {final_bitrate_MB:.2f} MB/s")
    return final_bitrate_MB

def v_transcode(src, dst, info):
    # 8 bit hq
    PARAMS_HQ = {
        'c:v': 'dnxhd',
        'profile:v': 'dnxhr_hq',
        'pix_fmt': 'yuv422p'
    }

    cmd = ['ffmpeg', '-hide_banner', '-i', src,]

    if mi['is_hq']:
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

        mime_type = magic.from_file(src_file, mime=True)
        if not mime_type or not mime_type.startswith('video'):
            continue
        print(f'FILE {src_file}')
        print(f'MIME {mime_type}')

        mi = get_minfo(src_file)

        mod_time = os.path.getmtime(src_file)
        if args.newer and mod_time < newer_time:
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
