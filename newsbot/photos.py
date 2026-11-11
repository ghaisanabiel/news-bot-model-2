import io
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageOps

COMMONS = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'LimitcryptoNewsBot/1.0 (private editorial photo lookup)'}
MAX_BYTES = 8 * 1024 * 1024
TOPICS = (
    (r'\btrump\b', 'Donald Trump official portrait'),
    (r'\b(ihsg|bei|idx|bursa efek indonesia)\b', 'intitle:SCBD Jakarta'),
    (r'\b(bank indonesia|bi rate)\b', 'Bank Indonesia headquarters Jakarta'),
    (r'\b(federal reserve|the fed|fomc)\b', 'Federal Reserve Eccles building'),
    (r'\b(bitcoin|btc)\b', 'Bitcoin physical coin photo'),
    (r'\b(ethereum|eth)\b', 'Ethereum physical coin photo'),
    (r'\b(minyak|brent|wti)\b', 'oil refinery industrial photo'),
    (r'\b(hormuz)\b', 'Strait of Hormuz satellite photograph'),
    (r'\b(emas|gold)\b', 'gold bars photo'),
    (r'\b(rupiah|idr)\b', 'Indonesian rupiah banknotes photo'),
    (r'\b(nikel|nickel)\b', 'nickel mine Indonesia'),
    (r'\b(batu bara|batubara|coal)\b', 'coal mine Indonesia'),
)


@dataclass(frozen=True)
class CoverPhoto:
    image: Image.Image
    original: bytes
    extension: str
    credit: dict


def metadata_text(metadata, field):
    value = metadata.get(field, {}).get('value', '')
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', value)).split())


def eligible_credit(info, page):
    meta = info.get('extmetadata', {})
    license_name = metadata_text(meta, 'LicenseShortName')
    license_url = metadata_text(meta, 'LicenseUrl')
    artist = metadata_text(meta, 'Artist')
    source = info.get('descriptionurl', '')
    if metadata_text(meta, 'Restrictions') or urlsplit(source).hostname != 'commons.wikimedia.org':
        return None
    if license_name == 'Public domain' and metadata_text(meta, 'License') in ('pd', 'public-domain'):
        pass
    elif license_name == 'CC0' and metadata_text(meta, 'License') in ('cc-zero', 'cc0'):
        license_url = 'https://creativecommons.org/publicdomain/zero/1.0/'
    elif re.fullmatch(r'https?://creativecommons\.org/(?:licenses/by/(?:2\.0|2\.5|3\.0|4\.0)|publicdomain/zero/1\.0)/?', license_url):
        if '/licenses/by/' in license_url and not artist:
            return None
    else:
        return None
    return {'id': page['pageid'], 'title': page['title'].removeprefix('File:'),
            'artist': artist or 'Lihat halaman sumber', 'license': license_name or license_url,
            'license_url': license_url, 'source': source, 'original_url': info['url']}


def cover_photo(story, excluded=()):
    query = next((query for pattern, query in TOPICS if re.search(pattern, story.title, re.I)), None)
    if not query:
        return None
    photo = find_photo(query, excluded)
    if not photo and query == 'intitle:SCBD Jakarta':
        photo = find_photo('intitle:Jakarta skyline', excluded)
    return photo


def find_photo(query, excluded):
    try:
        result = requests.get(COMMONS, headers=HEADERS, timeout=10, params={
            'action': 'query', 'generator': 'search', 'gsrsearch': query,
            'gsrnamespace': 6, 'gsrlimit': 24, 'prop': 'imageinfo',
            'iiprop': 'url|size|mime|extmetadata', 'iiextmetadatalanguage': 'en',
            'format': 'json', 'formatversion': 2,
        })
        result.raise_for_status()
        pages = sorted(result.json().get('query', {}).get('pages', []), key=lambda page: page.get('index', 999))
    except (requests.RequestException, ValueError):
        return None
    attempts = 0
    for page in pages:
        if page.get('pageid') in excluded or not page.get('imageinfo'):
            continue
        if 'Jakarta' in query and re.search(r'\b(protest|demonstration)\b', page['title'], re.I):
            continue
        info = page['imageinfo'][0]
        width, height = info.get('width', 0), info.get('height', 0)
        if (info.get('mime') not in ('image/jpeg', 'image/png') or width < 720 or height < 500
                or width * height > 30_000_000 or not 0 < info.get('size', 0) <= MAX_BYTES):
            continue
        url = urlsplit(info.get('url', ''))
        if url.scheme != 'https' or url.netloc != 'upload.wikimedia.org':
            continue
        credit = eligible_credit(info, page)
        if not credit:
            continue
        attempts += 1
        if attempts > 3:
            break
        try:
            with requests.get(info['url'], headers=HEADERS, timeout=10, stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    continue
                buffer = bytearray()
                for chunk in response.iter_content(65536):
                    buffer.extend(chunk)
                    if len(buffer) > MAX_BYTES:
                        raise ValueError('Foto melebihi batas ukuran')
            original = bytes(buffer)
            with Image.open(io.BytesIO(original), formats=('JPEG', 'PNG')) as source:
                if source.width * source.height > 30_000_000:
                    continue
                extension = '.jpg' if source.format == 'JPEG' else '.png'
                return CoverPhoto(ImageOps.exif_transpose(source).convert('RGB'), original, extension, credit)
        except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError):
            continue
    return None


def credit_line(credit):
    return (f"Foto arsip/ilustrasi: {credit['title']} — {credit['artist']} ({credit['license']}).\n"
            f"Sumber foto: {credit['source']}\n"
            + (f"Lisensi: {credit['license_url']}\n" if credit['license_url'] else '')
            + 'Foto dipotong dan diberi gradasi untuk cover.')
