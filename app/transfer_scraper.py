"""交接目录页 / 交接详情页抓取与解析。

解析约定（与示例站交接页面结构一致）：
- 交接目录页：记录链接 ul.transfer-list a[href]；分页导航 nav.pagination a[href]
- 交接详情页：容器 div.transfer-record（同一页可能有多个，对应编号冲突的多份登记），
  字段 #record-no / #section-no / #sample-no / #event-time / #from-party（入库无）/
  #to-party / #seal-no / #seal-status（data-seal-status=intact|broken）/
  #prev-record（入库无）

只跟随与起始目录网址同源的链接。失败处理与公告抓取不同：
- 目录页无法抓取 / 解析时抛 ScrapeError（携带出错网址），整次核对无法进行；
- 单个详情页失败不中断抓取，记入 failed_pages，由分析层把结论标为“待核实”并列网址。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_LIST_PAGES = 50
MAX_DETAIL_PAGES = 500
USER_AGENT = "bid-secretary-transfer-checker/1.0"

SEAL_INTACT = "intact"
SEAL_BROKEN = "broken"
SEAL_LABELS = {SEAL_INTACT: "完好", SEAL_BROKEN: "破损"}
_SEAL_TEXT_MAP = {"完好": SEAL_INTACT, "破损": SEAL_BROKEN}

_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d")


class ScrapeError(Exception):
    """目录页抓取或解析失败。url 为出错的页面网址。"""

    def __init__(self, url: str, message: str):
        self.url = url
        self.message = message
        super().__init__(f"{url}：{message}")


@dataclass
class TransferRecord:
    record_no: str
    section_no: str
    sample_no: str
    event_time: str  # 归一化为 YYYY-MM-DD HH:MM
    from_party: str | None  # 入库记录为 None
    to_party: str
    seal_no: str
    seal_status: str  # intact / broken
    prev_record: str | None  # 入库记录为 None
    note: str
    url: str

    @property
    def seal_label(self) -> str:
        return SEAL_LABELS.get(self.seal_status, self.seal_status)

    @property
    def is_intake(self) -> bool:
        return self.prev_record is None


@dataclass
class PageFailure:
    url: str
    message: str


@dataclass
class TransferScrapeResult:
    records: list[TransferRecord] = field(default_factory=list)
    list_pages: list[str] = field(default_factory=list)
    detail_pages: list[str] = field(default_factory=list)
    failed_pages: list[PageFailure] = field(default_factory=list)


def _default_port(scheme: str) -> int | None:
    return {"http": 80, "https": 443}.get(scheme)


def same_origin(url: str, origin_url: str) -> bool:
    p, o = urlparse(url), urlparse(origin_url)
    return (p.scheme, p.hostname, _default_port(p.scheme) if p.port is None else p.port) == (
        o.scheme,
        o.hostname,
        _default_port(o.scheme) if o.port is None else o.port,
    )


def _normalize(href: str, base: str) -> str:
    url, _frag = urldefrag(urljoin(base, href))
    return url


def _fetch_soup(client: httpx.Client, url: str):
    """返回 (soup, error_message)；抓取失败时 error_message 非空，soup 为 None。"""
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"请求失败：{exc}"
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}"
    return BeautifulSoup(resp.text, "html.parser"), None


def _norm_time(raw: str, url: str, field_name: str) -> str:
    raw = raw.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    raise ScrapeError(url, f"{field_name}格式无法识别：{raw!r}")


def _text(node, selector: str) -> str | None:
    el = node.select_one(selector)
    if el is None:
        return None
    return el.get_text(strip=True) or None


def _parse_seal_status(node, url: str) -> str:
    el = node.select_one("#seal-status")
    if el is None:
        raise ScrapeError(url, "缺少必要字段：封签状态")
    raw = (el.get("data-seal-status") or "").strip()
    if raw in SEAL_LABELS:
        return raw
    text = el.get_text(strip=True)
    if text in _SEAL_TEXT_MAP:
        return _SEAL_TEXT_MAP[text]
    raise ScrapeError(url, f"封签状态无法识别：{text!r}")


def parse_transfer_detail(html: str, url: str) -> list[TransferRecord]:
    """解析单个交接详情页；同页多份登记（编号冲突）时返回多条。"""
    soup = BeautifulSoup(html, "html.parser")
    roots = soup.select("div.transfer-record")
    if not roots:
        raise ScrapeError(url, "页面结构不符：未找到 div.transfer-record 容器")

    records: list[TransferRecord] = []
    for root in roots:
        record_no = _text(root, "#record-no")
        section_no = _text(root, "#section-no")
        sample_no = _text(root, "#sample-no")
        event_raw = _text(root, "#event-time")
        to_party = _text(root, "#to-party")
        seal_no = _text(root, "#seal-no")
        missing = [
            name
            for name, val in (
                ("记录编号", record_no),
                ("标段号", section_no),
                ("样品编号", sample_no),
                ("发生时间", event_raw),
                ("接收方", to_party),
                ("封签编号", seal_no),
            )
            if not val
        ]
        if missing:
            raise ScrapeError(url, "缺少必要字段：" + "、".join(missing))

        seal_status = _parse_seal_status(root, url)
        note_el = root.select_one("p.note")
        records.append(
            TransferRecord(
                record_no=record_no,
                section_no=section_no,
                sample_no=sample_no,
                event_time=_norm_time(event_raw, url, "发生时间"),
                from_party=_text(root, "#from-party"),
                to_party=to_party,
                seal_no=seal_no,
                seal_status=seal_status,
                prev_record=_text(root, "#prev-record"),
                note=note_el.get_text(strip=True) if note_el else "",
                url=url,
            )
        )
    return records


def scrape_transfer(start_url: str) -> TransferScrapeResult:
    """从交接目录网址出发，抓完同源分页与全部详情页。

    目录页失败抛 ScrapeError；详情页失败收集到 failed_pages，不中断其余页面。
    """
    parsed = urlparse(start_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScrapeError(start_url, "起始网址必须是 http(s) 网址")

    result = TransferScrapeResult()
    visited_lists: set[str] = set()
    queue = [start_url]
    detail_urls: list[str] = []
    seen_details: set[str] = set()

    with httpx.Client(
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        # 1) 遍历同源分页，收集详情页链接
        while queue:
            url = queue.pop(0)
            if url in visited_lists:
                continue
            if len(visited_lists) >= MAX_LIST_PAGES:
                raise ScrapeError(url, f"分页数量超过上限 {MAX_LIST_PAGES}")
            soup, error = _fetch_soup(client, url)
            if error:
                raise ScrapeError(url, error)

            items = soup.select("ul.transfer-list a[href]")
            nav_links = soup.select("nav.pagination a[href]")
            if not items and not nav_links:
                raise ScrapeError(url, "页面结构不符：未找到交接目录（ul.transfer-list）或分页导航（nav.pagination）")

            for a in items:
                href = _normalize(a["href"], url)
                if not same_origin(href, start_url):
                    continue  # 跨源链接不跟随
                if href not in seen_details:
                    seen_details.add(href)
                    detail_urls.append(href)

            visited_lists.add(url)
            result.list_pages.append(url)
            for a in nav_links:
                href = _normalize(a["href"], url)
                if same_origin(href, start_url) and href not in visited_lists and href not in queue:
                    queue.append(href)

        # 2) 逐个抓取详情页；单页失败记录后继续，保证把问题网址全部带回去
        for durl in detail_urls:
            if len(result.detail_pages) >= MAX_DETAIL_PAGES:
                result.failed_pages.append(PageFailure(durl, f"详情页数量超过上限 {MAX_DETAIL_PAGES}"))
                break
            soup, error = _fetch_soup(client, durl)
            if error:
                result.failed_pages.append(PageFailure(durl, error))
                continue
            try:
                page_records = parse_transfer_detail(str(soup), durl)
            except ScrapeError as exc:
                result.failed_pages.append(PageFailure(durl, exc.message))
                continue
            result.records.extend(page_records)
            result.detail_pages.append(durl)

    return result
