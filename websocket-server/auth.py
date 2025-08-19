#!/usr/bin/env python3
"""
AI Agent Platform - Simple Authentication System
단순한 세션 기반 사용자 인증
"""

import uuid
import hashlib
from typing import Dict, Optional
from datetime import datetime, timedelta
import google.cloud.firestore as firestore

# Initialize Firebase
db = firestore.Client()

class SimpleAuthManager:
    """단순한 세션 기반 인증 관리자"""
    
    def __init__(self):
        self.active_sessions: Dict[str, dict] = {}
        self.session_timeout = timedelta(hours=24)  # 24시간 세션
    
    async def create_guest_session(self, user_agent: str = "") -> dict:
        """게스트 세션 생성"""
        user_id = f"guest-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "user_type": "guest",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + self.session_timeout,
            "user_agent": user_agent,
            "is_active": True
        }
        
        # 메모리에 세션 저장
        self.active_sessions[session_id] = session_data
        
        # Firestore에 사용자 정보 저장
        await self._save_user_to_firestore(user_id, session_data)
        
        return {
            "session_id": session_id,
            "user_id": user_id,
            "user_type": "guest",
            "expires_at": session_data["expires_at"].isoformat()
        }
    
    async def validate_session(self, session_id: str) -> Optional[dict]:
        """세션 유효성 검사"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # 세션 만료 확인
        if datetime.utcnow() > session["expires_at"]:
            await self._cleanup_session(session_id)
            return None
        
        # 세션 갱신
        session["last_accessed"] = datetime.utcnow()
        return session
    
    async def get_user_id_from_session(self, session_id: str) -> Optional[str]:
        """세션으로부터 사용자 ID 추출"""
        session = await self.validate_session(session_id)
        return session["user_id"] if session else None
    
    async def cleanup_expired_sessions(self):
        """만료된 세션 정리"""
        current_time = datetime.utcnow()
        expired_sessions = [
            sid for sid, session in self.active_sessions.items()
            if current_time > session["expires_at"]
        ]
        
        for session_id in expired_sessions:
            await self._cleanup_session(session_id)
    
    async def _cleanup_session(self, session_id: str):
        """세션 정리"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
    
    async def _save_user_to_firestore(self, user_id: str, session_data: dict):
        """Firestore에 사용자 정보 저장"""
        try:
            user_ref = db.collection('users').document(user_id)
            user_data = {
                'userId': user_id,
                'userType': session_data['user_type'],
                'createdAt': session_data['created_at'],
                'lastAccessed': session_data['created_at'],
                'userAgent': session_data['user_agent'],
                'isActive': True
            }
            user_ref.set(user_data)
        except Exception as e:
            print(f"Error saving user to Firestore: {e}")

# 전역 인증 관리자 인스턴스
auth_manager = SimpleAuthManager()