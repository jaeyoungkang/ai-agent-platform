"""
Claude Code 빠른 초기화 모듈
이미 설치된 Claude Code를 검증만 하는 최소한의 로직
"""

import os
import subprocess
import logging
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

class FastClaudeInitializer:
    """빠른 Claude Code 초기화"""
    
    def __init__(self):
        self.claude_path: Optional[str] = None
        self.is_ready: bool = False
        
    def initialize(self) -> bool:
        """Claude Code 빠른 검증 (이미 설치되어 있다고 가정)"""
        
        # 1. Claude 경로 확인
        self.claude_path = shutil.which('claude')
        if not self.claude_path:
            logger.error("FATAL: Claude Code not found in PATH")
            logger.error("Docker image should have Claude Code pre-installed")
            return False
        
        logger.info(f"Claude Code found at: {self.claude_path}")
        
        # 2. API 키 확인
        if not os.environ.get('ANTHROPIC_API_KEY'):
            logger.error("FATAL: ANTHROPIC_API_KEY not set")
            return False
        
        # 3. 간단한 버전 체크 (옵션)
        try:
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=2  # 2초 타임아웃
            )
            if result.returncode == 0:
                logger.info(f"Claude version: {result.stdout.strip()}")
        except:
            pass  # 버전 체크 실패해도 무시
        
        self.is_ready = True
        logger.info("Claude Code ready (fast init)")
        return True
    
    def get_status(self) -> dict:
        return {
            'ready': self.is_ready,
            'claude_path': self.claude_path,
            'api_key_set': bool(os.environ.get('ANTHROPIC_API_KEY'))
        }

# 싱글톤
claude_init = FastClaudeInitializer()

def ensure_claude_ready() -> bool:
    """Claude Code 준비 확인"""
    if not claude_init.is_ready:
        return claude_init.initialize()
    return True

def get_claude_status() -> dict:
    """Claude Code 상태"""
    return claude_init.get_status()