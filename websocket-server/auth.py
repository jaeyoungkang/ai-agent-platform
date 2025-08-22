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

# SimpleAuthManager 클래스 제거됨 - Google OAuth만 사용

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

# 전역 인증 관리자 인스턴스 (SimpleAuthManager 제거됨)
google_auth = GoogleAuth()
beta_manager = BetaUserManager()