# core/orchestrators/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any
import uuid
import logging
from core.utils.result import Result

logger = logging.getLogger(__name__)


class BaseOrchestrator(ABC):
    """Базов клас за всички оркестратори"""

    def generate_workflow_id(self) -> str:
        """Генерира уникален ID за workflow"""
        return f"WF-{uuid.uuid4().hex[:8]}"

    @abstractmethod
    def execute(self, *args, **kwargs) -> Result:
        """Всеки оркестратор трябва да имплементира execute"""
        pass

    def log_step(self, workflow_id: str, step: str, status: str):
        """Логва стъпка от workflow"""
        logger.info(f"[{workflow_id}] Step: {step} - Status: {status}")