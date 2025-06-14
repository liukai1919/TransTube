#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试特定空白问题的修复效果
"""

import sys
import os

# 添加项目路径到Python路径
sys.path.append('/home/liukai1919/TransTube-1')

from backend.utils.subtitle_fixer import fix_blank_terminology_in_text

def test_specific_issues():
    """测试具体的空白问题"""
    
    test_cases = [
        # 您提到的具体问题
        '在Vision OS", 2中，包含像停靠播放和空间视频这样的惊人体验。',
        
        # 其他类似问题
        '我是 ","团队的媒体应用工程师。',
        '在 ", 2 中，这包括像停靠播放和空间视频这样的惊人体验。',
        '快速预览", 提供了两个应用程序接口 接口 接口。',
        '使用 ", 框架。',
        '", 和 ",，以便支持更多沉浸式媒体配置。',
        '在 ", 26上，我们扩展模式。',
        'Vision OS", 2',
        'Vision Pro", 2',
        'visionOS", 26',
        '应用程序接口 接口 接口支持',
        '媒体 ", 借助',
    ]
    
    print("🔧 测试空白术语修复效果")
    print("=" * 60)
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n测试 {i}:")
        print(f"原文: {test_text}")
        
        fixed_text = fix_blank_terminology_in_text(test_text)
        
        print(f"修复: {fixed_text}")
        
        if test_text != fixed_text:
            print("✅ 已修复")
        else:
            print("❌ 未修复")
        
        print("-" * 40)

def test_your_specific_case():
    """测试您截图中的具体问题"""
    
    print("\n🎯 测试您的具体问题")
    print("=" * 60)
    
    original = '在Vision OS", 2中，包含像停靠播放和空间视频这样的惊人体验。'
    expected = '在visionOS 2中，包含像停靠播放和空间视频这样的惊人体验。'
    
    print(f"原文: {original}")
    print(f"期望: {expected}")
    
    fixed = fix_blank_terminology_in_text(original)
    print(f"实际: {fixed}")
    
    if fixed == expected:
        print("✅ 修复成功！")
    else:
        print("❌ 修复不完全")
        
        # 详细分析差异
        print("\n差异分析:")
        if "Vision OS" in fixed:
            print("- 仍包含 'Vision OS' 而不是 'visionOS'")
        if '"' in fixed:
            print("- 仍包含多余的引号")
        if ', 2' in fixed:
            print("- 仍包含分离的 ', 2'")

if __name__ == "__main__":
    test_your_specific_case()
    test_specific_issues() 