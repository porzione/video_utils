#!/usr/bin/env python3
""" parse cli arguments """

import argparse
import os
import sys
import importlib
import dateparser
import lib
#import enc_dnxhr
#import enc_prores
#import enc_cineform

def parse_args():
    """ return: args, crf, encoder module """

    parser = argparse.ArgumentParser(description='Video copy/scale/convert')
    parser.add_argument('-s', dest='src_path', help='Source file or directory')
    parser.add_argument('-d', dest='dst_dir', help='Destination directory')
    parser.add_argument('-n', '--newer', help='Newer than')
    parser.add_argument('--copy', action='store_true', help='Copy as is')
    parser.add_argument('--res', type=int, choices=lib.RESOLUTIONS,
                        help='Resolution')
    parser.add_argument('--fmt', default='hevc', choices=lib.FORMATS,
                        help='Target format (%(default)s)')
    parser.add_argument('--preset', help='Preset HEVC/NVENC')
    parser.add_argument('--tune', help='Tune HEVC/NVENC')
    parser.add_argument('--crf', type=int, help=f'crf/quality ({lib.CRF})')
    parser.add_argument('--gop', type=float,
                        help='gop, float multiplier of fps')
    parser.add_argument('--params', help='Params HEVC')
    parser.add_argument('--profile', help='DNxHR/ProRes/CineForm profile')
    parser.add_argument('--enc', default='x265', choices=lib.ENCODERS,
                        help='Encoder (%(default)s)')
    parser.add_argument('--bits', choices=[8, 10], type=int,
                        help='Bit depth')
    parser.add_argument('--all-i', action='store_true', dest='all_i',
                        help='All Intra')
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

    if args.src_path is None:
        sys.exit('Need source directory or file')
    if args.dst_dir is None:
        sys.exit('Need target directory')
    if not os.path.exists(args.src_path):
        sys.exit(f"Source dir or file '{args.src_path}' doesn't exist")
    if not os.path.exists(args.dst_dir):
        sys.exit(f"Destination dir '{args.dst_dir}' doesn't exist")

    crf = args.crf if args.crf else lib.CRF.get(args.enc) or lib.CRF.get(args.fmt)

    if args.newer:
        args.newer = dateparser.parse(args.newer).timestamp()

    if args.fmt in ('dnxhr', 'prores', 'cineform'):
        enc_mod = importlib.import_module(f'enc_{args.fmt}')
    elif args.fmt == 'hevc':
        enc_mod = importlib.import_module(f'enc_{args.fmt}_{args.enc}')
    else:
        sys.exit(f"Unsupported encoder format/type: {args.fmt}{args.enc}")

    return args, crf, enc_mod
