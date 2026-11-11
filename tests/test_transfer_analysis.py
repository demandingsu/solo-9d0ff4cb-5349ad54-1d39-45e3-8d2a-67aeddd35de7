"""样品交接链分析逻辑测试。"""

import pytest

from transfer_analysis import (
    VERDICT_DELIVERABLE,
    VERDICT_NEED_VERIFY,
    VERDICT_NOT_DELIVERABLE,
    CutoffTimeError,
    analyze_transfer,
    parse_cutoff,
)
from transfer_scraper import SEAL_BROKEN, SEAL_INTACT, PageFailure, TransferRecord

CUTOFF = "2026-11-11 18:00"


def rec(
    no,
    event,
    to,
    prev=None,
    frm=None,
    section="BD-1",
    sample="SP-1",
    seal="SEAL-1",
    status=SEAL_INTACT,
    url=None,
):
    return TransferRecord(
        record_no=no,
        section_no=section,
        sample_no=sample,
        event_time=event,
        from_party=frm,
        to_party=to,
        seal_no=seal,
        seal_status=status,
        prev_record=prev,
        note="",
        url=url or f"http://example.com/transfer/detail/{no}.html",
    )


def full_chain():
    """入库 → 暂存间 → 流转专员 → 评审室，封签全程完好。"""
    return [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-10 10:05", "暂存间", prev="R1", frm="样品库"),
        rec("R3", "2026-11-11 08:50", "流转专员", prev="R2", frm="暂存间"),
        rec("R4", "2026-11-11 09:20", "评审室", prev="R3", frm="流转专员"),
    ]


def analyze(records, failed=None, section="BD-1", sample="SP-1", cutoff=CUTOFF):
    return analyze_transfer(records, failed or [], section, sample, cutoff)


def test_full_chain_to_review_room_is_deliverable():
    result = analyze(full_chain())
    assert result["verdict"] == VERDICT_DELIVERABLE
    assert result["chain_order_ok"] is True
    assert [c["record_no"] for c in result["chain"]] == ["R1", "R2", "R3", "R4"]
    assert result["ends_at_review_room"] is True
    assert result["issues"] == []


def test_records_after_cutoff_are_excluded_and_chain_truncated():
    records = full_chain() + [
        rec("R5", "2026-11-12 09:00", "档案室", prev="R4", frm="评审室")
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_DELIVERABLE
    assert [c["record_no"] for c in result["chain"]] == ["R1", "R2", "R3", "R4"]
    assert [c["record_no"] for c in result["excluded"]] == ["R5"]
    assert result["total_matched"] == 5
    assert result["in_window_count"] == 4


def test_cutoff_excludes_everything_needs_verify():
    records = full_chain()
    result = analyze(records, cutoff="2026-11-09 18:00")
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert result["chain"] == []
    assert "均晚于核对时刻" in result["issues"][0]


def test_seal_broken_once_is_not_deliverable_even_if_later_intact():
    records = full_chain()
    records[1] = rec("R2", "2026-11-10 10:05", "暂存间", prev="R1", frm="样品库", status=SEAL_BROKEN)
    result = analyze(records)
    assert result["verdict"] == VERDICT_NOT_DELIVERABLE
    assert result["seal_ever_broken"] is True
    assert any("破损事实不得被后续" in msg for msg in result["issues"])
    # 后续仍登记完好
    assert all(c["seal_status"] == SEAL_INTACT for c in result["chain"][2:])


def test_not_reaching_review_room_is_not_deliverable():
    records = [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 08:40", "暂存间", prev="R1", frm="样品库"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NOT_DELIVERABLE
    assert result["ends_at_review_room"] is False
    assert "未送达评审室" in result["issues"][0]


def test_fork_is_need_verify():
    records = [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 08:20", "暂存间", prev="R1", frm="样品库"),
        rec("R3", "2026-11-11 09:00", "流转专员", prev="R2", frm="暂存间"),
        rec("R4", "2026-11-11 09:05", "流转专员", prev="R2", frm="暂存间"),
        rec("R5", "2026-11-11 09:30", "评审室", prev="R3", frm="流转专员"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any("交接链分叉" in msg for msg in result["issues"])
    assert result["chain_order_ok"] is False


def test_missing_prev_is_need_verify():
    records = [
        rec("R1", "2026-11-10 10:00", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 09:00", "流转专员", prev="R999", frm="暂存间"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any("缺前序" in msg and "R999" in msg for msg in result["issues"])


def test_duplicate_record_no_conflict_is_need_verify():
    records = [
        rec("R1", "2026-11-10 10:20", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 08:30", "暂存间", prev="R1", frm="样品库",
            url="http://example.com/transfer/detail/R2.html"),
        rec("R2", "2026-11-11 08:35", "流转专员", prev="R1", frm="样品库",
            url="http://example.com/transfer/detail/R2.html"),
        rec("R3", "2026-11-11 09:15", "评审室", prev="R2", frm="流转专员"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any("编号冲突" in msg and "R2" in msg for msg in result["issues"])


def test_personnel_gap_is_need_verify():
    records = [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 08:50", "流转专员", prev="R1", frm="暂存间"),  # 交出方≠样品库
        rec("R3", "2026-11-11 09:20", "评审室", prev="R2", frm="流转专员"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any("人员衔接不上" in msg for msg in result["issues"])
    assert result["chain"][1]["personnel_mismatch"] is True


def test_seal_no_gap_is_need_verify():
    records = [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None, seal="SEAL-1"),
        rec("R2", "2026-11-11 08:50", "暂存间", prev="R1", frm="样品库", seal="SEAL-9"),
        rec("R3", "2026-11-11 09:20", "评审室", prev="R2", frm="暂存间", seal="SEAL-9"),
    ]
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any("封签衔接不上" in msg for msg in result["issues"])
    assert result["chain"][1]["seal_mismatch"] is True


def test_failed_detail_page_forces_need_verify_even_if_chain_intact():
    failed = [PageFailure("http://example.com/transfer/detail/R5.html", "HTTP 500")]
    result = analyze(full_chain(), failed=failed)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert result["problem_urls"][0][0].endswith("R5.html")
    assert any("抓取失败" in msg for msg in result["issues"])


def test_no_matching_record_is_need_verify():
    result = analyze(full_chain(), section="BD-X", sample="SP-X")
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert "未找到" in result["issues"][0]


def test_section_and_sample_filtering():
    records = full_chain() + [
        # 另一标段只有入库记录且末笔接收方不是评审室
        rec("O1", "2026-11-11 09:00", "样品库", prev=None, frm=None, section="BD-2", sample="SP-2"),
    ]
    result = analyze(records, section="BD-2", sample="SP-2")
    assert result["verdict"] == VERDICT_NOT_DELIVERABLE
    assert [c["record_no"] for c in result["chain"]] == ["O1"]


def test_chain_restored_from_unsorted_input():
    records = list(reversed(full_chain()))
    result = analyze(records)
    assert result["verdict"] == VERDICT_DELIVERABLE
    assert [c["record_no"] for c in result["chain"]] == ["R1", "R2", "R3", "R4"]


def test_cycle_is_need_verify():
    records = [
        rec("R1", "2026-11-10 08:30", "样品库", prev=None, frm=None),
        rec("R2", "2026-11-11 08:50", "暂存间", prev="R1", frm="样品库"),
        rec("R3", "2026-11-11 09:20", "样品库", prev="R2", frm="暂存间"),
        rec("R4", "2026-11-11 09:40", "暂存间", prev="R3", frm="样品库"),
    ]
    # 人为制造环：R1 的前序指向 R4（R1 不再是入库点，因此再加一个入库点保证链起点存在）
    records[0] = rec("R0", "2026-11-10 08:00", "门卫", prev=None, frm=None)
    records.append(rec("R1", "2026-11-10 08:30", "样品库", prev="R4", frm="门卫"))
    result = analyze(records)
    assert result["verdict"] == VERDICT_NEED_VERIFY
    assert any(
        "成环" in msg or "缺前序" in msg or "分叉" in msg or "无法覆盖全部记录" in msg
        for msg in result["issues"]
    )


def test_bad_cutoff_time_raises():
    with pytest.raises(CutoffTimeError):
        parse_cutoff("11月11日下午")


def test_cutoff_accepts_multiple_formats():
    assert parse_cutoff("2026/11/11 18:00:00").strftime("%Y-%m-%d %H:%M") == "2026-11-11 18:00"
