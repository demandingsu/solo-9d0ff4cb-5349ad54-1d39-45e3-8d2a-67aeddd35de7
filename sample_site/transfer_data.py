"""示例公告站的交接记录数据（投标样品入库 / 交接核对演示）。

字段与采集端约定的交接页面结构一一对应：
- record_no    记录编号（详情页路径 /transfer/detail/<record_no>.html）
- section_no   标段号
- sample_no    样品编号
- event_time   发生时间（YYYY-MM-DD HH:MM）
- from_party   交出方（入库记录为 None）
- to_party     接收方
- seal_no      封签编号
- seal_status  封签状态：intact 完好 / broken 破损
- prev_record  前序记录编号（入库记录为 None）
- note         交接说明

标段场景一览：
- BD-2026-01：完整链，入库 → 暂存 → 流转 → 评审室，封签全程完好（可交）
- BD-2026-02：途中封签破损，虽送达评审室也不可交（不可交）
- BD-2026-03：末笔接收方不是评审室（不可交）
- BD-2026-04：同一前序出现两条后继记录，交接链分叉（待核实）
- BD-2026-05：后继记录指向不存在的前序编号，缺前序（待核实）
- BD-2026-06：两条记录编号相同但内容不一致，编号冲突（待核实）
"""

SEAL_INTACT = "intact"
SEAL_BROKEN = "broken"

SEAL_LABELS = {
    SEAL_INTACT: "完好",
    SEAL_BROKEN: "破损",
}

TRANSFER_RECORDS = [
    # ---- BD-2026-01：完整链（可交）。TR-0105 晚于核对时刻，演示只看截至时刻的记录 ----
    {
        "record_no": "TR-2026-0101",
        "section_no": "BD-2026-01",
        "sample_no": "SP-01-001",
        "event_time": "2026-11-10 08:30",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-A001",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库，核验外观与封签后登记。",
    },
    {
        "record_no": "TR-2026-0102",
        "section_no": "BD-2026-01",
        "sample_no": "SP-01-001",
        "event_time": "2026-11-10 10:05",
        "from_party": "样品库",
        "to_party": "暂存间",
        "seal_no": "SEAL-A001",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0101",
        "note": "入库后移交暂存间保管。",
    },
    {
        "record_no": "TR-2026-0103",
        "section_no": "BD-2026-01",
        "sample_no": "SP-01-001",
        "event_time": "2026-11-11 08:50",
        "from_party": "暂存间",
        "to_party": "流转专员",
        "seal_no": "SEAL-A001",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0102",
        "note": "评标日早上由流转专员领取。",
    },
    {
        "record_no": "TR-2026-0104",
        "section_no": "BD-2026-01",
        "sample_no": "SP-01-001",
        "event_time": "2026-11-11 09:20",
        "from_party": "流转专员",
        "to_party": "评审室",
        "seal_no": "SEAL-A001",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0103",
        "note": "送达评审室并签收。",
    },
    {
        "record_no": "TR-2026-0105",
        "section_no": "BD-2026-01",
        "sample_no": "SP-01-001",
        "event_time": "2026-11-12 09:00",
        "from_party": "评审室",
        "to_party": "档案室",
        "seal_no": "SEAL-A001",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0104",
        "note": "评审结束后归档（晚于核对时刻，核对时应被排除）。",
    },
    # ---- BD-2026-02：封签曾破损，后续登记“完好”不得覆盖（不可交） ----
    {
        "record_no": "TR-2026-0201",
        "section_no": "BD-2026-02",
        "sample_no": "SP-02-002",
        "event_time": "2026-11-10 09:00",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-B002",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库。",
    },
    {
        "record_no": "TR-2026-0202",
        "section_no": "BD-2026-02",
        "sample_no": "SP-02-002",
        "event_time": "2026-11-10 14:20",
        "from_party": "样品库",
        "to_party": "暂存间",
        "seal_no": "SEAL-B002",
        "seal_status": SEAL_BROKEN,
        "prev_record": "TR-2026-0201",
        "note": "搬运途中封签撕裂，登记破损并暂停流转。",
    },
    {
        "record_no": "TR-2026-0203",
        "section_no": "BD-2026-02",
        "sample_no": "SP-02-002",
        "event_time": "2026-11-11 08:30",
        "from_party": "暂存间",
        "to_party": "流转专员",
        "seal_no": "SEAL-B002",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0202",
        "note": "补贴封签后登记“完好”（破损事实不得被覆盖）。",
    },
    {
        "record_no": "TR-2026-0204",
        "section_no": "BD-2026-02",
        "sample_no": "SP-02-002",
        "event_time": "2026-11-11 09:10",
        "from_party": "流转专员",
        "to_party": "评审室",
        "seal_no": "SEAL-B002",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0203",
        "note": "送达评审室。",
    },
    # ---- BD-2026-03：封签完好但末笔接收方不是评审室（不可交） ----
    {
        "record_no": "TR-2026-0301",
        "section_no": "BD-2026-03",
        "sample_no": "SP-03-003",
        "event_time": "2026-11-10 09:20",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-C003",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库。",
    },
    {
        "record_no": "TR-2026-0302",
        "section_no": "BD-2026-03",
        "sample_no": "SP-03-003",
        "event_time": "2026-11-11 08:40",
        "from_party": "样品库",
        "to_party": "暂存间",
        "seal_no": "SEAL-C003",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0301",
        "note": "移交暂存间，等待评标日领取。",
    },
    # ---- BD-2026-04：分叉——TR-2026-0402 有两条后继记录（待核实） ----
    {
        "record_no": "TR-2026-0401",
        "section_no": "BD-2026-04",
        "sample_no": "SP-04-004",
        "event_time": "2026-11-10 09:40",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-D004",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库。",
    },
    {
        "record_no": "TR-2026-0402",
        "section_no": "BD-2026-04",
        "sample_no": "SP-04-004",
        "event_time": "2026-11-11 08:20",
        "from_party": "样品库",
        "to_party": "暂存间",
        "seal_no": "SEAL-D004",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0401",
        "note": "移交暂存间。",
    },
    {
        "record_no": "TR-2026-0403",
        "section_no": "BD-2026-04",
        "sample_no": "SP-04-004",
        "event_time": "2026-11-11 09:00",
        "from_party": "暂存间",
        "to_party": "流转专员",
        "seal_no": "SEAL-D004",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0402",
        "note": "流转专员甲领取（与下一条同时指向前序，形成分叉）。",
    },
    {
        "record_no": "TR-2026-0404",
        "section_no": "BD-2026-04",
        "sample_no": "SP-04-004",
        "event_time": "2026-11-11 09:05",
        "from_party": "暂存间",
        "to_party": "流转专员",
        "seal_no": "SEAL-D004",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0402",
        "note": "流转专员乙重复登记领取（同一前序的第二条后继）。",
    },
    {
        "record_no": "TR-2026-0405",
        "section_no": "BD-2026-04",
        "sample_no": "SP-04-004",
        "event_time": "2026-11-11 09:30",
        "from_party": "流转专员",
        "to_party": "评审室",
        "seal_no": "SEAL-D004",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0403",
        "note": "送达评审室。",
    },
    # ---- BD-2026-05：缺前序——后继指向不存在的记录编号（待核实） ----
    {
        "record_no": "TR-2026-0501",
        "section_no": "BD-2026-05",
        "sample_no": "SP-05-005",
        "event_time": "2026-11-10 10:00",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-E005",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库。",
    },
    {
        "record_no": "TR-2026-0502",
        "section_no": "BD-2026-05",
        "sample_no": "SP-05-005",
        "event_time": "2026-11-11 09:00",
        "from_party": "暂存间",
        "to_party": "流转专员",
        "seal_no": "SEAL-E005",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0599",
        "note": "前序编号 TR-2026-0599 在本站不存在（缺前序）。",
    },
    # ---- BD-2026-06：编号冲突——同一记录编号两条详情，内容不一致（待核实） ----
    {
        "record_no": "TR-2026-0601",
        "section_no": "BD-2026-06",
        "sample_no": "SP-06-006",
        "event_time": "2026-11-10 10:20",
        "from_party": None,
        "to_party": "样品库",
        "seal_no": "SEAL-F006",
        "seal_status": SEAL_INTACT,
        "prev_record": None,
        "note": "投标样品入库。",
    },
    {
        "record_no": "TR-2026-0602",
        "section_no": "BD-2026-06",
        "sample_no": "SP-06-006",
        "event_time": "2026-11-11 08:30",
        "from_party": "样品库",
        "to_party": "暂存间",
        "seal_no": "SEAL-F006",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0601",
        "note": "移交暂存间（列表出现两次，对应详情内容冲突）。",
    },
    {
        "record_no": "TR-2026-0602",
        "section_no": "BD-2026-06",
        "sample_no": "SP-06-006",
        "event_time": "2026-11-11 08:35",
        "from_party": "样品库",
        "to_party": "流转专员",
        "seal_no": "SEAL-F006",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0601",
        "note": "同编号冲突记录：接收方与发生时间与上一条不一致。",
    },
    {
        "record_no": "TR-2026-0603",
        "section_no": "BD-2026-06",
        "sample_no": "SP-06-006",
        "event_time": "2026-11-11 09:15",
        "from_party": "流转专员",
        "to_party": "评审室",
        "seal_no": "SEAL-F006",
        "seal_status": SEAL_INTACT,
        "prev_record": "TR-2026-0602",
        "note": "送达评审室。",
    },
]

TRANSFER_PAGE_SIZE = 8

# 故障注入目标：开启后该交接记录详情页返回 500（同时保留公告站的 NT-2026-0004 注入）
FAIL_TRANSFER_RECORD = "TR-2026-0405"


def sorted_transfer_records():
    """交接列表按发生时间倒序展示；同时间按记录编号稳定排序。"""
    return sorted(TRANSFER_RECORDS, key=lambda r: (r["event_time"], r["record_no"]), reverse=True)


def get_transfer_record_versions(record_no):
    """同一记录编号可能存在多条（编号冲突演示），按发生时间升序返回。"""
    return sorted(
        [r for r in TRANSFER_RECORDS if r["record_no"] == record_no],
        key=lambda r: r["event_time"],
    )


def get_section_sample(section_no):
    """返回该标段涉及的样品编号集合（保持出现顺序）。"""
    seen = []
    for r in TRANSFER_RECORDS:
        if r["section_no"] == section_no and r["sample_no"] not in seen:
            seen.append(r["sample_no"])
    return seen
