import asyncio, json, logging, os, sys, tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from app.auth import require_admin
from app.models import AppUser
from app.config import settings
from app.schemas import ImportResult

log = logging.getLogger("pubapp.import")
router = APIRouter(prefix="/api/import", tags=["import"])
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def _get_env() -> dict:
    env = os.environ.copy()
    env.update({
        "DB_HOST": settings.DB_HOST, "DB_PORT": str(settings.DB_PORT),
        "DB_NAME": settings.DB_NAME, "DB_USER": settings.DB_USER,
        "DB_PASSWORD": settings.DB_PASSWORD, "PYTHONUNBUFFERED": "1",
    })
    return env


def _check_script(script: Path):
    if not script.exists():
        raise HTTPException(500, f"Скрипт не найден: {script}")


async def _stream_script(script: Path, tmp_path: str):
    """Async generator: yields SSE lines from script stdout."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), tmp_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_get_env(),
    )
    try:
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            yield f"data: {json.dumps({'line': line})}\n\n"
    finally:
        await proc.wait()
        try: os.unlink(tmp_path)
        except OSError: pass
        yield f"data: {json.dumps({'done': True, 'code': proc.returncode})}\n\n"


@router.post("/xml/stream")
async def import_xml_stream(
    file: UploadFile = File(...),
    _: AppUser = Depends(require_admin),
):
    if not (file.filename or "").lower().endswith(".xml"):
        raise HTTPException(400, "Принимаются только .xml файлы")
    script = SCRIPTS_DIR / "import_from_xml.py"
    _check_script(script)
    content = await file.read()
    log.info(f"XML upload: {file.filename!r} {len(content)} bytes")
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="wb") as t:
        t.write(content); tmp_path = t.name
    return StreamingResponse(
        _stream_script(script, tmp_path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/json/stream")
async def import_json_stream(
    file: UploadFile = File(...),
    _: AppUser = Depends(require_admin),
):
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(400, "Принимаются только .json файлы")
    script = SCRIPTS_DIR / "import_from_json.py"
    _check_script(script)
    content = await file.read()
    log.info(f"JSON upload: {file.filename!r} {len(content)} bytes")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as t:
        t.write(content); tmp_path = t.name
    return StreamingResponse(
        _stream_script(script, tmp_path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
