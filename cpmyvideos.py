#!/usr/bin/env python3
""" mass video copy/transcode/scale """

from timeit import default_timer as timer
import os
import sys
import shutil
import magic
from mymediainfo import MyMediaInfo
import argsp
import lib
import enc_dnxhr

def transcode(src, dst, info):
    video = lib.Video(
        bits = args.bits or 10,
        bits_in = info.bit_depth,
        crf = crf,
        gop = lib.gop(info.frame_rate, args.gop),
        all_i = args.all_i,
        params = args.params,
        preset = args.preset,
        tune = args.tune,
        color_format = info.color_format,
        frame_rate = info.frame_rate,
        profile = args.profile,
        res = args.res or info.width,
        color_primaries = info.color_primaries,
        matrix_coefficients = info.matrix_coefficients,
        transfer_characteristics = info.transfer_characteristics,
    )
    encoder = ENC_MOD.Encoder(video)

    if hasattr(encoder, 'CMD'):
        cmd = encoder.CMD.copy()
    else:
        cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-ignore_editlist', '1']

    need_scale = args.res and args.res < info.height
    filter_v = encoder.get_filter(scale=need_scale)
    if need_scale and not encoder.can_scale:
        filter_v.append({'scale': f'w=-1:h={args.res}:{lib.DSCALE_FLAGS}'})
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

    # All-intra
    if args.all_i:
        params['g:v'] = 0

    # filters
    if filter_v:
        if hasattr(encoder, 'CMD'):
            cmd.extend(filter_v)
        else:
            items = lib.join_filters(filter_v)
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

def format_name(name, info):
    if args.fmt == 'dnxhr':
        if args.profile:
            dnxp = args.profile
        else:
            idx = f'{info.color_format}:{info.bit_depth}'
            dnxp = enc_dnxhr.PROFILES_AUTO[idx]
        DEBUG.append(f'DNxHR profile: {dnxp}')
        name += f'_{args.fmt}_{dnxp}'
    elif args.fmt in ('prores', 'cineform'):
        prof = f'_{args.profile}' if args.profile else ''
        name +=  f'_{args.fmt}{prof}'
    else:
        name += f'_{args.fmt}_{args.enc}'
    if crf:
        name += f'_crf{crf}'
    if args.bits:
        name += f'_bit{args.bits}'
    if args.res and args.res < info.height:
        name += f'_res{args.res}'
    else:
        name += f'_res{info.height}'
    if args.preset:
        name += f'_p-{args.preset}'
    if args.tune:
        name += f'_tun={args.tune}'
    if args.gop:
        name += f'_gop{lib.gop(info.frame_rate, args.gop)}'
    if args.all_i:
        name += '_alli'
    return name

def process_file():
    mime_type = magic.from_file(src_file, mime=True)
    #print(f'MIME {mime_type}')
    if not mime_type or not mime_type.startswith('video'):
        return 0
    print(f'FILE {src_file}')

    mi = MyMediaInfo(src_file)

    if args.res:
        DEBUG.append(f'res: {args.res}')

    base_name = os.path.splitext(filename)[0]
    if args.fnparams:
        base_name = format_name(base_name, mi)
    dst_file = os.path.join(args.dst_dir, f'{base_name}.MOV')
    if os.path.exists(dst_file):
        print(f'EXISTS {dst_file}')
        if not args.dry:
            return 0

    if crf:
        DEBUG.append(f'crf: {crf}')
    if args.preset:
        DEBUG.append(f'preset: {args.preset}')
    if DEBUG:
        print('\n'.join(map(lambda s: f'> {s}', DEBUG)))
    mi.print()

    if args.newer and os.path.getmtime(src_file) < args.newer:
        return 0

    start_time = timer()
    if args.copy:
        copy(src_file, dst_file)
    else:
        rcode = transcode(src_file, dst_file, mi)
        if rcode != 0:
            print(f'transcode failed with code: {rcode}')
            if os.path.exists(dst_file) and os.path.getsize(dst_file) == 0:
                os.remove(dst_file)
            sys.exit(rcode)
    end_time = timer() - start_time
    if not args.dry:
        print(f"TIME {lib.format_time(end_time)}\n")
    return end_time

args, crf, ENC_MOD = argsp.parse_args()
DEBUG = []

if os.path.isfile(args.src_path):
    src_file = args.src_path
    filename = os.path.basename(src_file)
    total_time = process_file()
elif os.path.isdir(args.src_path):
    total_time = 0.0 # pylint: disable=invalid-name
    for filename in os.listdir(args.src_path):
        src_file = os.path.join(args.src_path, filename)
        if os.path.isfile(src_file):
            total_time += process_file()
        if args.first:
            break
        DEBUG = []

if not args.dry:
    print(f"TOTAL TIME: {lib.format_time(total_time)}")
