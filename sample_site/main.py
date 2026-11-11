"""示例公告站：模拟公开招标公告网站与样品交接记录站。

页面结构（与采集端解析约定一致）：
- 公告列表页 /list.html?page=N
    - 公告链接：ul.notice-list a[href]
    - 分页导航：nav.pagination a[href]
- 公告详情页 /detail/<公告编号>.html
    - 容器 div.notice，data-notice-type = tender|correction|cancellation
    - #project-no 项目编号、#notice-no 公告编号、#publish-time 发布时间
    - #deadline 截标时间（如有）、#target-notice 更正/撤销所指公告编号（如有）
- 交接目录页 /transfer/list.html?page=N
    - 交接记录链接：ul.transfer-list a[href]
    - 分页导航：nav.pagination a[href]
- 交接详情页 /transfer/detail/<记录编号>.html
    - 容器 div.transfer-record
    - #record-no 记录编号、#section-no 标段号、#sample-no 样品编号、#event-time 发生时间
    - #from-party 交出方（入库无此节点）、#to-party 接收方
    - #seal-no 封签编号、#seal-status 封签状态（data-seal-status=intact|broken）
    - #prev-record 前序记录编号（入库无此节点）

故障注入：GET /admin/fail?on=1 开启后，公告详情 NT-2026-0004 与交接详情
TR-2026-0405 返回 500，用于演示采集端“页面抓取失败则标记待核实”的行为；on=0 关闭。
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from data import ANNOUNCEMENTS, PAGE_SIZE, TYPE_LABELS, get_by_notice_no, sorted_announcements
from transfer_data import (
    FAIL_TRANSFER_RECORD,
    SEAL_LABELS,
    TRANSFER_PAGE_SIZE,
    get_transfer_record_versions,
    sorted_transfer_records,
)

app = FastAPI(title="示例公告站")
templates = Jinja2Templates(directory="templates")

# 故障注入状态：开启后 FAIL_NOTICE 公告详情页与 FAIL_TRANSFER_RECORD 交接详情页返回 500
FAIL_STATE = {"on": False}
FAIL_NOTICE = "NT-2026-0004"


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/list.html?page=1")


@app.get("/list.html", response_class=HTMLResponse)
def list_page(request: Request, page: int = 1):
    items_all = sorted_announcements()
    total_pages = max(1, (len(items_all) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page < 1 or page > total_pages:
        return HTMLResponse("<h1>404 页码不存在</h1>", status_code=404)
    start = (page - 1) * PAGE_SIZE
    items = []
    for a in items_all[start : start + PAGE_SIZE]:
        items.append({**a, "type_label": TYPE_LABELS[a["type"]]})
    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "pages": list(range(1, total_pages + 1)),
            "fail_on": FAIL_STATE["on"],
            "fail_notice": FAIL_NOTICE,
        },
    )


@app.get("/detail/{notice_no}.html", response_class=HTMLResponse)
def detail_page(request: Request, notice_no: str):
    if FAIL_STATE["on"] and notice_no == FAIL_NOTICE:
        return HTMLResponse(
            f"<h1>500 Internal Server Error</h1><p>故障注入已开启：{notice_no} 暂时不可用。</p>",
            status_code=500,
        )
    a = get_by_notice_no(notice_no)
    if a is None:
        return HTMLResponse(f"<h1>404 公告不存在：{notice_no}</h1>", status_code=404)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"a": {**a, "type_label": TYPE_LABELS[a["type"]]}, "fail_on": FAIL_STATE["on"]},
    )


@app.get("/transfer/list.html", response_class=HTMLResponse)
def transfer_list_page(request: Request, page: int = 1):
    """交接目录页：交接记录链接 ul.transfer-list a[href]，分页 nav.pagination a[href]。"""
    items_all = sorted_transfer_records()
    total_pages = max(1, (len(items_all) + TRANSFER_PAGE_SIZE - 1) // TRANSFER_PAGE_SIZE)
    if page < 1 or page > total_pages:
        return HTMLResponse("<h1>404 页码不存在</h1>", status_code=404)
    start = (page - 1) * TRANSFER_PAGE_SIZE
    items = [
        {**r, "seal_label": SEAL_LABELS[r["seal_status"]]}
        for r in items_all[start : start + TRANSFER_PAGE_SIZE]
    ]
    return templates.TemplateResponse(
        request,
        "transfer_list.html",
        {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "pages": list(range(1, total_pages + 1)),
            "fail_on": FAIL_STATE["on"],
            "fail_transfer_record": FAIL_TRANSFER_RECORD,
        },
    )


@app.get("/transfer/detail/{record_no}.html", response_class=HTMLResponse)
def transfer_detail_page(request: Request, record_no: str):
    if FAIL_STATE["on"] and record_no == FAIL_TRANSFER_RECORD:
        return HTMLResponse(
            f"<h1>500 Internal Server Error</h1><p>故障注入已开启：交接记录 {record_no} 暂时不可用。</p>",
            status_code=500,
        )
    versions = get_transfer_record_versions(record_no)
    if not versions:
        return HTMLResponse(f"<h1>404 交接记录不存在：{record_no}</h1>", status_code=404)
    records = [
        {**r, "seal_label": SEAL_LABELS[r["seal_status"]]}
        for r in versions
    ]
    return templates.TemplateResponse(
        request,
        "transfer_detail.html",
        {
            "record_no": record_no,
            "records": records,
            "conflict": len(records) > 1,
        },
    )


@app.get("/admin/fail", response_class=HTMLResponse)
def admin_fail(on: int = 0):
    FAIL_STATE["on"] = bool(on)
    state = "已开启" if FAIL_STATE["on"] else "已关闭"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>故障注入</title></head>
<body>
<h1>故障注入{state}</h1>
<p>开启后，公告详情页 <code>/detail/{FAIL_NOTICE}.html</code> 与交接详情页
<code>/transfer/detail/{FAIL_TRANSFER_RECORD}.html</code> 将返回 500，用于验证采集端失败处理。</p>
<p><a href="/admin/fail?on=1">开启</a> · <a href="/admin/fail?on=0">关闭</a> ·
<a href="/list.html?page=1">公告列表</a> · <a href="/transfer/list.html?page=1">交接目录</a></p>
</body></html>"""


@app.get("/admin/status")
def admin_status():
    return {
        "fail_on": FAIL_STATE["on"],
        "fail_notice": FAIL_NOTICE,
        "fail_transfer_record": FAIL_TRANSFER_RECORD,
        "announcements": len(ANNOUNCEMENTS),
        "transfer_records": len(sorted_transfer_records()),
    }
