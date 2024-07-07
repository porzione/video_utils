#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YouTube recommended upload encoding settings for ffmpeg
https://support.google.com/youtube/answer/1722171
"""

import sys
import os.path
import json
import argparse
#from pprint import pprint, pformat
from mymediainfo import MyMediaInfo
from lib import run_cmd, ENCODERS

class YouTube:

    DEFAULT_YT_CATEGORY = 'HDR'

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-i', dest='in_file', required=True, type=str,
                          help='Input file')
        parser.add_argument('-o', dest='out_file', required=True, type=str,
                          help='Output file')
        parser.add_argument('--yt-cat', dest='yt_cat', type=str,
                          default=self.DEFAULT_YT_CATEGORY,
                          help='YouTube category (default: %(default)s)')
        parser.add_argument('--crf', help='CRF / CQP / disable bitrate control')
        parser.add_argument('--enc', default='sw',
                            help='Encoder (%(default)s)')
        parser.add_argument('--opencl', action='store_true')
        parser.add_argument('--deint', action='store_true',
                            help='deinterlace')
        parser.add_argument('--preset', default='slow',
                            help='ffmpeg preset (%(default)s)')
        parser.add_argument('-t', dest='duration')
        parser.add_argument('--dry', action='store_true',
                            help='Dry run')
        self.args = parser.parse_args()

        if not self.args.enc in ENCODERS:
            raise ValueError(f"Bad encoder '{self.args.enc}', use one of {ENCODERS}")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        conf_path = os.path.join(script_dir, 'youtube.json')

        with open(conf_path, 'r', encoding="utf-8") as file:
            self.conf = json.load(file)

        self.mi = MyMediaInfo(self.args.in_file)
        self.mi.print()
        self.get_params()

    # frame rate, list of frame rates, list of bit rates
    def estimate_bitrate(self, frame_rate, fr_list, br_list):
        # print(f'estimate_bitrate frame_rate:{frame_rate} fr_list:{fr_list} br_list:{br_list}')
        frame_rate1 = fr_list[0]
        bitrate1 = br_list[0]
        frame_rate2 = fr_list[-1]
        bitrate2 = br_list[-1]

        estimated_bitrate = (
            bitrate1 +
            ((bitrate2 - bitrate1) / (frame_rate2 - frame_rate1)) *
            (frame_rate - frame_rate1)
        )

        return int(estimated_bitrate)

    def get_params(self):
        height_p = f'{self.mi.height()}p'
        frame_rate = int(float(self.mi.frame_rate()))
        for mode in self.conf[self.args.yt_cat]:
            if frame_rate in mode['FrameRates'] and height_p in mode['Bitrates']:
                self.vbitrate = mode['Bitrates'][height_p]
                if isinstance(self.vbitrate, list):
                    self.vbitrate = self.estimate_bitrate(frame_rate,
                                                          mode['FrameRates'],
                                                          mode['Bitrates'][height_p])
                print(f"YT category: {mode['Category']}")
        if not hasattr(self, 'vbitrate'):
            print('no profile')
            sys.exit(1)
        print(f"YT bitrate: {self.vbitrate} Mbps")
        self.gop = frame_rate // 2
        print(f"YT GOP: {self.gop}")

    def run(self):
        cmd = ['ffmpeg', '-hide_banner', '-nostdin']
        params_in = {}
        filter_v = {}
        match self.args.enc:
            case 'amf':
                params = {
                    'c:v': 'h264_amf',
                    'usage': 'lowlatency_high_quality',
                    'profile': 'high',
                    'quality': 'quality',
                }
                if self.args.crf:
                    params['rc'] = 'cqp'
                    params['qp_i'] = self.args.crf
                    params['qp_p'] = self.args.crf
                    params['qp_b'] = self.args.crf
            case 'vaapi':
                # ffmpeg -hide_banner -h encoder=h264_vaapi|less
                params_in = {
                    'threads': '1',
                    'hwaccel': 'vaapi',
                    'hwaccel_output_format': 'vaapi',
                    'vaapi_device': '/dev/dri/renderD128',
                }
                params = {
                    'c:v': 'h264_vaapi',
                    'compression_level': '29',
                    # 'quality': '0' # def -1
                }
                if self.mi.bit_depth() == 8:
                    params['profile:v'] = 'high'
                else:
                    params['profile:v'] = 'high10'
                if self.args.crf:
                    params['rc_mode'] = 'CQP'
                    params['qp'] = self.args.crf
            case 'nv':
                params_in = {
                    'hwaccel': 'cuda',
                    'hwaccel_output_format': 'cuda',
                }
                params = {
                    'c:v': 'h264_nvenc',
                    'preset': 'p5', # p6,p7
                    'tune': 'hq',
                    'profile': 'high',
                }
                if self.mi.bit_depth() == 10:
                    filter_v['format'] = 'p010le'
                if self.args.crf:
                    params['fps_mode'] = 'passthrough'
                    params['rc'] = 'constqp'
                    params['qp'] = self.args.crf
            case 'sw':
                params = {
                    'c:v': 'libx264',
                    'preset': self.args.preset,
                    'bf': '2', # maximum number of B-frames between non-B-frames
                }
                if self.args.opencl:
                    params_in['hwaccel'] = 'auto'
                    params['x264opts'] = 'opencl'
                if self.mi.bit_depth() == 8:
                    filter_v['format'] = 'yuv420p'
                    params['profile:v'] = 'high'
                else:
                    filter_v['format'] = 'yuv420p10le'
                    params['profile:v'] = 'high422'
                if self.args.crf:
                    # for 10 bit params['qp'] = 0
                    params['crf'] = self.args.crf

        if self.args.deint:
            filter_v['bwdif'] = 'mode=send_field:parity=auto:deint=all'

        if self.mi.has_audio():
            params['c:a'] = 'aac'
            channels = self.mi.audio_channels()
            params['ac'] = str(channels)
            if channels == 1:
                # force stereo
                params['ac'] = '2'
                abr = 256
            elif channels == 2:
                abr = 384
            else:
                abr = 512
            params['b:a'] = f'{abr}k'
            if self.mi.audio_sampling_rate() <= 48000:
                ar = 48000
            else:
                ar = 96000
            params['ar'] = str(ar)
        else:
            cmd.append('-an')

        if not self.args.crf:
            params['b:v'] = f'{self.vbitrate}M'
            mr = f'{int(self.vbitrate*1.2)}M'
            params['maxrate:v'] = mr
            params['bufsize'] =  mr
        #params['r'] = f'{self.mi.frame_rate()}'
        #params['g'] = f'{self.gop}'
        params['force_key_frames'] = 'expr:gte(t,n_forced/2)'
        params['flags'] = 'cgop'
        params['movflags'] = '+faststart'
        params['use_editlist'] = '0'
        params['coder'] = 'cabac'
        if self.args.duration:
            params['t'] = self.args.duration

        # input
        for key, value in params_in.items():
            cmd.extend([f'-{key}', value])
        cmd.extend(['-i', self.args.in_file])
        # output
        for key, value in params.items():
            cmd.extend([f'-{key}', value])
        # filters
        if filter_v:
            vf = [f"{key}={value}" for key, value in filter_v.items()]
            cmd.extend(['-filter:v', ','.join(vf)])

        cmd.append('-y')
        cmd.append(self.args.out_file)

        run_cmd(cmd, self.args.dry)


def __main__():
    yt = YouTube()
    yt.run()

if __name__ == '__main__':
    __main__()
