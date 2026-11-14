"""Frame sources for the native video stream. Every source yields ``(rgb, captured)`` in memory: an RGB uint8
array and the capture time on this host's monotonic clock. No source writes a frame anywhere.

Existing now:
- ``door_png_source``  the door conversation service's PNG adapter (``door_camera_frame.read_camera``), polled.
                       It drives the doorbell Android emulator over ADB, so only an operator starts it, and only
                       while that service is not using the emulator.
- ``SnapshotFeed``     the MQTT/JPEG snapshot service: its message handler pushes each decrypted JPEG here
                       instead of (or before) anything else; one image per event.
- ``mjpeg_source``     any multipart MJPEG over HTTP: a phone IP-camera app, or the door stream's MJPEG view.
For the glasses and anything else:
- ``ffmpeg_source``    RTSP, HLS, HTTP MJPEG or a local webcam through the installed ffmpeg, decoded to JPEGs
                       on a pipe.
- ``PushSource``       a thread-safe queue a WebRTC receiver (or any callback API) pushes decoded frames into.
                       No WebRTC stack is bundled; adding one is a separate, approved install.
- ``replay_source``    public clips paced on the clock, for tests and gates.
"""
import io
import os
import queue
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

SOI, EOI = b"\xff\xd8", b"\xff\xd9"
MAX_JPEG = 6 * 1024 * 1024


def decode(data):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 4096 * 4096
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def split_jpegs(buffer):
    """Complete JPEGs in ``buffer`` and the unfinished remainder (MJPEG and ffmpeg image2pipe output)."""
    found = []
    while True:
        start = buffer.find(SOI)
        if start < 0:
            return found, b""
        end = buffer.find(EOI, start + 2)
        if end < 0:
            rest = buffer[start:]
            return found, rest if len(rest) <= MAX_JPEG else b""
        found.append(buffer[start:end + 2])
        buffer = buffer[end + 2:]


def replay_source(frames, fps, clock=time.monotonic, sleep=time.sleep):
    """Public frames delivered on the recording clock, as a live camera would."""
    started = clock()
    for i, rgb in enumerate(frames):
        due = started + i / float(fps)
        sleep(max(0., due - clock()))
        yield rgb, clock()


def door_png_source(interval=1., read=None, clock=time.monotonic, sleep=time.sleep, limit=None):
    """Poll the door service's PNG adapter. ``read`` defaults to door_camera_frame.read_camera from the
    directory named by VINTOS_DOOR_ADAPTER_DIR; a missing frame (camera not live) is skipped, never replaced."""
    if read is None:
        folder = os.environ.get("VINTOS_DOOR_ADAPTER_DIR", "")
        if not folder or not os.path.isdir(folder):
            raise RuntimeError("Set VINTOS_DOOR_ADAPTER_DIR to the door service's adapter directory")
        sys.path.insert(0, folder)
        from door_camera_frame import read_camera as read
    n = 0
    while limit is None or n < limit:
        started = clock()
        png = read()
        if png:
            yield decode(png), started
        n += 1
        sleep(max(0., interval - (clock() - started)))


class PushSource:
    """Frames pushed by a callback (WebRTC receiver, MQTT snapshot handler). Old frames are dropped first."""

    def __init__(self, maxsize=4, clock=time.monotonic):
        self.queue, self.clock, self.dropped = queue.Queue(maxsize), clock, 0

    def push(self, rgb, captured=None):
        item = (np.asarray(rgb, dtype=np.uint8), self.clock() if captured is None else captured)
        while True:
            try:
                self.queue.put_nowait(item)
                return
            except queue.Full:
                try:
                    self.queue.get_nowait(); self.dropped += 1
                except queue.Empty:
                    pass

    def frames(self, timeout=30.):
        while True:
            try:
                yield self.queue.get(timeout=timeout)
            except queue.Empty:
                return


class SnapshotFeed(PushSource):
    """The snapshot service's handler calls ``push_jpeg`` with the decrypted bytes it already holds."""

    def push_jpeg(self, data, captured=None):
        if not data.startswith(SOI) or len(data) > MAX_JPEG:
            raise ValueError("Expected one JPEG snapshot")
        self.push(decode(data), captured)


def mjpeg_source(url, clock=time.monotonic, opener=None, chunk=65536):
    """Multipart MJPEG over HTTP; proxies are never used."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        raise ValueError("MJPEG source must be a plain http(s) URL without embedded credentials")
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=10) as response:
        buffer = b""
        while True:
            data = response.read(chunk)
            if not data:
                return
            found, buffer = split_jpegs(buffer + data)
            for jpeg in found:
                yield decode(jpeg), clock()


def ffmpeg_command(url, fps=4., width=640):
    """ffmpeg reading RTSP/HLS/HTTP/webcam input and writing JPEGs to stdout at most ``fps``."""
    if url.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        source = ["-rtsp_transport", "tcp", "-i", url] if url.startswith("rtsp") else ["-i", url]
    elif url.startswith("avfoundation:"):
        source = ["-f", "avfoundation", "-framerate", "30", "-i", url.split(":", 1)[1]]
    elif url.startswith("/dev/video"):
        source = ["-f", "v4l2", "-i", url]
    else:
        raise ValueError("Unsupported stream URL")
    return (["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"] + source +
            ["-an", "-vf", "fps=%g,scale=%d:-2" % (fps, width), "-f", "image2pipe", "-c:v", "mjpeg",
             "-q:v", "4", "pipe:1"])


def ffmpeg_source(url, fps=4., width=640, clock=time.monotonic, popen=subprocess.Popen):
    process = popen(ffmpeg_command(url, fps, width), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0)
    try:
        buffer = b""
        while True:
            data = process.stdout.read(65536)
            if not data:
                return
            found, buffer = split_jpegs(buffer + data)
            for jpeg in found:
                yield decode(jpeg), clock()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()


def run(stream, frames, ask_every=None, question=None, on_answer=None):
    """Feed a source into a native_video.Stream through its adaptive sampler. Questions are answered on their own
    thread, so frames keep flowing while an answer is decoded (one question at a time)."""
    last, pending = None, None

    def deliver(answer):
        if on_answer:
            on_answer(answer.result())

    for rgb, captured in frames:
        stream.offer(rgb, captured)
        if pending is not None and pending.done():
            deliver(pending); pending = None
        if ask_every and question and pending is None and (last is None or captured - last >= ask_every):
            last = captured
            pending = stream.ask(question, wait=False)
    if pending is not None:
        pending.wait(180)
        deliver(pending)
