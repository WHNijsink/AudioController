""" Read audio stream, and play it, using installed vlc player (libvlc) """
import sys
import os
import time
from typing import List
import ctypes
from subprocess import Popen, PIPE, TimeoutExpired
from multiprocessing import Process, Queue
import logging
import re
import shlex

from audio_controller import envvars
from audio_controller import soundcard

main_logger = logging.getLogger("main")

_BITRATE_RE = re.compile(r"^[0-9]+[KkMm]?$")


def sanitize_bitrate(raw: str) -> str:
    """Return raw if it is a plain ffmpeg bitrate (e.g. '64K'), else the safe default '64K' (S1)."""
    raw = (raw or "").strip()
    return raw if _BITRATE_RE.match(raw) else "64K"


def ffmpeg_input_for_url(url: str) -> str:
    """'-i <shell-quoted-url>' — prevents shell injection via the source url (S1)."""
    return "-i {}".format(shlex.quote(url))


def ffmpeg_output_for_url(raw_url: str) -> str:
    """Parse 'url;bitrate' and return injection-safe ffmpeg output args (S1)."""
    parts = raw_url.split(";")
    url = parts[0]
    bitrate = sanitize_bitrate(parts[1]) if len(parts) > 1 and parts[1] else "64K"
    content_type = "-content_type audio/mpeg -f mp3"
    bitrate_ = "-b:a {b} -minrate {b} -maxrate {b} -bufsize {b}".format(b=bitrate)
    return "{} {} {}".format(content_type, bitrate_, shlex.quote(url))


def print_info(msg):
    print(msg)
    main_logger.info(msg)


#
# Using ffmpeg to play url stream
#


def execute_ffmpeg(command: str, queue: Queue, testing=False):
    """Execute ffmpeg command, until queue gets message. Retry when command exits."""
    # 'exec' is needed to be able to easily stop/terminate the process
    cmd = f"exec {command} >/dev/null 2>&1"
    sleeptime = 3
    if testing:  # for testing, give full output:
        cmd = f"exec {command}"
        sleeptime = 10
    proc = None

    def create_process():
        nonlocal proc
        print_info(f"execute_ffmpeg create_process: {command}")
        proc = Popen(args=cmd, stdin=None, stdout=None, stderr=None, cwd=None, bufsize=0, shell=True)

    create_process()

    def stop():
        print_info(f"execute_ffmpeg stop: {command}")
        proc.terminate()
        try:
            proc.wait(timeout=5)  # C4: don't block forever if ffmpeg ignores SIGTERM
        except TimeoutExpired:
            proc.kill()
            proc.wait()

    while True:
        # check if process must stop
        must_stop = None
        try:
            must_stop = queue.get(block=True, timeout=1)
        except:
            pass
        if must_stop is not None:
            stop()
            break
        else:
            # check if process is stopped (by accident)
            is_running = proc.poll() is None
            if not is_running:
                print_info(f"execute_ffmpeg stopped unexpectedly: {command}")
                create_process()
                time.sleep(sleeptime)  # do not try to create process too many times


class FfmpegProcess:
    def __init__(self, cmd, testing=False):
        self.queue = Queue()
        self.process = Process(
            target=execute_ffmpeg,
            args=(
                cmd,
                self.queue,
                testing,
            ),
            daemon=True,
        )
        self.process.start()
        self.stopped = False

    def stop(self):
        if not self.stopped:
            self.stopped = True
            self.queue.put("stop")
            self.process.join()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class ReadFromUrl:
    """
    Read from external url and send to soundcard
    """

    def __init__(self) -> None:
        self.process_play = ()  # tuple (url, FfmpegProcess)

    def update_url(self, url):
        # stop
        if self.process_play and self.process_play[0] != url:
            self.process_play[1].stop()
            self.process_play = ()

        # start
        if not self.process_play and url is not None:
            self.process_play = (url, self._run(url))

    def _run(self, url):
        """Create and return process to read audio from url and send to default soundcard"""
        format_ = "-f alsa"
        output = soundcard.get_real_play_device()
        return FfmpegProcess("ffmpeg {} {} {}".format(ffmpeg_input_for_url(url), format_, output), testing=False)


class SendToUrlsSimple:
    """
    Read from soundcard and send to external urls, using one FfmpegProcess
    """

    def __init__(self) -> None:
        self.process_send = ()  # tuple (urls, FfmpegProcess)

    def update_urls(self, urls):
        # stop
        urls = sorted(urls)
        if self.process_send and self.process_send[0] != urls:
            self.process_send[1].stop()
            self.process_send = ()

        # start
        if not self.process_send and len(urls) > 0:
            self.process_send = (urls, self.get_send_process(urls))

    def get_send_process(self, urls: "list[str]"):
        format_ = "-f alsa"
        input_device = soundcard.get_real_record_device()
        input = f"{format_} -i {input_device}"
        outputs = " ".join(ffmpeg_output_for_url(url) for url in urls)
        cmd = f"ffmpeg {input} {outputs}"
        return FfmpegProcess(cmd)


class SendToUrls:
    """
    Read with one process from soundcard,
    duplicate this to multiple virtual soundcards,
    and send to external urls with separate Ffmpeg processes.
    """

    def __init__(self) -> None:
        self.process_read: FfmpegProcess = None
        self.process_send = {}  # {url: (input_device, FfmpegProcess)}
        # WARNING if user applies same url to multiple destinations,
        # only one process will start, user sees 2 activated,
        # and process is stopped if user deactivates only 1
        self.urls = []

    def update_urls(self, urls):
        # stop
        self.urls = sorted(urls)
        self.start_stop_read()
        self.start_stop_send()

    def start_stop_read(self):
        if self.process_read is None and self.urls:
            self.process_read = self.create_process_read()
        elif self.process_read is not None and not self.urls:
            self.process_read.stop()
            self.process_read = None

    def create_process_read(self):
        """
        Read from real soundcard and play on multiple virtual soundcard subdevices
        """
        input_device = soundcard.get_real_record_device()
        format_ = "-f alsa"
        input = f"{format_} -i {input_device}"
        output_devices = soundcard.get_virtual_play_devices()
        outputs = [f"-f alsa {output}" for output in output_devices]
        outputs = " ".join(outputs)
        cmd = f"ffmpeg {input} {outputs}"
        return FfmpegProcess(cmd)

    def start_stop_send(self):
        """
        Read from virtual soundcards and send to external url
        """
        input_devices = soundcard.get_virtual_record_devices()

        # stop processes for urls which are not in self.urls
        for url in list(self.process_send.keys()):
            if url not in self.urls:
                self.process_send[url][1].stop()
                del self.process_send[url]

        available_devices = []
        for device in input_devices:
            for input_device, process in self.process_send.values():
                if device == input_device:
                    break  # not available
            else:
                available_devices.append(device)

        # start processes for urls which are not started yet
        for url in self.urls:
            if url not in self.process_send:
                if available_devices:
                    input_device = available_devices.pop(0)
                    self.process_send[url] = (input_device, self.get_send_process(input_device, url))
                else:
                    pass  # TODO log warning: too many url destinations specified, max = ...

    def get_send_process(self, input_device, url):
        format_ = "-f alsa"
        input = f"{format_} -i {input_device}"
        output = ffmpeg_output_for_url(url)
        cmd = f"ffmpeg {input} {output}"
        return FfmpegProcess(cmd)


def get_url_reader() -> ReadFromUrl:
    return ReadFromUrl()


def get_url_sender() -> SendToUrls:
    if "virtual_card" in soundcard.get_soundcard_info():
        return SendToUrls()
    else:
        return SendToUrlsSimple()


class TestUrl:
    ro1 = "http://ro1.reformatorischeomroep.nl:8003/live"
    ro1_s = "https://radio1.reformatorischeomroep.nl/live.m3u"  # werkt niet
    ro2 = "http://ro2.reformatorischeomroep.nl:8020/live"
    ro3 = "http://ro3.reformatorischeomroep.nl:8072/live"
    noord = "http://meeluisteren.gergemrijssen.nl:8000/noord"
    zuid = "http://meeluisteren.gergemrijssen.nl:8000/zuid"
    west = "http://meeluisteren.gergemrijssen.nl:8000/west"


def test_ffmpeg():
    """stream to icecast"""
    from decouple import config

    input_url = TestUrl.ro1
    password = config("icecast_password")
    icecast_url = f"icecast://source:{password}@173.249.6.236:8000/babyfoon"
    content_type = "-content_type audio/mpeg -f mp3"
    bitrate = "-b:a 64K -minrate 64K -maxrate 64K -bufsize 64K"
    # play on standard out:
    # cmd = f'ffmpeg -i {input_url} -f alsa default'
    # send input url to icecast:
    # cmd = f'ffmpeg -i {input_url} {content_type} {bitrate} "{icecast_url}"'
    # send recording to icecast:
    cmd = f'ffmpeg -f alsa -i hw:0 {content_type} {bitrate} "{icecast_url}"'
    print(cmd)
    # with FfmpegProcess(cmd):
    #    while True:
    #        time.sleep(30)


def test():
    return
    test_ffmpeg()
    # test_sounddevice()
    # test_ffmpeg()
    sys.exit(0)


if __name__ == "__main__":
    test_ffmpeg()


#
# Deprecated: Using VLC to play url stream
#


# import urllib3
# import vlc
# from vlc import CallbackDecorators

# MediaReadCb = CallbackDecorators.MediaReadCb


# def from_url(url):
#     while True:
#         try:
#             http = urllib3.PoolManager()
#             r = http.request('GET', url, preload_content=False)
#             for chunk in r.stream(32 * 100):
#                 yield chunk
#             r.release_conn()
#         except:
#             print(f"Exception while reading from url {url}:")
#             print(traceback.format_exc())
#             time.sleep(5)


# def play_from_url(url: str, queue: Queue):
#     print(f"playing {url}")
#     generator = from_url(url)

#     @MediaReadCb
#     def read_cb(opaque, buffer, length):
#         new_data = next(generator)
#         c = len(new_data)
#         buffer_array = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char * length))
#         ctypes.memmove(buffer_array, new_data, c)
#         return c

#     instance = vlc.Instance()
#     player = instance.media_player_new()
#     media = instance.media_new_callbacks(None, read_cb, seek_cb=None, close_cb=None, opaque=None)
#     player.set_media(media)
#     player.play()

#     # wait until other process puts something in queue
#     queue.get(block=True)


# def test_sounddevice():
#     import sounddevice as sd

#     def callback(indata, outdata, frames, time, status):
#         if status:
#             print(status)
#         outdata[:] = indata
#     with sd.RawStream(channels=2, dtype='int24', callback=callback):
#         while True:
#             sd.sleep(1000)
#     print('done')
