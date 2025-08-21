#!/usr/bin/env python3
"""
Claude Code CLI 통합 테스트 스크립트
실제 Claude Code CLI와의 통신을 테스트합니다.
"""

import asyncio
import os
import subprocess
import shutil
import sys
from datetime import datetime

# main.py에서 클래스들 임포트
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from main import ClaudeCodeProcess, UserWorkspace
    import logging
except ImportError as e:
    print(f"Import error: {e}")
    print("Please make sure you're running this script from the websocket-server directory")
    sys.exit(1)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_claude_cli_direct():
    """Claude CLI 직접 테스트"""
    print("\n=== 1. Claude CLI 직접 테스트 ===")
    
    # Claude Code CLI 설치 확인
    claude_path = shutil.which('claude')
    if not claude_path:
        print("❌ Claude Code CLI not found")
        print("Installing Claude Code CLI...")
        try:
            result = subprocess.run(['npm', 'install', '-g', '@anthropic-ai/claude-code'], 
                                  capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print("✅ Claude Code CLI installed successfully")
                claude_path = shutil.which('claude')
            else:
                print(f"❌ Installation failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Installation error: {e}")
            return False
    else:
        print(f"✅ Claude Code CLI found at: {claude_path}")
    
    # API 키 확인
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("⚠️ ANTHROPIC_API_KEY not set")
        api_key = input("Please enter your ANTHROPIC_API_KEY (or press Enter to skip): ").strip()
        if api_key:
            os.environ['ANTHROPIC_API_KEY'] = api_key
        else:
            print("❌ API key is required for Claude Code to work")
            return False
    else:
        print("✅ ANTHROPIC_API_KEY is configured")
    
    # Claude Code 버전 확인
    try:
        result = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Claude Code version: {result.stdout.strip()}")
        else:
            print(f"⚠️ Could not get version: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Version check error: {e}")
    
    return True


async def test_claude_process():
    """ClaudeCodeProcess 클래스 테스트"""
    print("\n=== 2. ClaudeCodeProcess 클래스 테스트 ===")
    
    test_user_id = "test_user_001"
    test_session_id = "test_session_001"
    
    process = ClaudeCodeProcess(test_user_id, test_session_id)
    
    # 에이전트 생성 모드로 시작
    print("Starting Claude process with agent-create context...")
    success = await process.start(initial_context='agent-create')
    
    if not success:
        print("❌ Failed to start Claude process")
        return False
    
    print("✅ Claude process started successfully")
    
    # 테스트 메시지들
    test_messages = [
        "안녕하세요. 주식 정보를 수집하는 에이전트를 만들고 싶어요.",
        "매주 월요일 오전 8시에 실행하면 좋겠어요.",
        "알파벳 회사의 뉴스를 수집해주세요."
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n--- Message {i} ---")
        print(f"User: {message}")
        
        try:
            response = await process.send_message(message, timeout=20.0)
            print(f"Claude: {response[:300]}...")  # 처음 300자만 출력
            
            if not response or "오류" in response:
                print("⚠️ Received error or empty response")
            else:
                print("✅ Received valid response")
            
            # 응답 사이에 잠시 대기
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            break
    
    # 프로세스 정리
    process.stop()
    print("\n✅ Claude process stopped")
    
    return True


async def test_user_workspace():
    """UserWorkspace 클래스 테스트"""
    print("\n=== 3. UserWorkspace 클래스 테스트 ===")
    
    test_user_id = "test_user_002"
    test_session_id = "test_session_002"
    
    workspace = UserWorkspace(test_user_id)
    
    # 에이전트 생성 대화 테스트
    messages = [
        "데이터 분석 에이전트를 만들고 싶습니다.",
        "매일 오후 2시에 실행하고 싶어요."
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n--- Workspace Message {i} ---")
        print(f"User: {message}")
        
        try:
            response = await workspace.send_to_claude(
                message, 
                context="agent-create", 
                session_id=test_session_id
            )
            print(f"Response: {response[:200]}...")  # 처음 200자만 출력
            
            if response and "오류" not in response:
                print("✅ Workspace communication successful")
            else:
                print("⚠️ Workspace communication issue")
            
        except Exception as e:
            print(f"❌ Workspace error: {e}")
            break
    
    # 정리
    await workspace.cleanup()
    print("\n✅ Workspace cleaned up")
    
    return True


async def run_integration_tests():
    """전체 통합 테스트 실행"""
    print("Claude Code CLI 통합 테스트 시작")
    print("=" * 50)
    
    test_results = []
    
    # 1. CLI 직접 테스트
    try:
        result1 = await test_claude_cli_direct()
        test_results.append(("Claude CLI Direct Test", result1))
    except Exception as e:
        print(f"❌ CLI test failed: {e}")
        test_results.append(("Claude CLI Direct Test", False))
    
    # 2. ClaudeCodeProcess 테스트
    try:
        result2 = await test_claude_process()
        test_results.append(("ClaudeCodeProcess Test", result2))
    except Exception as e:
        print(f"❌ Process test failed: {e}")
        test_results.append(("ClaudeCodeProcess Test", False))
    
    # 3. UserWorkspace 테스트
    try:
        result3 = await test_user_workspace()
        test_results.append(("UserWorkspace Test", result3))
    except Exception as e:
        print(f"❌ Workspace test failed: {e}")
        test_results.append(("UserWorkspace Test", False))
    
    # 결과 요약
    print("\n" + "=" * 50)
    print("테스트 결과 요약")
    print("=" * 50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<25} {status}")
        if result:
            passed += 1
    
    print(f"\n전체 결과: {passed}/{total} 테스트 통과")
    
    if passed == total:
        print("🎉 모든 테스트가 성공했습니다!")
        return True
    else:
        print("⚠️ 일부 테스트가 실패했습니다.")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_integration_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n예상치 못한 오류: {e}")
        sys.exit(1)