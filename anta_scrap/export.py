"""异步导出三步走：trigger → poll → download（仅 CSV）。

HAR 验证：
  POST /api/write/file/{cardId}?typeOp=CSV  body=查询体  → {taskId, status:PROCESSING}
  GET  /api/task/{taskId}                   → {response: {status: PROCESSING|SUCCESS|FAILED, ...}}
  POST /api/export/file/common/{taskId}
       body={downloadFileName, time, fileNameWithTime}  → 二进制流
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from anta_scrap.client import AntaAPIError, AntaClient
from anta_scrap.models import QueryParams
from anta_scrap.reports.base import BaseReport

EXPORT_CSV = "CSV"

_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 300.0


def trigger_export(report: BaseReport, params: QueryParams) -> str:
    """触发 CSV 导出，返回 taskId。"""
    payload = report.build_payload(params)
    client: AntaClient = report.client
    # 注意：trigger 接口要直接拿原始 JSON（不走 _check_ok），因为响应结构是
    #   {result:"ok", response:{taskId, status, fileName, postBody}}
    resp = client.post_json(
        f"/api/write/file/{report.card_id}",
        params={"typeOp": EXPORT_CSV},
        body=payload,
        headers={
            "raw-backend-response": "TRUE",
            "referer": f"https://datav.anta.com/page/{report.page_id}",
        },
    )
    data = resp.json()
    task_id = data.get("taskId") or (data.get("response") or {}).get("taskId")
    if not task_id:
        raise AntaAPIError(f"导出未返回 taskId: {data}")
    return task_id


def poll_task(client: AntaClient, task_id: str, *, interval: float = _POLL_INTERVAL, timeout: float = _POLL_TIMEOUT) -> str:
    """轮询任务直到完成，返回最终 status。

    兼容两种响应：
      - 带 raw-backend-response 头：{result:"ok", response:{status,...}}
      - 不带头：{taskId, status, ...}（status 在顶层）
    """
    import time

    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        data = client.get_json(f"/api/task/{task_id}")
        # 优先取 response.status，回退到顶层 status
        if isinstance(data, dict):
            inner = data.get("response")
            if isinstance(inner, dict):
                status = inner.get("status", "")
            else:
                status = data.get("status", "")
        else:
            status = ""
        last_status = status
        if status and status != "PROCESSING":
            return status
        time.sleep(interval)
    raise AntaAPIError(f"导出任务 {task_id} 轮询超时（{timeout}s），最后状态: {last_status}")


def download(
    client: AntaClient,
    task_id: str,
    download_file_name: str,
    *,
    time_str: Optional[str] = None,
    file_name_with_time: bool = True,
) -> tuple:
    """触发下载，返回 (bytes, resolved_filename)。"""
    if time_str is None:
        time_str = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000+08:00")
    body = {
        "downloadFileName": download_file_name,
        "time": time_str,
        "fileNameWithTime": file_name_with_time,
    }
    # 注意：此接口返回二进制流，不能用 post_json_ok（它要求 JSON）
    resp = client.post_json(
        f"/api/export/file/common/{task_id}",
        body=body,
    )
    if resp.status_code != 200:
        raise AntaAPIError(f"下载失败: {resp.status_code} {resp.text[:200]}")
    disp = resp.headers.get("content-disposition", "")
    resolved = _parse_filename(disp) or f"{download_file_name}.bin"
    return resp.content, resolved


def export_csv(
    report: BaseReport,
    params: QueryParams,
    out_dir: Path,
    download_file_name: Optional[str] = None,
) -> Path:
    """完整三步走导出 CSV，落盘到 out_dir，返回写入的文件路径。"""
    client: AntaClient = report.client
    name = download_file_name or params.card_name or report.name
    task_id = trigger_export(report, params)
    status = poll_task(client, task_id)
    if status not in ("SUCCESS", "SUCCESSFUL", "OK", "DONE", "FINISHED"):
        # 有些后端用非标准状态名，拿到文件流就算成功；这里只在明确失败时报错
        if status in ("FAILED", "ERROR", "FAILURE"):
            raise AntaAPIError(f"导出任务失败: status={status}")

    content, resolved = download(client, task_id, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Windows 文件名不能含 \ / : * ? " < > |，统一替换为 _
    import re
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", resolved).strip()
    out_path = out_dir / safe_name
    out_path.write_bytes(content)
    return out_path


def _parse_filename(disp: str) -> Optional[str]:
    """从 content-disposition 抠 filename*（RFC 5987）或 filename。"""
    if not disp:
        return None
    import re

    m = re.search(r"filename\*\s*=\s*([^;]+)", disp)
    if m:
        raw = m.group(1).strip().strip('"')
        if raw.startswith("UTF-8''") or raw.startswith("utf-8''"):
            return unquote(raw.split("''", 1)[1])
        return unquote(raw)
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', disp)
    if m:
        return unquote(m.group(1))
    return None
