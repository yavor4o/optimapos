# core/utils/result.py
from typing import Any, Optional, Dict
from dataclasses import dataclass


@dataclass
class Result:
    """
    Унифициран response за всички services
    Използва се навсякъде вместо exceptions
    """
    ok: bool
    code: str = 'SUCCESS'
    msg: str = ''
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, data=None, msg='Operation successful'):
        return cls(ok=True, code='SUCCESS', msg=msg, data=data or {})

    @classmethod
    def error(cls, code: str, msg: str, data=None):
        return cls(ok=False, code=code, msg=msg, data=data or {})