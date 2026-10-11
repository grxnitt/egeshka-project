"""Proof screenshots: only JPEG, PNG or WebP, and never stored as uploaded.

Every file is decoded in a separate worker process with memory and CPU limits, then drawn again into a fresh
WebP without metadata (EXIF, GPS, comments, embedded profiles). What reaches the disk and the moderator is a new
picture made by us, so a crafted file (polyglot, script inside, exploit for a viewer) cannot survive: anything
that is not a real image of an allowed type fails to decode and is rejected.
"""
import asyncio
import io
import os
import secrets
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context

MAX_FILES = 3
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000          # 40 MP: larger than any real screenshot or phone photo
MAX_SIDE = 2000                  # what the moderator needs to read a contract or a platform page
MAX_OUTPUT_BYTES = 3 * 1024 * 1024
WORKER_MEMORY = 1024 * 1024 * 1024
WORKER_CPU_SECONDS = 20

SIGNATURES = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
)


class ImageError(ValueError):
    pass


def sniff(data: bytes):
    """Format by magic bytes (never by the file name or the browser's content type)."""
    for magic, kind in SIGNATURES:
        if data.startswith(magic):
            return kind
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _limit_worker():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY, WORKER_MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (WORKER_CPU_SECONDS, WORKER_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ImportError, ValueError, OSError):  # macOS ignores RLIMIT_AS; production is Linux
        pass


def _reencode(data: bytes, kind: str):
    """Runs in the worker. Returns (webp bytes, width, height) or raises."""
    import warnings
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(data), formats=[kind]) as source:
        if source.format != kind:
            raise ValueError("format mismatch")
        width, height = source.size
        if width < 50 or height < 50 or width * height > MAX_PIXELS:
            raise ValueError("bad size")
        source.seek(0)                       # animated files: the first frame only
        source.load()
        picture = ImageOps.exif_transpose(source)
        if picture.mode in ("RGBA", "LA", "P"):
            picture = picture.convert("RGBA")
            canvas = Image.new("RGB", picture.size, (255, 255, 255))
            canvas.paste(picture, mask=picture.getchannel("A"))
            picture = canvas
        else:
            picture = picture.convert("RGB")
        picture.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        clean = Image.new("RGB", picture.size)
        clean.paste(picture)                 # pixels only: no info dict, no ICC profile, no EXIF
        out = io.BytesIO()
        clean.save(out, format="WEBP", quality=82, method=4)
        return out.getvalue(), clean.width, clean.height


class Sanitizer:
    def __init__(self, workers: int = 1):
        self.workers = workers
        self._pool = None

    def _executor(self):
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.workers, mp_context=get_context("spawn"),
                                             initializer=_limit_worker)
        return self._pool

    async def clean(self, data: bytes):
        if not data:
            raise ImageError("Пустой файл.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ImageError("Файл больше 10 МБ. Сделай скриншот поменьше.")
        kind = sniff(data)
        if kind is None:
            raise ImageError("Подходят только картинки JPG, PNG или WebP.")
        loop = asyncio.get_running_loop()
        try:
            webp, width, height = await asyncio.wait_for(
                loop.run_in_executor(self._executor(), _reencode, data, kind), timeout=WORKER_CPU_SECONDS + 10)
        except BrokenProcessPool:
            self._pool = None                # the worker died (memory/CPU limit): start a fresh one next time
            raise ImageError("Не получилось обработать картинку. Попробуй другой скриншот.") from None
        except Exception:  # noqa: BLE001 - any decode failure means "not a usable image"
            raise ImageError("Не получилось открыть картинку. Попробуй другой скриншот (JPG, PNG или WebP).") from None
        if len(webp) > MAX_OUTPUT_BYTES:
            raise ImageError("Картинка слишком сложная. Попробуй другой скриншот.")
        return webp, width, height

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(cancel_futures=True)
            self._pool = None


def new_file_name() -> str:
    return f"{secrets.token_hex(20)}.webp"


def safe_path(directory: str, file_name: str) -> str:
    """Only names we generated (40 hex + .webp) map to a path; anything else is refused."""
    stem, dot, ext = file_name.partition(".")
    if ext != "webp" or len(stem) != 40 or any(ch not in "0123456789abcdef" for ch in stem):
        raise ImageError("bad name")
    return os.path.join(directory, file_name)


def write_file(directory: str, file_name: str, data: bytes) -> None:
    path = safe_path(directory, file_name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o640)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def remove_file(directory: str, file_name: str) -> None:
    try:
        os.remove(safe_path(directory, file_name))
    except (FileNotFoundError, ImageError):
        pass
