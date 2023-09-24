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
from pymediainfo import MediaInfo
from lib import run_cmd

class YouTube:

    DEFAULT_YT_CATEGORY = 'HDR'

    def __init__(self):
        argp = argparse.ArgumentParser()
        argp.add_argument("-i", dest="infile", required=True, type=str,
                          help="Input file")
        #argp.add_argument("-o", dest="outfile", required=True, type=str,
        #                  help="Outfile")
        argp.add_argument("--yt-cat", dest="yt_cat", type=str,
                          default=self.DEFAULT_YT_CATEGORY,
                          help="YouTube category (default: %(default)s)")
        #argp.add_argument("--conf", dest="conf", type=str,
        #                  default='.json',
        #                  help="Path to config file (default: %(default)s)")
        self.args = argp.parse_args()

        script_dir = os.path.dirname(os.path.abspath(__file__))
        conf_path = os.path.join(script_dir, 'youtube.json')

        with open(conf_path, 'r', encoding="utf-8") as file:
            self.conf = json.load(file)

        self.media_info()
        self.get_params()

    # save info for last track if each type
    def media_info(self):
        mi = MediaInfo.parse(self.args.infile)
        self.audio_channels = 0
        for track in mi.tracks:
            if track.track_type == 'Video':
                self.video_track = track
                frame_rate = int(float(track.frame_rate))
                self.video_track.frame_rate = frame_rate
                bit_rate = track.bit_rate//1000000
                self.video_track.bitrate = bit_rate
                print(f'Video: {track.width}x{track.height}@{frame_rate}')
                print(f'Bit rate: {bit_rate}')
                print(f'Bit depth: {track.bit_depth}')
                print(f'Format: {track.format}')
                print(f'Color: {track.color_space} {track.chroma_subsampling}')
                # print(f'Duration (raw value): {track.duration}')
                # print(f'Duration (other values: {track.other_duration}')
                # print(f'VIDEO DATA:\n', pformat(track.to_data()))
            elif track.track_type == 'Audio':
                self.audio_track = track
                print(f'Audio: {track.format} {track.format_settings} '
                      f'{track.bit_depth} bit {track.channel_s} ch')
                self.audio_channels += track.channel_s
                # print(f'AUDIO DATA:\n', pformat(track.to_data()))

    # frame rate, list of frame rates, list of bit rates
    def estimate_bitrate(self,frame_rate, fr_list, br_list):
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
        # print(f'{self.args.yt_cat} {self.video_track.height}@{self.video_track.frame_rate}')
        for mode in self.conf[self.args.yt_cat]:
            height_p = f'{self.video_track.height}p'
            if self.video_track.frame_rate in mode['FrameRates'] and height_p in mode['Bitrates']:
                self.vbitrate = mode['Bitrates'][height_p]
                if isinstance(self.vbitrate, list):
                    self.vbitrate = self.estimate_bitrate(self.video_track.frame_rate,
                                                          mode['FrameRates'],
                                                          self.video_track.frame_rate)
                print(f"YT category: {mode['Category']}")
        if not hasattr(self, 'vbitrate'):
            print('no profile')
            sys.exit(1)
        print(f"YT bitrate: {self.vbitrate} Mbps")
        self.gop = self.video_track.frame_rate // 2
        print(f"YT GOP: {self.gop}")

    def mk_cmd(self):
        cmd = ['ffmpeg']
        cmd.append('-hide_banner')
        cmd.extend(['-i', f'{self.args.infile}'])
        cmd.extend(['-c:v', 'libx264'])
        cmd.extend(['-preset', 'slow'])
        cmd.extend(['-crf', '18'])
        cmd.extend(['-vf', 'scale=out_color_matrix=bt709'])
        cmd.extend(['-color_primaries', ' bt709'])
        cmd.extend(['-color_trc', 'bt709'])
        cmd.extend(['-colorspace', 'bt709'])
        if hasattr(self, 'audio_track'):
            cmd.extend(['-c:a', 'aac'])
            cmd.extend(['-ac', f'{self.audio_channels}'])
            if self.audio_channels == 1:
                abr = 128
            elif self.audio_channels == 2:
                abr = 384
            else:
                abr = 512
            cmd.extend(['-b:a', f'{abr}k'])
            if self.audio_track.sampling_rate <= 48000:
                ar = 48000
            else:
                ar = 96000
            cmd.extend(['-ar' , f'{ar}'])
        else:
            cmd.append('-an')
        cmd.extend(['-profile:v', 'high'])
        cmd.extend(['-level', '4.0'])
        cmd.extend(['-bf', '2'])
        cmd.extend(['-coder', '1'])
        cmd.extend(['-pix_fmt', 'yuv420p'])
        cmd.extend(['-b:v', f'{self.vbitrate}M'])
        cmd.extend(['-threads', '4'])
        cmd.extend(['-cpu-used', '0'])
        cmd.extend(['-r', f'{self.video_track.frame_rate}'])
        cmd.extend(['-g', f'{self.gop}'])
        cmd.extend(['-movflags', '+faststart'])
        cmd.append('-y')
        cmd.append('output.mp4')
        return cmd

def __main__():
    yt = YouTube()
    cmd = yt.mk_cmd()
    run_cmd(cmd)

if __name__ == '__main__':
    __main__()
