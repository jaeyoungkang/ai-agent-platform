#!/usr/bin/env python3
"""
Email Service for AI Agent Platform
Google Workspace SMTP를 사용한 이메일 발송 서비스
"""

import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class EmailService:
    """Google Workspace SMTP를 사용한 이메일 발송 서비스"""
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.username = os.getenv('SMTP_USERNAME')
        self.password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL')
        self.apply_receive_email = os.getenv('APPLY_RECEIVE_EMAIL')
        
        if not all([self.username, self.password, self.from_email, self.apply_receive_email]):
            logger.warning("이메일 환경변수가 설정되지 않았습니다.")
    
    def _send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """실제 이메일 발송 처리"""
        try:
            # 이메일 메시지 생성
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # HTML 콘텐츠 추가
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # SMTP 서버 연결 및 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"이메일 발송 성공: {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"이메일 발송 실패 ({to_email}): {e}")
            return False
    
    async def send_beta_application_notification(self, user_data: Dict[str, Any]) -> bool:
        """관리자에게 베타 신청 알림 이메일 발송"""
        
        subject = f"[AI Agent Platform] 새로운 베타 신청 - {user_data.get('name', '이름 없음')}"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>베타 신청 알림</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background: #f9f9f9; }}
        .info-box {{ background: white; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #667eea; }}
        .approval-box {{ background: #e3f2fd; padding: 15px; margin: 20px 0; border-radius: 8px; }}
        .button {{ background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🚀 새로운 베타 테스터 신청</h2>
        </div>
        
        <div class="content">
            <div class="info-box">
                <h3>신청자 정보</h3>
                <p><strong>이름:</strong> {user_data.get('name', 'N/A')}</p>
                <p><strong>이메일:</strong> {user_data.get('email', 'N/A')}</p>
                <p><strong>회사/조직:</strong> {user_data.get('company', 'N/A')}</p>
                <p><strong>신청일:</strong> {user_data.get('applied_at', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))}</p>
            </div>
            
            <div class="info-box">
                <h3>AI 에이전트 활용 계획</h3>
                <p>{user_data.get('use_case', 'N/A')}</p>
            </div>
            
            <div class="info-box">
                <h3>AI/자동화 경험 수준</h3>
                <p>{user_data.get('experience', 'N/A')}</p>
            </div>
            
            <div class="approval-box">
                <h3>🔧 승인 방법</h3>
                <p>Firestore Console에서 다음 작업을 수행하세요:</p>
                <ol>
                    <li><strong>whitelist</strong> 컬렉션에 이메일 추가</li>
                    <li><strong>status: "active"</strong>로 설정</li>
                    <li>승인 이메일이 자동 발송됩니다</li>
                </ol>
                <p><a href="https://console.firebase.google.com" class="button">Firestore Console 바로가기</a></p>
            </div>
            
            <hr style="margin: 30px 0;">
            <p style="color: #666; font-size: 12px;">
                AI Agent Platform 자동 알림<br>
                이 이메일은 발신 전용입니다.
            </p>
        </div>
    </div>
</body>
</html>
"""
        
        return self._send_email(self.apply_receive_email, subject, html_content)
    
    async def send_application_confirmation(self, user_email: str, user_name: str, applied_at: str) -> bool:
        """신청자에게 접수 확인 이메일 발송"""
        
        subject = "[AI Agent Platform] 베타 참여 신청이 접수되었습니다"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>베타 신청 접수 확인</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .info-box {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .next-steps {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .button {{ background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; }}
        .footer {{ border-top: 1px solid #eee; margin: 30px 0; padding: 15px 0; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>✅ AI Agent Platform 베타 신청 접수 완료</h2>
        </div>
        
        <div class="content">
            <p>안녕하세요, <strong>{user_name}</strong>님!</p>
            
            <p>AI Agent Platform 베타 참여 신청이 성공적으로 접수되었습니다.</p>
            
            <div class="info-box">
                <h3>신청 정보</h3>
                <p><strong>이메일:</strong> {user_email}</p>
                <p><strong>신청일:</strong> {applied_at}</p>
                <p><strong>상태:</strong> 검토 중</p>
            </div>
            
            <div class="next-steps">
                <h3>📋 다음 단계</h3>
                <ol>
                    <li><strong>검토 과정</strong>: 1-2일 내 신청 내용을 검토합니다</li>
                    <li><strong>승인 알림</strong>: 승인 시 별도 이메일로 안내드립니다</li>
                    <li><strong>서비스 이용</strong>: 승인 후 Google 계정으로 로그인하여 바로 이용 가능합니다</li>
                </ol>
            </div>
            
            <p>궁금한 점이 있으시면 언제든 문의해주세요.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://oh-my-agent.info" class="button">
                    서비스 바로가기
                </a>
            </div>
            
            <div class="footer">
                AI Agent Platform Team<br>
                이 이메일은 발신 전용입니다.
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        return self._send_email(user_email, subject, html_content)
    
    async def send_approval_notification(self, user_email: str, user_name: str) -> bool:
        """승인 완료 이메일 발송"""
        
        subject = "[AI Agent Platform] 🎉 베타 참여가 승인되었습니다!"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>베타 참여 승인</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #28a745; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .success-box {{ background: #d4edda; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .guide-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .button {{ background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-size: 18px; display: inline-block; }}
        .footer {{ border-top: 1px solid #eee; margin: 30px 0; padding: 15px 0; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🎉 베타 참여 승인 완료!</h2>
        </div>
        
        <div class="content">
            <p>축하합니다, <strong>{user_name}</strong>님!</p>
            
            <p>AI Agent Platform 베타 테스터로 승인되었습니다. 지금 바로 서비스를 이용하실 수 있습니다.</p>
            
            <div class="success-box">
                <h3>🚀 시작하기</h3>
                <ol>
                    <li><strong>로그인</strong>: 아래 버튼을 클릭하여 사이트에 접속하세요</li>
                    <li><strong>Google 계정 연결</strong>: 승인된 이메일({user_email})로 Google 로그인</li>
                    <li><strong>온보딩 완료</strong>: 간단한 설정 후 바로 이용 가능</li>
                </ol>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://oh-my-agent.info" class="button">
                    🚀 지금 시작하기
                </a>
            </div>
            
            <div class="guide-box">
                <h3>📋 베타 테스터 안내사항</h3>
                <ul>
                    <li>서비스 이용 중 발견한 버그나 개선사항을 공유해주세요</li>
                    <li>최소 4주간 활용해보시고 피드백을 제공해주세요</li>
                    <li>베타 기간 중 모든 기능을 무료로 이용하실 수 있습니다</li>
                </ul>
            </div>
            
            <p>훌륭한 AI 에이전트 개발 경험을 만들어보세요!</p>
            
            <div class="footer">
                AI Agent Platform Team<br>
                문의사항: support@youngcompany.kr
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        return self._send_email(user_email, subject, html_content)

# 전역 이메일 서비스 인스턴스
email_service = EmailService()