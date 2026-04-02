"""
doc_converter.py — 문서 변환 BackgroundTask 서비스

asyncio.Lock으로 변환 작업을 직렬화하여 GPU OOM을 방지한다.
작업 상태는 Django 내부 API(callback_token) 를 통해 업데이트한다.
"""

import asyncio
import logging
import pathlib
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 변환을 직렬화하는 전역 Lock — GPU OOM 방지, 한 번에 하나씩만 변환
_conversion_lock = asyncio.Lock()

DJANGO_BASE_URL = "http://127.0.0.1:8000"


async def _update_job_status(
    http_client: httpx.AsyncClient,
    callback_token: str,
    new_status: str,
    error_message: Optional[str] = None,
    internal_secret: str = "",
) -> None:
    """Django callback 엔드포인트로 job 상태를 업데이트한다."""
    payload: dict = {"status": new_status}
    if error_message:
        payload["error_message"] = error_message[:500]

    url = f"{DJANGO_BASE_URL}/api/doc-uploader/jobs/callback/{callback_token}/"
    try:
        resp = await http_client.patch(
            url,
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Job status update failed (token=%s, status=%s): %s", callback_token, new_status, exc)


async def run_converter_subprocess(
    python_exe: pathlib.Path,
    script_path: pathlib.Path,
    input_file: pathlib.Path,
    output_dir: pathlib.Path,
    extra_args: Optional[list] = None,
) -> tuple[int, str]:
    """
    변환 스크립트를 서브프로세스로 실행한다.

    Returns:
        (returncode, stderr_text)
    """
    cmd = [
        str(python_exe),
        str(script_path),
        "--input-file", str(input_file),
        "--output", str(output_dir),
    ]
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Running subprocess: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if stdout_text:
        logger.info("Converter stdout:\n%s", stdout_text)
    if stderr_text:
        # marker/markitdown은 WARNING 등을 stderr에 출력하므로 info 레벨로 기록
        logger.info("Converter stderr:\n%s", stderr_text)

    return proc.returncode, stderr_text


async def process_conversion_job(
    http_client: httpx.AsyncClient,
    callback_token: str,
    temp_file: pathlib.Path,
    category: str,
    original_filename: str,
    dev_marker_dir: pathlib.Path,
    doc_data_dir: pathlib.Path,
    internal_secret: str,
    force_ocr: bool = False,
) -> None:
    """
    BackgroundTask 진입점.

    흐름:
      Lock 대기 → working → subprocess 변환 → 결과 검증 → completed / failed → 임시파일 삭제
    """
    file_ext = pathlib.Path(original_filename).suffix.lower()
    stem = pathlib.Path(original_filename).stem
    output_dir = doc_data_dir / category

    async with _conversion_lock:
        # 변환 시작: working 상태로 업데이트
        await _update_job_status(
            http_client, callback_token, "working", internal_secret=internal_secret
        )

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            python_exe = dev_marker_dir / ".venv" / "Scripts" / "python.exe"
            if not python_exe.exists():
                raise FileNotFoundError(
                    f"dev_marker venv Python not found: {python_exe}\n"
                    "dev_marker 프로젝트에서 setup.bat을 먼저 실행하세요."
                )

            if file_ext == ".pdf":
                script = dev_marker_dir / "convert_pdf.py"
                extra_args = ["--force-ocr"] if force_ocr else []
                rc, stderr = await run_converter_subprocess(
                    python_exe, script, temp_file, output_dir, extra_args
                )
            elif file_ext in (".doc", ".docx", ".pptx", ".ppt", ".xlsx", ".xls"):
                script = dev_marker_dir / "convert_office.py"
                rc, stderr = await run_converter_subprocess(
                    python_exe, script, temp_file, output_dir
                )
            else:
                raise ValueError(f"지원하지 않는 파일 형식: {file_ext}")

            if rc != 0:
                raise RuntimeError(
                    f"변환 프로세스가 종료 코드 {rc}로 실패했습니다.\n{stderr[:400]}"
                )

            # 변환기는 temp_file stem을 출력 파일명으로 사용 (UUID 접두사 포함)
            # 예: b1b543e6_원본파일명.md → 원본파일명.md 으로 rename
            temp_md_file = output_dir / f"{temp_file.stem}.md"
            if not temp_md_file.exists():
                raise FileNotFoundError(
                    f"변환 결과 파일을 찾을 수 없습니다: {temp_md_file}"
                )

            # 원본 파일명 기반으로 rename (UUID 접두사 제거)
            final_md_file = output_dir / f"{stem}.md"
            if final_md_file.exists():
                # 동일 이름 충돌 시 기존 파일 덮어쓰기 (재업로드 업데이트 허용)
                final_md_file.unlink()
            temp_md_file.rename(final_md_file)

            await _update_job_status(
                http_client, callback_token, "completed", internal_secret=internal_secret
            )
            logger.info("Conversion completed: %s → %s", original_filename, final_md_file)

        except Exception as exc:
            error_msg = str(exc)[:500]
            logger.error("Conversion failed [%s]: %s", original_filename, exc)
            await _update_job_status(
                http_client, callback_token, "failed",
                error_message=error_msg,
                internal_secret=internal_secret,
            )

        finally:
            # 임시 파일 정리
            try:
                temp_file.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                logger.warning("Temp file delete failed (%s): %s", temp_file, cleanup_exc)
