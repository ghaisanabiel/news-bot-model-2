import hashlib
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .config import now


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(StrictModel):
    url: str
    title: str = Field(max_length=180)
    publisher: str = Field(max_length=80)
    origin: str = Field(max_length=100, description='Original reporting institution, not syndicating outlet')
    primary: bool
    published_at: str
    read_full: bool = Field(description='True when fetched visible article text is sufficient for the specific cited claims, even if unrelated parts of the article are unavailable. False for search snippets, navigation, or text insufficient for the claims.')


class Fact(StrictModel):
    id: str
    text: str = Field(max_length=360)
    source_urls: list[str] = Field(min_length=1, max_length=4)
    evidence: str = Field(max_length=600, description='Brief faithful supporting excerpt or paraphrase')


class Story(StrictModel):
    event_key: str = Field(description='Stable lowercase entity-event-date slug, same for duplicate reporting')
    title: str = Field(max_length=150)
    category: str = Field(max_length=50)
    summary: str = Field(max_length=500)
    why: str = Field(max_length=350)
    angle: str = Field(max_length=200)
    event_at: str
    published_at: str
    score: int = Field(ge=0, le=100)
    verified: bool
    uncertainty: str = Field(max_length=350)
    sources: list[Source] = Field(min_length=1, max_length=5)
    facts: list[Fact] = Field(min_length=1, max_length=8)


class Scan(StrictModel):
    coverage: str = Field(max_length=600)
    stories: list[Story] = Field(max_length=8)


class Recheck(StrictModel):
    same_event: bool
    material_change: bool
    explanation: str = Field(max_length=500)
    story: Story


class Slide(StrictModel):
    title: str = Field(max_length=85)
    body: str = Field(max_length=360)
    fact_ids: list[str] = Field(min_length=1)


class Draft(StrictModel):
    slides: list[Slide] = Field(min_length=1, max_length=6)
    caption: str = Field(max_length=1700)
    alt_text: list[str] = Field(min_length=1, max_length=6)


class Review(StrictModel):
    passed: bool
    issues: list[str]


def canonical(url):
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('URL sumber tidak valid')
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k not in ('gclid', 'fbclid')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(query), ''))


def parse_date(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Tanggal harus menyertakan zona waktu')
    return result


def validate_story(story, consulted, clock=None, fresh=True):
    clock = clock or now()
    if not story.verified:
        raise ValueError('Bukti belum memadai')
    published = parse_date(story.published_at)
    event = parse_date(story.event_at)
    if published > clock + timedelta(minutes=10) or event > clock + timedelta(minutes=10):
        raise ValueError('Peristiwa belum terjadi; gunakan tanggal pengumuman, bukan jadwal mendatang')
    if fresh and (clock - published > timedelta(hours=48) or clock - event > timedelta(hours=48)):
        raise ValueError('Peristiwa atau publikasi terlalu lama untuk kandidat baru')
    allowed = {canonical(u) for u in consulted}
    urls = {canonical(s.url) for s in story.sources}
    if not urls.issubset(allowed):
        raise ValueError('Tautan yang dipilih tidak cocok dengan halaman sumber yang berhasil diambil.')
    if not all(s.read_full for s in story.sources):
        raise ValueError('Isi salah satu halaman sumber belum cukup untuk memeriksa klaimnya.')
    if not any(s.primary for s in story.sources) and len({s.origin.casefold() for s in story.sources}) < 2:
        raise ValueError('Butuh sumber primer atau dua asal laporan independen')
    ids = [f.id for f in story.facts]
    if len(ids) != len(set(ids)):
        raise ValueError('ID fakta berulang')
    for fact in story.facts:
        if not fact.evidence.strip() or not {canonical(u) for u in fact.source_urls}.issubset(urls):
            raise ValueError('Fakta tidak memiliki bukti sumber yang sesuai')
    for source in story.sources:
        if parse_date(source.published_at) > clock + timedelta(minutes=10):
            raise ValueError('Tanggal sumber tidak valid')


def fingerprint(story):
    return hashlib.sha256(story.event_key.lower().strip().encode()).hexdigest()


def duplicate(a, b):
    if fingerprint(a) == fingerprint(b):
        return True
    if {canonical(s.url) for s in a.sources} & {canonical(s.url) for s in b.sources}:
        return True
    normalize = lambda x: ' '.join(re.findall(r'\w+', x.lower()))
    return SequenceMatcher(None, normalize(a.title), normalize(b.title)).ratio() > .82


def validate_draft(draft, story):
    ids = {f.id for f in story.facts}
    if len(draft.alt_text) != len(draft.slides):
        raise ValueError('Teks alternatif tidak cocok dengan jumlah slide')
    for slide in draft.slides:
        if not set(slide.fact_ids).issubset(ids):
            raise ValueError('Slide merujuk fakta yang tidak ada')
