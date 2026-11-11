"""交接详情页解析与同源判断测试。"""

import pytest

from transfer_scraper import SEAL_BROKEN, SEAL_INTACT, ScrapeError, parse_transfer_detail, same_origin

DETAIL_HTML = """<!DOCTYPE html>
<html><body>
<div class="transfer-record">
  <h2>标段 BD-2026-01 ｜ 样品 SP-01-001</h2>
  <dl class="transfer-fields">
    <dt>记录编号</dt><dd id="record-no">TR-2026-0103</dd>
    <dt>标段号</dt><dd id="section-no">BD-2026-01</dd>
    <dt>样品编号</dt><dd id="sample-no">SP-01-001</dd>
    <dt>发生时间</dt><dd id="event-time">2026-11-11 08:50</dd>
    <dt>交出方</dt><dd id="from-party">暂存间</dd>
    <dt>接收方</dt><dd id="to-party">流转专员</dd>
    <dt>封签编号</dt><dd id="seal-no">SEAL-A001</dd>
    <dt>封签状态</dt><dd id="seal-status" data-seal-status="intact"><span class="seal-intact">完好</span></dd>
    <dt>前序记录编号</dt><dd id="prev-record"><a href="/transfer/detail/TR-2026-0102.html">TR-2026-0102</a></dd>
  </dl>
  <p class="note">评标日早上由流转专员领取。</p>
</div>
</body></html>"""

INTAKE_HTML = """<!DOCTYPE html>
<html><body>
<div class="transfer-record">
  <dl class="transfer-fields">
    <dt>记录编号</dt><dd id="record-no">TR-2026-0101</dd>
    <dt>标段号</dt><dd id="section-no">BD-2026-01</dd>
    <dt>样品编号</dt><dd id="sample-no">SP-01-001</dd>
    <dt>发生时间</dt><dd id="event-time">2026-11-10 08:30</dd>
    <dt>接收方</dt><dd id="to-party">样品库</dd>
    <dt>封签编号</dt><dd id="seal-no">SEAL-A001</dd>
    <dt>封签状态</dt><dd id="seal-status" data-seal-status="intact">完好</dd>
  </dl>
  <p class="note">入库登记。</p>
</div>
</body></html>"""

URL = "http://example.com/transfer/detail/TR-2026-0103.html"


def test_parse_full_detail():
    (r,) = parse_transfer_detail(DETAIL_HTML, URL)
    assert r.record_no == "TR-2026-0103"
    assert r.section_no == "BD-2026-01"
    assert r.sample_no == "SP-01-001"
    assert r.event_time == "2026-11-11 08:50"
    assert r.from_party == "暂存间"
    assert r.to_party == "流转专员"
    assert r.seal_no == "SEAL-A001"
    assert r.seal_status == SEAL_INTACT
    assert r.prev_record == "TR-2026-0102"
    assert r.url == URL
    assert r.is_intake is False


def test_parse_intake_has_no_prev_and_from_party():
    (r,) = parse_transfer_detail(INTAKE_HTML, "http://example.com/transfer/detail/TR-2026-0101.html")
    assert r.prev_record is None
    assert r.from_party is None
    assert r.is_intake is True


def test_parse_broken_seal_via_data_attribute():
    html = DETAIL_HTML.replace('data-seal-status="intact"', 'data-seal-status="broken"').replace(
        '>完好<', '>破损<'
    )
    (r,) = parse_transfer_detail(html, URL)
    assert r.seal_status == SEAL_BROKEN


def test_parse_seal_status_falls_back_to_chinese_text():
    html = DETAIL_HTML.replace(' data-seal-status="intact"', "")
    (r,) = parse_transfer_detail(html, URL)
    assert r.seal_status == SEAL_INTACT


def test_parse_unknown_seal_status_raises():
    html = DETAIL_HTML.replace('data-seal-status="intact"', 'data-seal-status="weird"').replace(
        ">完好<", ">未知<"
    )
    with pytest.raises(ScrapeError, match="封签状态"):
        parse_transfer_detail(html, URL)


def test_parse_missing_required_field():
    html = DETAIL_HTML.replace('<dd id="to-party">流转专员</dd>', '<dd id="to-party"></dd>')
    with pytest.raises(ScrapeError) as exc:
        parse_transfer_detail(html, URL)
    assert "接收方" in exc.value.message


def test_parse_bad_time_format():
    html = DETAIL_HTML.replace("2026-11-11 08:50", "11月11日早上")
    with pytest.raises(ScrapeError, match="发生时间"):
        parse_transfer_detail(html, URL)


def test_parse_page_without_container_raises():
    with pytest.raises(ScrapeError, match="div.transfer-record"):
        parse_transfer_detail("<html><body><p>无关页面</p></body></html>", URL)


def _container(to_party, event):
    return f"""<div class="transfer-record">
      <dl class="transfer-fields">
        <dt>记录编号</dt><dd id="record-no">TR-2026-0103</dd>
        <dt>标段号</dt><dd id="section-no">BD-2026-01</dd>
        <dt>样品编号</dt><dd id="sample-no">SP-01-001</dd>
        <dt>发生时间</dt><dd id="event-time">{event}</dd>
        <dt>交出方</dt><dd id="from-party">暂存间</dd>
        <dt>接收方</dt><dd id="to-party">{to_party}</dd>
        <dt>封签编号</dt><dd id="seal-no">SEAL-A001</dd>
        <dt>封签状态</dt><dd id="seal-status" data-seal-status="intact">完好</dd>
        <dt>前序记录编号</dt><dd id="prev-record">TR-2026-0102</dd>
      </dl>
      <p class="note">登记。</p>
    </div>"""


def test_parse_multiple_records_on_one_page_conflict_case():
    html = (
        "<html><body>"
        + _container("流转专员", "2026-11-11 08:50")
        + _container("评审室", "2026-11-11 09:00")
        + "</body></html>"
    )
    records = parse_transfer_detail(html, URL)
    assert len(records) == 2
    assert records[0].to_party == "流转专员"
    assert records[1].to_party == "评审室"
    assert all(r.record_no == "TR-2026-0103" for r in records)


def test_same_origin_transfer_urls():
    base = "http://example.com/transfer/list.html?page=1"
    assert same_origin("http://example.com/transfer/detail/R1.html", base)
    assert same_origin("http://example.com:80/transfer/list.html?page=2", base)
    assert not same_origin("http://other.com/transfer/detail/R1.html", base)
    assert not same_origin("https://example.com/transfer/list.html", base)
