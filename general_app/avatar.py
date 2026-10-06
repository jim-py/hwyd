"""Decode and normalize avatar uploads before they enter media storage."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import re
import warnings

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image, ImageOps

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
MAX_ANIMATION_SECONDS = 10
MAX_GIF_FRAMES = 300
MAX_GIF_DECODED_PIXELS = 50_000_000


def _webm_header(data):
    """Require the WebM DocType in the bounded EBML header, not a filename."""
    def vint(offset, keep_marker=False):
        if offset >= len(data) or not data[offset]:
            raise ValueError
        length = 9 - data[offset].bit_length()
        end = offset + length
        if end > len(data):
            raise ValueError
        value = int.from_bytes(data[offset:end], 'big')
        if not keep_marker:
            value &= (1 << (7 * length)) - 1
        return value, end

    try:
        identifier, offset = vint(0, True)
        size, offset = vint(offset)
        end = offset + size
        if identifier != 0x1A45DFA3 or end > len(data):
            return False
        while offset < end:
            identifier, offset = vint(offset, True)
            size, offset = vint(offset)
            if offset + size > end:
                return False
            if identifier == 0x4282:
                return data[offset:offset + size] == b'webm'
            offset += size
    except ValueError:
        pass
    return False


def _normalize_webm(upload, max_size=None, preserve_alpha=False):
    if not _webm_header(upload.read(4096)):
        raise forms.ValidationError('Загрузите корректное видео в формате WEBM.')
    upload.seek(0)
    # Preserve avatar sizing; chat caps resolution without upscaling small clips.
    scale = '256:256' if max_size is None else f'min({max_size}\\,iw):min({max_size}\\,ih)'
    try:
        executable = get_ffmpeg_exe()
        with TemporaryDirectory(prefix='habitus-avatar-') as directory:
            source = Path(directory) / 'source.webm'
            target = Path(directory) / 'avatar.webm'
            with source.open('wb') as destination:
                for chunk in upload.chunks():
                    destination.write(chunk)
            decoder = []
            if preserve_alpha:
                # Native VP8/VP9 decoders discard WebM's separate alpha plane.
                # Inspect the first video stream without decoding, then select
                # the matching libvpx decoder; opaque clips remain opaque.
                probe = subprocess.run([
                    executable, '-nostdin', '-hide_banner', '-max_alloc', '67108864',
                    '-protocol_whitelist', 'file', '-f', 'matroska', '-i', str(source),
                    '-map', '0:v:0', '-c:v', 'copy', '-frames:v', '1', '-f', 'null', '-',
                ], capture_output=True, timeout=5,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                stream = re.search(r'^\s*Stream #0:\d+(?:\[[^\]]*\])?(?:\([^)]*\))?: Video: (\w+)',
                                   probe.stderr.decode('utf8', errors='replace'), re.MULTILINE)
                if probe.returncode or stream is None:
                    raise forms.ValidationError('Не удалось прочитать WEBM. Выберите другое видео.')
                if stream.group(1) in ('vp8', 'vp9'):
                    decoder = ['-c:v', 'libvpx' if stream.group(1) == 'vp8' else 'libvpx-vp9']
            # A separate, time-limited decoder cannot access network protocols.
            result = subprocess.run([
                executable, '-nostdin', '-hide_banner', '-loglevel', 'warning',
                '-xerror', '-max_alloc', '67108864', '-max_pixels', str(MAX_AVATAR_PIXELS), '-threads', '1',
                '-protocol_whitelist', 'file', '-f', 'matroska', *decoder, '-i', str(source),
                '-map', '0:v:0', '-an', '-sn', '-dn', '-map_metadata', '-1',
                '-map_chapters', '-1', '-vf',
                f'setpts=PTS-STARTPTS,scale={scale}:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30',
                '-t', str(MAX_ANIMATION_SECONDS + 0.1), '-c:v', 'libvpx-vp9',
                '-threads', '1', '-b:v', '0', '-crf', '32', '-deadline', 'realtime',
                '-cpu-used', '8', '-pix_fmt', 'yuva420p' if preserve_alpha else 'yuv420p', '-fs', str(MAX_AVATAR_BYTES),
                '-progress', 'pipe:1', '-nostats', '-y', str(target),
            ], capture_output=True, timeout=20,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode or result.stderr.strip() or not target.exists():
                raise forms.ValidationError('Не удалось прочитать WEBM. Выберите другое видео.')
            progress = result.stdout.decode('ascii', errors='replace').splitlines()
            frames = [int(line.split('=', 1)[1]) for line in progress if line.startswith('frame=')]
            if not frames or max(frames) == 0:
                raise forms.ValidationError('В WEBM нет видеокадров.')
            if max(frames) > MAX_ANIMATION_SECONDS * 30:
                raise forms.ValidationError('Длительность анимации не должна превышать 10 секунд.')
            output = target.read_bytes()
    except subprocess.TimeoutExpired:
        raise forms.ValidationError('Обработка WEBM заняла слишком много времени. Выберите более короткое видео.')
    except (OSError, RuntimeError, ValueError):
        raise forms.ValidationError('Не удалось обработать WEBM. Попробуйте другое видео или GIF.')
    if len(output) >= MAX_AVATAR_BYTES:
        raise forms.ValidationError('Размер аватара после обработки превышает 5 МБ.')
    return SimpleUploadedFile('avatar.webm', output, content_type='video/webm')


def _normalize_image(upload):
    formats = {'JPEG': ('.jpg', 'image/jpeg'), 'PNG': ('.png', 'image/png'),
               'WEBP': ('.webp', 'image/webp'), 'GIF': ('.gif', 'image/gif')}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                image_format = image.format
                if image_format not in formats:
                    raise forms.ValidationError('Выберите JPEG, PNG, WEBP, GIF или WEBM.')
                if image.width * image.height > MAX_AVATAR_PIXELS:
                    raise forms.ValidationError('Разрешение фотографии не должно превышать 20 млн пикселей.')
                output = BytesIO()
                if image_format == 'GIF':
                    frames, durations = [], []
                    decoded_pixels = 0
                    # seek() composites GIF disposal/transparency before copying.
                    for index in range(MAX_GIF_FRAMES + 1):
                        try:
                            image.seek(index)
                        except EOFError:
                            break
                        decoded_pixels += image.width * image.height
                        duration = image.info.get('duration', 100) or 100
                        if index == MAX_GIF_FRAMES or decoded_pixels > MAX_GIF_DECODED_PIXELS:
                            raise forms.ValidationError('GIF слишком сложный. Выберите анимацию меньшего размера.')
                        durations.append(duration)
                        if sum(durations) > MAX_ANIMATION_SECONDS * 1000:
                            raise forms.ValidationError('Длительность анимации не должна превышать 10 секунд.')
                        frame = image.convert('RGBA')
                        frame.thumbnail((256, 256))
                        frame.info.clear()
                        frames.append(frame)
                    frames[0].save(output, format='GIF', save_all=True,
                                   append_images=frames[1:], duration=durations, loop=0, disposal=2)
                else:
                    image.load()
                    oriented = ImageOps.exif_transpose(image)
                    mode = 'RGBA' if image_format != 'JPEG' and ('A' in oriented.getbands() or 'transparency' in oriented.info) else 'RGB'
                    normalized = Image.new(mode, oriented.size)
                    normalized.paste(oriented.convert(mode))
                    normalized.save(output, format=image_format)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise forms.ValidationError('Не удалось прочитать изображение. Выберите другую фотографию.')
    if output.tell() > MAX_AVATAR_BYTES:
        raise forms.ValidationError('Размер фотографии после обработки превышает 5 МБ. Выберите файл меньшего размера.')
    extension, content_type = formats[image_format]
    return SimpleUploadedFile(f'avatar{extension}', output.getvalue(), content_type=content_type)


def normalize_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise forms.ValidationError('Размер фотографии не должен превышать 5 МБ.')
    prefix = upload.read(4)
    upload.seek(0)
    if prefix == b'\x1a\x45\xdf\xa3' or Path(upload.name).suffix.lower() == '.webm':
        return _normalize_webm(upload)
    return _normalize_image(upload)
