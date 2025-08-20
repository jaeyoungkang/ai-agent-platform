#!/usr/bin/env python3
"""
AI Agent Platform - Authentication System with Google OAuth
단순한 세션 기반 사용자 인증 + 구글 OAuth 지원
"""

import uuid
import hashlib
import os
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import google.cloud.firestore as firestore
from google.oauth2 import id_token
from google.auth.transport import requests
import logging

# Initialize Firebase
db = firestore.Client()
logger = logging.getLogger(__name__)

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

class GoogleAuth:
    """Google OAuth 인증 관리자"""
    
    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
    async def verify_token(self, token: str) -> Optional[dict]:
        """Google OAuth ID 토큰 검증"""
        try:
            if not self.client_id:
                logger.warning("Google Client ID not configured")
                return None
                
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), self.client_id)
            
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            return {
                'user_id': idinfo['sub'],
                'email': idinfo['email'],
                'name': idinfo['name'],
                'picture': idinfo.get('picture', '')
            }
        except ValueError as e:
            logger.error(f"Token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in token verification: {e}")
            return None

class BetaUserManager:
    """베타 사용자 관리자"""
    
    def __init__(self):
        self.max_beta_users = 30
        
    async def get_beta_user_count(self) -> int:
        """현재 베타 사용자 수 조회"""
        try:
            users_ref = db.collection('users').where('is_beta_user', '==', True)
            count = 0
            for _ in users_ref.stream():
                count += 1
            return count
        except Exception as e:
            logger.error(f"Error getting beta user count: {e}")
            return 17  # 기본값
            
    async def can_register_beta_user(self) -> bool:
        """베타 사용자 등록 가능 여부"""
        count = await self.get_beta_user_count()
        return count < self.max_beta_users
        
    async def register_beta_user(self, google_user_info: dict) -> dict:
        """베타 사용자 등록"""
        try:
            if not await self.can_register_beta_user():
                raise Exception("Beta slots are full")
                
            user_id = google_user_info['user_id']
            
            # 이미 등록된 사용자인지 확인
            existing_user = await self.get_user_by_google_id(user_id)
            if existing_user:
                return existing_user
                
            # 새 베타 사용자 생성
            user_doc = {
                'user_id': user_id,
                'google_id': user_id,
                'email': google_user_info['email'],
                'name': google_user_info['name'],
                'picture': google_user_info.get('picture', ''),
                'signup_date': datetime.utcnow(),
                'is_beta_user': True,
                'onboarding_completed': False,
                'interests': [],
                'nickname': '',
                'user_type': 'beta',
                'is_active': True,
                'created_at': datetime.utcnow(),
                'last_accessed': datetime.utcnow()
            }
            
            db.collection('users').document(user_id).set(user_doc)
            logger.info(f"Registered new beta user: {user_id}")
            
            return user_doc
            
        except Exception as e:
            logger.error(f"Error registering beta user: {e}")
            raise
            
    async def get_user_by_google_id(self, google_id: str) -> Optional[dict]:
        """Google ID로 사용자 조회"""
        try:
            user_ref = db.collection('users').document(google_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                return user_doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by Google ID: {e}")
            return None
            
    async def complete_onboarding(self, user_id: str, onboarding_data: dict) -> bool:
        """온보딩 완료 처리"""
        try:
            user_ref = db.collection('users').document(user_id)
            
            # 먼저 기존 사용자 데이터 확인
            user_doc = user_ref.get()
            
            update_data = {
                'user_id': user_id,
                'interests': onboarding_data.get('interests', []),
                'nickname': onboarding_data.get('nickname', ''),
                'onboarding_completed': True,
                'onboarding_completed_at': datetime.utcnow(),
                'last_accessed': datetime.utcnow()
            }
            
            # 기존 데이터가 있으면 유지
            if user_doc.exists:
                existing_data = user_doc.to_dict()
                update_data.update({
                    'user_type': existing_data.get('user_type', 'guest'),
                    'is_beta_user': existing_data.get('is_beta_user', True),
                    'email': existing_data.get('email', ''),
                    'name': existing_data.get('name', ''),
                    'signup_date': existing_data.get('signup_date', datetime.utcnow())
                })
            else:
                # 새 사용자 기본 데이터
                update_data.update({
                    'user_type': 'guest',
                    'is_beta_user': True,
                    'email': '',
                    'name': '',
                    'signup_date': datetime.utcnow()
                })
            
            # merge=True로 문서가 없어도 생성하도록 함
            user_ref.set(update_data, merge=True)
            logger.info(f"Completed onboarding for user: {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error completing onboarding: {e}")
            return False
            
    async def get_user_profile(self, user_id: str) -> Optional[dict]:
        """사용자 프로필 조회"""
        try:
            user_ref = db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                return None
                
            user_data = user_doc.to_dict()
            
            # 마지막 접근 시간 업데이트
            user_ref.update({'last_accessed': datetime.utcnow()})
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return None

# 전역 인증 관리자 인스턴스
auth_manager = SimpleAuthManager()
google_auth = GoogleAuth()
beta_manager = BetaUserManager()