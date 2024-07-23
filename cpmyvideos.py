#!/usr/bin/env python3
""" mass video copy/transcode/scale """

import argparse
from timeit import default_timer as timer
import os
import sys
import shutil
import importlib
import magic
import dateparser
from mymediainfo import MyMediaInfo
import lib
import enc_dnxhr

# 1920x1080 2560x1440 3840x2160
RESOLUTIONS = (1080, 1440, 2160)

FORMATS = ('dnxhr', 'hevc')
# downscale: Lanczos/Spline, upscale: Bicubic/Lanczos
# error diffusion dithering to minimize banding +dither=error_diffusion
DSCALE_FLAGS = 'flags=lanczos+accurate_rnd+full_chroma_int'

parser = argparse.ArgumentParser(description='Video copy/scale/convert')
parser.add_argument('-s', '--srcdir', help='Source directory')
parser.add_argument('-d', '--dstdir', help='Destination directory')
parser.add_argument('-n', '--newer', help='Newer than')
parser.add_argument('--copy', action='store_true', help='Copy as is')
parser.add_argument('--res', type=int, choices=RESOLUTIONS,
                    help='Resolution (%(default)s)')
parser.add_argument('--fmt', default='hevc', choices=FORMATS,
                    help='Target format (%(default)s)')
parser.add_argument('--preset', help='Preset HEVC/NVENC')
parser.add_argument('--tune', help='Tune HEVC/NVENC')
parser.add_argument('--crf', type=int, help=f'crf/quality ({lib.CRF})')
parser.add_argument('--gop', type=float,
                    help='gop, float multiplier of fps')
parser.add_argument('--params', help='Params HEVC')
parser.add_argument('--dnx', choices=enc_dnxhr.PROFILES.keys(),
                    help='DNxHR profile')
parser.add_argument('--enc', default='x265', choices=lib.ENCODERS,
                    help='Encoder (%(default)s)')
parser.add_argument('--bits', choices=[8, 10], type=int,
                    help='Bit depth')
parser.add_argument('--nometa', action='store_true',
                    help='Do not map metadata')
parser.add_argument('--fnparams', action='store_true',
                    help='Add params to dest file names')
parser.add_argument('-t', type=int, dest='duration')
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

crf = args.crf if args.crf else lib.CRF.get(args.enc) or lib.CRF.get(args.fmt)

if args.newer:
    args.newer = dateparser.parse(args.newer).timestamp()

def transcode(src, dst, info, enc_mod):
    video = lib.Video(
        bits = args.bits or 10,
        bits_in = info.bit_depth,
        crf = crf,
        gop = lib.gop(info.frame_rate, args.gop),
        params = args.params,
        preset = args.preset,
        tune = args.tune,
        color_format = info.color_format,
        frame_rate = info.frame_rate,
        dnx = args.dnx,
        res = args.res or info.width,
        color_primaries = info.color_primaries,
        matrix_coefficients = info.matrix_coefficients,
        transfer_characteristics = info.transfer_characteristics,
    )
    encoder = enc_mod.Encoder(video)

    if hasattr(encoder, 'CMD'):
        cmd = encoder.CMD.copy()
    else:
        cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-ignore_editlist', '1']

    need_scale = args.res and args.res < info.height
    filter_v = encoder.get_filter(scale=need_scale)
    if need_scale and not encoder.can_scale:
        filter_v.append({'scale': f'w=-1:h={args.res}:{DSCALE_FLAGS}'})
    #print(f'filter_v: {filter_v}')

    params = encoder.get_params()

    if not args.nometa and not hasattr(encoder, 'CMD'):
        params['movflags'] = 'use_metadata_tags' # mov, mp4

    # input
    params_in = {}
    if hasattr(encoder, 'get_params_in'):
        params_in.update(encoder.get_params_in())
    for key, val in params_in.items():
        cmd.extend([f'-{key}', val if isinstance(val, str) else str(val)])
    cmd.extend(['-i', src])

    if not args.nometa:
        if hasattr(encoder, 'CMD'):
            params['-metadata'] = 'copy'
            params['-video-metadata'] = 'copy'
            params['-audio-metadata'] = 'copy'
        else:
            params['map_metadata'] = '0:g'
            params['map_metadata:s:v'] = '0:s:v'
            params['map_metadata:s:a'] = '0:s:a'

    # audio
    if hasattr(encoder, 'CMD'):
        if info.audio_format:
            params['-audio-codec'] = 'copy'
    else:
        match info.audio_format:
            case None:
                cmd.append('-an')
            case 'PCM Little / Signed':
                params['c:a'] = 'copy'
            case _:
                if args.fmt == 'dnxhr':
                    params['c:a'] = 'pcm_s16le'
                    params['ar']= '48000'
                else:
                    params['c:a'] = 'copy'

    # filters
    if filter_v:
        if hasattr(encoder, 'CMD'):
            cmd.extend(filter_v)
        else:
            items = lib.join_filters(filter_v)
            #print(f'items: {items} from filter_v: {filter_v}')
            cmd.extend(['-filter:v', items])
    #print(cmd) ; return 0

    # output
    if args.duration:
        if hasattr(encoder, 'CMD'):
            params['-frames'] = int(args.duration*float(info.frame_rate))
        else:
            params['t'] = args.duration
    for key, val in params.items():
        cmd.extend([f'-{key}', val if isinstance(val, str) else str(val)])

    if hasattr(encoder, 'CMD'):
        cmd.extend(['-o', dst])
    else:
        cmd.append(dst)
    return lib.run_cmd(cmd1=cmd, dry=args.dry)

def copy(src, dst):
    print(f"COPY {src} {dst}")
    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)


if args.fmt == 'dnxhr':
    ENC_MOD = enc_dnxhr
elif args.fmt == 'hevc':
    ENC_MOD = importlib.import_module(f'enc_{args.fmt}_{args.enc}')
else:
    raise ValueError(f"Unsupported encoder format/type: {args.fmt}{args.enc}")

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

        debug = []
        if args.res:
            debug.append(f'res: {args.res}')

        base_name = os.path.splitext(filename)[0]
        if args.fnparams:
            if args.fmt == 'dnxhr':
                if args.dnx:
                    dnxp = args.dnx
                else:
                    idx = f'{mi.color_format}:{mi.bit_depth}'
                    dnxp = enc_dnxhr.PROFILES_AUTO[idx]
                base_name += f'_{args.fmt}_{dnxp}'
            else:
                base_name += f'_{args.fmt}_{args.enc}'
            if crf:
                base_name += f'_crf{crf}'
            if args.bits:
                base_name += f'_bit{args.bits}'
            if args.res and args.res < mi.height:
                base_name += f'_res{args.res}'
            else:
                base_name += f'_res{mi.height}'
            if args.preset:
                base_name += f'_p-{args.preset}'
            if args.tune:
                base_name += f'_tun={args.tune}'
            if args.gop:
                base_name += f'_gop{lib.gop(mi.frame_rate, args.gop)}'
        dst_file = os.path.join(args.dstdir, f'{base_name}.MOV')
        if os.path.exists(dst_file):
            print(f'EXISTS {dst_file}')
            if not args.dry:
                continue

        if crf:
            debug.append(f'crf: {crf}')
        if args.preset:
            debug.append(f'preset: {args.preset}')
        if args.fmt == 'dnxhr' and dnxp:
            debug.append(f'DNxHR profile: {dnxp}')
        print('\n'.join(map(lambda s: f'> {s}', debug)))
        mi.print()

        if args.newer and os.path.getmtime(src_file) < args.newer:
            continue

        start_time = timer()
        if args.copy:
            copy(src_file, dst_file)
        else:
            RC = transcode(src_file, dst_file, mi, ENC_MOD)
            if RC != 0:
                print(f'transcode failed with code: {RC}')
                if os.path.exists(dst_file) and os.path.getsize(dst_file) == 0:
                    os.remove(dst_file)
                sys.exit(RC)

        if not args.dry:
            end_time = timer() - start_time
            print(f"TIME {lib.format_time(end_time)}\n")
            TOTAL_TIME += end_time
        if args.first:
            break

if not args.dry:
    print(f"TOTAL TIME: {lib.format_time(TOTAL_TIME)}")
