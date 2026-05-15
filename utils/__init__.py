"""Utilities package for Rite Audit System."""

def get_llm():
    from utils.llm import get_llm as _get_llm
    return _get_llm()

def get_vision_llm():
    from utils.llm import get_vision_llm as _f
    return _f()

def get_voucher_llm():
    from utils.llm import get_voucher_llm as _f
    return _f()

def get_db(db_path: str = "claims.db"):
    from utils.db import get_db as _get_db
    return _get_db(db_path)

__all__ = ["get_llm", "get_vision_llm", "get_voucher_llm", "get_db"]

