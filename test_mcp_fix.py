#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MCp术语保护和英文换行修复功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# 只导入字幕修复功能，避免依赖问题
from utils.subtitle_fixer import merge_inline_linebreaks, NO_TRANSLATE_TERMS

def test_english_linebreak_fix():
    """测试英文换行修复功能"""
    print("=== 测试英文换行修复功能 ===")
    
    test_cases = [
        "V\nS\nCode is a great editor",
        "MC\np is a framework",
        "Hello\nWorld\nApplication",
        "React\nNative\nDevelopment",
        "Python\nScript\nExecution",
        "JavaScript\nCode\nReview",
        "API\nDesign\nPatterns",
        "MC\np\nFramework",
        "V\nS\nCode\nEditor"
    ]
    
    for text in test_cases:
        print(f"\n原文: {text}")
        fixed = merge_inline_linebreaks(text)
        print(f"修复后: {fixed}")

def test_no_translate_terms():
    """测试不翻译术语列表"""
    print("\n=== 测试不翻译术语列表 ===")
    print("当前不翻译的术语:")
    for term in sorted(NO_TRANSLATE_TERMS):
        print(f"  - {term}")

def test_mcp_specific():
    """测试MCp/MCP特定的修复"""
    print("\n=== 测试MCp/MCP特定修复 ===")
    
    mcp_cases = [
        "MC\np",
        "MC\np\nFramework", 
        "Using\nMC\np",
        "MC\np\nis\npowerful",
        "MC\np\nand\nAPI",
        "M\nC\nP",
        "M\nC\nP\nFramework",
        "Using\nM\nC\nP",
        "M\nC\nP\nis\npowerful",
        "M\nC\nP\nand\nAPI",
        "vibe\ncoding",
        "vibe\ncoding\nis\nfun",
        "Using\nvibe\ncoding",
        "vibe\ncoding\napproach"
    ]
    
    for text in mcp_cases:
        print(f"\n原文: {text}")
        fixed = merge_inline_linebreaks(text)
        print(f"修复后: {fixed}")

if __name__ == "__main__":
    test_english_linebreak_fix()
    test_mcp_specific()
    test_no_translate_terms()
    
    print("\n=== 测试完成 ===") 