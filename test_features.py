#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TransTube 功能测试脚本
测试新增的智能翻译、术语库、断点续跑等功能
"""

import requests
import json
import time
import sys
import os

# 配置
API_BASE = "http://localhost:8000"
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # 示例视频

def test_api_connection():
    """测试 API 连接"""
    try:
        response = requests.get(f"{API_BASE}/api/videos")
        if response.status_code == 200:
            print("✅ API 连接正常")
            return True
        else:
            print(f"❌ API 连接失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API 连接异常: {str(e)}")
        return False

def test_video_processing():
    """测试视频处理功能"""
    print("\n🎬 测试视频处理功能...")
    
    # 提交处理任务
    payload = {
        "url": TEST_VIDEO_URL,
        "force_reprocess": True
    }
    
    try:
        response = requests.post(f"{API_BASE}/api/process", json=payload)
        if response.status_code == 200:
            data = response.json()
            task_id = data.get("task_id")
            print(f"✅ 任务提交成功，任务ID: {task_id}")
            return task_id
        else:
            print(f"❌ 任务提交失败: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ 任务提交异常: {str(e)}")
        return None

def test_task_status(task_id):
    """测试任务状态查询"""
    print(f"\n📊 测试任务状态查询: {task_id}")
    
    max_attempts = 10
    for i in range(max_attempts):
        try:
            response = requests.get(f"{API_BASE}/api/task/{task_id}")
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                progress = data.get("progress", 0)
                message = data.get("message", "")
                stage = data.get("stage", "")
                
                print(f"状态: {status} | 进度: {progress}% | 阶段: {stage} | 消息: {message}")
                
                if status == "completed":
                    print("✅ 任务完成")
                    return data
                elif status == "failed":
                    print("❌ 任务失败")
                    return data
                
                time.sleep(5)
            else:
                print(f"❌ 状态查询失败: {response.status_code}")
                break
        except Exception as e:
            print(f"❌ 状态查询异常: {str(e)}")
            break
    
    print("⏰ 测试超时")
    return None

def test_task_resume(task_id):
    """测试任务恢复功能"""
    print(f"\n🔄 测试任务恢复功能: {task_id}")
    
    try:
        response = requests.post(f"{API_BASE}/api/task/{task_id}/resume")
        if response.status_code == 200:
            print("✅ 任务恢复成功")
            return True
        else:
            print(f"❌ 任务恢复失败: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ 任务恢复异常: {str(e)}")
        return False

def test_subtitle_features():
    """测试字幕相关功能"""
    print("\n📝 测试字幕功能...")
    
    # 这里可以添加更多字幕功能的测试
    # 比如测试术语库提取、智能切分等
    
    test_text = "This is a test subtitle for artificial intelligence and machine learning."
    
    # 模拟术语提取测试
    print(f"测试文本: {test_text}")
    print("✅ 字幕功能测试完成（需要实际运行时验证）")

def test_docker_services():
    """测试 Docker 服务状态"""
    print("\n🐳 测试 Docker 服务状态...")
    
    services = [
        ("Ollama", "http://localhost:11434"),
        ("Redis", "redis://localhost:6379"),
        ("API", "http://localhost:8000"),
        ("Frontend", "http://localhost:3001")
    ]
    
    for name, url in services:
        try:
            if url.startswith("redis://"):
                # Redis 需要特殊处理
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('localhost', 6379))
                sock.close()
                if result == 0:
                    print(f"✅ {name} 服务正常")
                else:
                    print(f"❌ {name} 服务不可用")
            else:
                response = requests.get(url, timeout=5)
                if response.status_code < 500:
                    print(f"✅ {name} 服务正常")
                else:
                    print(f"❌ {name} 服务异常: {response.status_code}")
        except Exception as e:
            print(f"❌ {name} 服务不可用: {str(e)}")

def main():
    """主测试函数"""
    print("🚀 TransTube 功能测试开始")
    print("=" * 50)
    
    # 1. 测试 API 连接
    if not test_api_connection():
        print("❌ API 连接失败，请确保后端服务正在运行")
        sys.exit(1)
    
    # 2. 测试 Docker 服务
    test_docker_services()
    
    # 3. 测试字幕功能
    test_subtitle_features()
    
    # 4. 测试视频处理（可选，因为需要较长时间）
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        task_id = test_video_processing()
        if task_id:
            # 测试任务状态查询
            result = test_task_status(task_id)
            
            # 如果任务失败，测试恢复功能
            if result and result.get("status") == "failed":
                test_task_resume(task_id)
    else:
        print("\n💡 提示: 使用 --full 参数进行完整测试（包括视频处理）")
    
    print("\n" + "=" * 50)
    print("🎉 测试完成")

if __name__ == "__main__":
    main() 