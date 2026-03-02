from fastapi import Header, HTTPException
from fastapi.concurrency import run_in_threadpool
import sqlite3
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to Django DB
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "django_server" / "db.sqlite3"

async def verify_token(authorization: str = Header(None)):
    """
    Django DB의 authtoken_token 테이블을 조회하여 토큰 유효성 검증
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        parts = authorization.split()
        if len(parts) != 2:
            raise HTTPException(status_code=401, detail="Invalid Authorization Header Format")
            
        scheme, token = parts
        if scheme.lower() != 'token':
            raise HTTPException(status_code=401, detail="Invalid Authorization Scheme")
            
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Authorization Header")
        
    if not os.path.exists(DB_PATH):
        logger.error(f"Authentication DB not found at {DB_PATH}")
        # DB가 없으면 인증을 할 수 없음 (보안상 거부)
        raise HTTPException(status_code=500, detail="Authentication System Unavailable")
        
    # Blocking DB Operation
    is_valid = await run_in_threadpool(_check_token_in_db, token)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid Token")
        
    return token

def _check_token_in_db(token: str) -> bool:
    try:
        # Read-only connection
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM authtoken_token WHERE key = ?", (token,))
        row = cursor.fetchone()
        conn.close()
        return bool(row)
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return False
