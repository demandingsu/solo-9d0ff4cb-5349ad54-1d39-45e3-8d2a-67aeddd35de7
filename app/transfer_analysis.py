"""样品交接链分析：从入库起按前序记录编号还原唯一交接链并核对可交性。

输入为交接目录抓到的全部记录 + 抓取失败页，加上用户填写的标段号、样品编号与核对时刻。

判定分三档：
- 可交（DELIVERABLE）：截至核对时刻的记录能还原从入库起的唯一链；人员逐笔衔接
  （本笔交出方 = 前笔接收方）、封签编号逐笔一致且全程“完好”；末笔接收方为评审室。
- 不可交（NOT_DELIVERABLE）：链本身可信但业务条件不满足——
  末笔接收方不是评审室（未到评审室），或封签曾登记“破损”；
  曾破损的事实不会被后续“完好”登记覆盖。
- 待核实（NEED_VERIFY）：数据不足以支撑结论——相关页面抓取失败、无记录、
  编号冲突、缺前序、分叉、多条入库、成环，或人员 / 封签编号逐笔衔接不上。

只看不晚于核对时刻的记录；晚于核对时刻的记录列入“已排除记录”供页面说明。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from transfer_scraper import SEAL_BROKEN, PageFailure, TransferRecord

VERDICT_DELIVERABLE = "可交"
VERDICT_NOT_DELIVERABLE = "不可交"
VERDICT_NEED_VERIFY = "待核实"

REVIEW_ROOM = "评审室"
_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d")


class CutoffTimeError(ValueError):
    """核对时刻格式无法识别。"""


def parse_cutoff(raw: str) -> datetime:
    raw = raw.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise CutoffTimeError(f"核对时刻格式无法识别：{raw!r}")


def _to_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _view(r: TransferRecord) -> dict:
    """模板用的记录视图。"""
    return {
        "record_no": r.record_no,
        "section_no": r.section_no,
        "sample_no": r.sample_no,
        "event_time": r.event_time,
        "from_party": r.from_party,
        "to_party": r.to_party,
        "seal_no": r.seal_no,
        "seal_status": r.seal_status,
        "seal_label": r.seal_label,
        "prev_record": r.prev_record,
        "note": r.note,
        "url": r.url,
        "personnel_mismatch": False,
        "seal_mismatch": False,
    }


def analyze_transfer(
    records: Iterable[TransferRecord],
    failed_pages: Iterable[PageFailure],
    section_no: str,
    sample_no: str,
    cutoff_raw: str,
) -> dict:
    cutoff = parse_cutoff(cutoff_raw)
    section_no = section_no.strip()
    sample_no = sample_no.strip()

    matched = [r for r in records if r.section_no == section_no and r.sample_no == sample_no]
    in_window = [r for r in matched if _to_dt(r.event_time) <= cutoff]
    excluded = sorted(
        (r for r in matched if _to_dt(r.event_time) > cutoff),
        key=lambda r: (r.event_time, r.record_no),
    )

    issues: list[str] = []
    problem_urls = [(f.url, f.message) for f in failed_pages]
    # 数据可信性问题：任一存在都只能判“待核实”，不得据此给出可交/不可交结论
    trust_issues = bool(problem_urls)
    for url, message in problem_urls:
        issues.append(f"相关页面抓取失败：{url}（{message}）")

    chain_views: list[dict] = []
    chain_order_ok = False
    linkage_broken = False  # 人员或封签逐笔衔接不上
    seal_ever_broken = any(r.seal_status == SEAL_BROKEN for r in in_window)
    ends_at_review_room = False

    if not in_window:
        trust_issues = True
        if matched:
            issues.append(
                f"标段 {section_no} / 样品 {sample_no} 有 {len(matched)} 条记录，但均晚于核对时刻 {cutoff_raw}，"
                "截至该时刻无可用记录。"
            )
        else:
            issues.append(f"未找到标段 {section_no} / 样品 {sample_no} 的任何交接记录，请核对标段号与样品编号。")
    else:
        # 1) 编号冲突：同一记录编号出现多份登记
        by_no: dict[str, list[TransferRecord]] = {}
        for r in in_window:
            by_no.setdefault(r.record_no, []).append(r)
        dup_nos = sorted(no for no, group in by_no.items() if len(group) > 1)
        for no in dup_nos:
            trust_issues = True
            versions = "；".join(
                f"{r.event_time} {r.from_party or '（入库）'}→{r.to_party}（来源 {r.url}）"
                for r in by_no[no]
            )
            issues.append(f"编号冲突：记录编号 {no} 存在 {len(by_no[no])} 份内容不一致的登记——{versions}")

        # 2) 入库点：前序为空的记录应当唯一
        intakes = [r for r in in_window if r.is_intake]
        if len(intakes) == 0:
            trust_issues = True
            issues.append("找不到入库记录（无前序编号的记录），交接链无法从入库起还原。")
        elif len(intakes) > 1:
            trust_issues = True
            issues.append(
                "存在多条入库记录（无前序编号）：" + "、".join(r.record_no for r in intakes) + "，链起点不唯一。"
            )

        # 3) 缺前序：非入库记录指向的前序编号在截至时刻的记录集合中不存在
        existing_nos = set(by_no)
        for r in in_window:
            if not r.is_intake and r.prev_record not in existing_nos:
                trust_issues = True
                issues.append(
                    f"缺前序：记录 {r.record_no}（{r.event_time}）指向的前序记录 {r.prev_record} "
                    "在截至核对时刻的记录中不存在（前序缺失或晚于核对时刻）。"
                )

        # 4) 分叉 / 成环：统计每个前序编号的后继
        successors: dict[str, list[TransferRecord]] = {}
        for r in in_window:
            if not r.is_intake:
                successors.setdefault(r.prev_record, []).append(r)
        for prev_no, group in sorted(successors.items()):
            if len(group) > 1:
                trust_issues = True
                issues.append(
                    f"交接链分叉：前序记录 {prev_no} 同时存在多条后继——"
                    + "、".join(f"{r.record_no}（{r.event_time}）" for r in group)
                )

        # 5) 在无编号冲突的前提下尝试还原唯一链
        if not dup_nos and len(intakes) == 1:
            nodes = {no: group[0] for no, group in by_no.items()}
            ordered: list[TransferRecord] = []
            current: TransferRecord | None = intakes[0]
            seen: set[str] = set()
            cyclic = False
            while current is not None:
                if current.record_no in seen:
                    cyclic = True
                    issues.append(f"交接链成环：记录 {current.record_no} 在链上重复出现。")
                    break
                seen.add(current.record_no)
                ordered.append(current)
                nxt_list = successors.get(current.record_no, [])
                current = nxt_list[0] if len(nxt_list) == 1 else None
            if not cyclic and len(ordered) == len(nodes) and not any(
                not r.is_intake and r.prev_record not in existing_nos for r in in_window
            ):
                chain_order_ok = True
                chain_views = [_view(r) for r in ordered]

                # 6) 人员逐笔衔接：本笔交出方必须等于前笔接收方；封签编号须逐笔一致
                for idx in range(1, len(ordered)):
                    prev, cur = ordered[idx - 1], ordered[idx]
                    if cur.from_party != prev.to_party:
                        trust_issues = True
                        linkage_broken = True
                        chain_views[idx]["personnel_mismatch"] = True
                        issues.append(
                            f"人员衔接不上：记录 {cur.record_no} 的交出方“{cur.from_party or '空'}”"
                            f"与前序 {prev.record_no} 的接收方“{prev.to_party}”不一致。"
                        )
                    if cur.seal_no != prev.seal_no:
                        trust_issues = True
                        linkage_broken = True
                        chain_views[idx]["seal_mismatch"] = True
                        issues.append(
                            f"封签衔接不上：记录 {cur.record_no} 的封签编号 {cur.seal_no} "
                            f"与前序 {prev.record_no} 的封签编号 {prev.seal_no} 不一致。"
                        )
            else:
                if not cyclic:
                    trust_issues = True
                    leftover = sorted(set(nodes) - {r.record_no for r in ordered})
                    issues.append(
                        "交接链无法覆盖全部记录，链在中途断开或成环；未纳入唯一链的记录："
                        + "、".join(leftover)
                    )
                chain_views = [_view(r) for r in sorted(in_window, key=lambda x: (x.event_time, x.record_no))]
        else:
            chain_views = [_view(r) for r in sorted(in_window, key=lambda x: (x.event_time, x.record_no))]

        if chain_views:
            ends_at_review_room = chain_views[-1]["to_party"] == REVIEW_ROOM

    # 判定优先级：数据不可信（抓取失败 / 结构异常 / 衔接断裂）先标待核实；
    # 链可信时再看业务条件——封签曾破损或未达评审室则不可交，否则可交。
    if trust_issues or not chain_order_ok or linkage_broken:
        verdict = VERDICT_NEED_VERIFY
    elif seal_ever_broken:
        verdict = VERDICT_NOT_DELIVERABLE
        broken = [
            f"{r.record_no}（{r.event_time}，封签 {r.seal_no} 登记“破损”）"
            for r in in_window
            if r.seal_status == SEAL_BROKEN
        ]
        issues.append("封签曾破损，破损事实不得被后续“完好”登记覆盖：" + "、".join(broken) + "。")
    elif not ends_at_review_room:
        verdict = VERDICT_NOT_DELIVERABLE
        last_to = chain_views[-1]["to_party"] if chain_views else "—"
        issues.append(f"末笔接收方为“{last_to}”而非评审室，样品截至核对时刻未送达评审室。")
    else:
        verdict = VERDICT_DELIVERABLE

    return {
        "verdict": verdict,
        "section_no": section_no,
        "sample_no": sample_no,
        "cutoff_time": cutoff.strftime("%Y-%m-%d %H:%M"),
        "issues": issues,
        "problem_urls": problem_urls,
        "chain": chain_views,
        "chain_order_ok": chain_order_ok,
        "excluded": [_view(r) for r in excluded],
        "seal_ever_broken": seal_ever_broken,
        "ends_at_review_room": ends_at_review_room,
        "total_matched": len(matched),
        "in_window_count": len(in_window),
    }
