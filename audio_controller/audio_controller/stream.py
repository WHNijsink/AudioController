""" Read audio stream, and play it, using installed vlc player (libvlc) """
import sys
import os
import time
from typing import List
import ctypes
from subprocess import Popen, PIPE, TimeoutExpired, DEVNULL
from multiprocessing import Process, Queue
import logging
import re

from audio_controller import envvars
from audio_controller import soundcard

main_logger = logging.getLogger("main")

_BITRATE_RE = re.compile(r"^[0-9]+[KkMm]?$")

# Matches the "user:pass@" userinfo in a scheme://user:pass@host url (S-M1).
_URL_USERINFO_RE = re.compile(r"(://)[^/@\s]+@")


def redact_credentials(command):
    """Return a copy of an ffmpeg argv list with any 'user:pass@' userinfo in a
    url masked, so a logged command never leaks icecast/source credentials (S-M1).
    The host and path are kept, which is what you actually want when debugging."""
    return [_URL_USERINFO_RE.sub(r"\1***@", str(arg)) for arg in command]


def sanitize_bitrate(raw: str) -> str:
    """Return raw if it is a plain ffmpeg bitrate (e.g. '64K'), else the safe default '64K' (S1)."""
    raw = (raw or "").strip()
    return raw if _BITRATE_RE.match(raw) else "64K"


def ffmpeg_input_for_url(url: str) -> "list[str]":
    """Return ffmpeg input argv ['-i', url]. The url is a single argv element, so
    there is no shell and no token splitting/injection via the source url (S1/S6)."""
    return ["-i", url]


def ffmpeg_output_for_url(raw_url: str) -> "list[str]":
    """Parse 'url;bitrate' and return injection-safe ffmpeg output argv (S1/S6).
    Every value is a separate argv element; the url is the single trailing token."""
    parts = raw_url.split(";")
    url = parts[0]
    bitrate = sanitize_bitrate(parts[1]) if len(parts) > 1 and parts[1] else "64K"
    return [
        "-content_type", "audio/mpeg", "-f", "mp3",
        "-b:a", bitrate, "-minrate", bitrate, "-maxrate", bitrate, "-bufsize", bitrate,
        url,
    ]


def print_info(msg):
    print(msg)
    main_logger.info(msg)


#
# Using ffmpeg to play url stream
#


def execute_ffmpeg(command, queue: Queue, testing=False):
    """Execute the ffmpeg argv `command` (a list[str]), until the queue gets a
    message. Retry when the command exits.

    The command is an argv list run WITHOUT a shell (no shell=True), so a source
    or destination url can never inject shell syntax (S1/S6). Popen is ffmpeg
    itself, so proc.terminate() stops it directly (no exec-through-shell needed)."""
    sleeptime = 10 if testing else 3
    # discard ffmpeg output in normal operation; show it when testing
    out = None if testing else DEVNULL
    proc = None

    def create_process():
        nonlocal proc
        print_info(f"execute_ffmpeg create_process: {redact_credentials(command)}")
        proc = Popen(command, stdin=None, stdout=out, stderr=out, cwd=None, bufsize=0)

    create_process()

    def stop():
        print_info(f"execute_ffmpeg stop: {redact_credentials(command)}")
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
                print_info(f"execute_ffmpeg stopped unexpectedly: {redact_credentials(command)}")
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
        output = soundcard.get_real_play_device()
        cmd = ["ffmpeg"] + ffmpeg_input_for_url(url) + ["-f", "alsa", output]
        return FfmpegProcess(cmd, testing=False)


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
        input_device = soundcard.get_real_record_device()
        cmd = ["ffmpeg", "-f", "alsa", "-i", input_device]
        for url in urls:
            cmd += ffmpeg_output_for_url(url)
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
        cmd = ["ffmpeg", "-f", "alsa", "-i", input_device]
        for output in soundcard.get_virtual_play_devices():
            cmd += ["-f", "alsa", output]
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
        cmd = ["ffmpeg", "-f", "alsa", "-i", input_device] + ffmpeg_output_for_url(url)
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
