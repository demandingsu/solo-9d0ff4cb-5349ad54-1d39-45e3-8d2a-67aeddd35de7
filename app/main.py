"""评标秘书核对工具（FastAPI 网页）。

两个核对能力：
- 截标时间核对（/）：输入公告列表网址，抓取同源分页与全部详情页，按项目串起
  公告链，给出每个项目的最终截标时间与状态，采集轮次存入 SQLite。
- 样品交接核对（/transfer）：输入交接目录网址、标段号、样品编号与核对时刻，
  抓取同源入库/交接详情，按前序编号还原唯一交接链，判定样品能否交付评审室。
"""

import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import analysis
import db
import scraper
import transfer_analysis
import transfer_scraper

DEFAULT_START_URL = os.environ.get("DEFAULT_START_URL", "http://sample-site:8000/list.html?page=1")
DEFAULT_TRANSFER_URL = os.environ.get(
    "DEFAULT_TRANSFER_URL", "http://sample-site:8000/transfer/list.html?page=1"
)
# 展示层网址改写：容器内部地址 → 浏览器可访问地址（可选）
URL_REWRITE_FROM = os.environ.get("URL_REWRITE_FROM", "")
URL_REWRITE_TO = os.environ.get("URL_REWRITE_TO", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="截标时间核对工具", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


def public_url(url: str) -> str:
    """把采集用的内部网址改写成浏览器可访问的网址（未配置时原样返回）。"""
    if URL_REWRITE_FROM and URL_REWRITE_TO and url.startswith(URL_REWRITE_FROM):
        return URL_REWRITE_TO + url[len(URL_REWRITE_FROM) :]
    return url


templates.env.filters["public_url"] = public_url


@app.get("/", response_class=HTMLResponse)
def index(request: Request, msg: str = ""):
    rounds = db.get_rounds()
    latest_ok = db.get_latest_success_round()
    projects = None
    if latest_ok is not None:
        projects = analysis.build_projects(db.get_announcements(latest_ok["id"]))
    last_round = rounds[0] if rounds else None
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_start_url": DEFAULT_START_URL,
            "msg": msg,
            "last_round": last_round,
            "latest_ok": latest_ok,
            "projects": projects,
            "rounds": rounds,
        },
    )


@app.post("/scrape")
def do_scrape(start_url: str = Form(...)):
    start_url = start_url.strip()
    round_id = db.create_round(start_url)
    try:
        result = scraper.scrape(start_url)
    except scraper.ScrapeError as exc:
        # 任一页面失败：记录出错网址，本轮不产生数据，页面仍展示上一轮结果
        db.finish_round_failed(round_id, exc.url, exc.message)
        msg = f"第 {round_id} 轮抓取失败：{exc.url}（{exc.message}）。已保留上一轮结果。"
        return RedirectResponse(f"/?msg={quote(msg)}", status_code=303)
    except Exception as exc:  # 兜底，避免未预期异常丢轮次
        db.finish_round_failed(round_id, start_url, f"未预期错误：{exc!r}")
        msg = f"第 {round_id} 轮抓取失败：{start_url}（{exc!r}）。已保留上一轮结果。"
        return RedirectResponse(f"/?msg={quote(msg)}", status_code=303)

    db.finish_round_success(round_id, result.announcements, len(result.list_pages), len(result.detail_pages))
    msg = (
        f"第 {round_id} 轮抓取成功：{len(result.list_pages)} 个列表页、"
        f"{len(result.detail_pages)} 个详情页，共 {len(result.announcements)} 条公告。"
    )
    return RedirectResponse(f"/?msg={quote(msg)}", status_code=303)


# ---------------------------------------------------------------------------
# 投标样品交接核对
# ---------------------------------------------------------------------------


@app.get("/transfer", response_class=HTMLResponse)
def transfer_page(request: Request):
    return templates.TemplateResponse(
        request,
        "transfer.html",
        {
            "default_transfer_url": DEFAULT_TRANSFER_URL,
            "form": None,
            "result": None,
            "scrape_error": None,
        },
    )


@app.post("/transfer/check", response_class=HTMLResponse)
def transfer_check(
    request: Request,
    catalog_url: str = Form(...),
    section_no: str = Form(...),
    sample_no: str = Form(...),
    cutoff_time: str = Form(...),
):
    form = {
        "catalog_url": catalog_url.strip(),
        "section_no": section_no.strip(),
        "sample_no": sample_no.strip(),
        "cutoff_time": cutoff_time.strip(),
    }
    base_ctx = {"default_transfer_url": DEFAULT_TRANSFER_URL, "form": form, "result": None}

    try:
        transfer_analysis.parse_cutoff(form["cutoff_time"])
    except transfer_analysis.CutoffTimeError as exc:
        return templates.TemplateResponse(
            request,
            "transfer.html",
            {**base_ctx, "scrape_error": str(exc)},
        )

    try:
        scraped = transfer_scraper.scrape_transfer(form["catalog_url"])
    except transfer_scraper.ScrapeError as exc:
        # 目录页本身抓取失败：整次核对无法进行，列出问题网址
        return templates.TemplateResponse(
            request,
            "transfer.html",
            {**base_ctx, "scrape_error": f"交接目录抓取失败：{exc.url}（{exc.message}）"},
        )

    result = transfer_analysis.analyze_transfer(
        scraped.records,
        scraped.failed_pages,
        form["section_no"],
        form["sample_no"],
        form["cutoff_time"],
    )
    result["list_pages"] = scraped.list_pages
    result["detail_pages"] = scraped.detail_pages
    result["failed_pages"] = [{"url": f.url, "message": f.message} for f in scraped.failed_pages]
    return templates.TemplateResponse(
        request,
        "transfer.html",
        {**base_ctx, "result": result, "scrape_error": None},
    )
