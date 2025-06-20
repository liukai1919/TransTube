#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试空白问题检测修复
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from utils.translator import has_blank_terminology_issues, NO_TRANSLATE_TERMS

def test_blank_issue_detection():
    """测试空白问题检测"""
    print("=== 测试空白问题检测 ===")
    
    # 正常翻译结果（不应该被检测为问题）
    normal_cases = [
        "你不需要编写代码，因为在使用 Claude 时，你就会明白其中无需任何代码参与。",
        "使用 API 进行开发",
        "MCp 是一个强大的框架",
        "Python 和 JavaScript 都是编程语言",
        "GitHub 是代码托管平台",
        "使用 Docker 容器化应用",
        "React 和 Vue 是前端框架"
    ]
    
    print("\n正常翻译结果测试:")
    for text in normal_cases:
        has_issue = has_blank_terminology_issues(text)
        print(f"文本: {text}")
        print(f"检测结果: {'有问题' if has_issue else '正常'}")
        print()
    
    # 真正的空白问题（应该被检测为问题）
    blank_issue_cases = [
        "你不需要编写代码，因为在使用 \", 代码 时，你就会明白其中无需任何代码参与。",
        "使用 \", 进行开发",
        "MCp \", 是一个强大的框架",
        "Python \", JavaScript 都是编程语言",
        "GitHub \", 是代码托管平台",
        "使用 \", 容器化应用",
        "React \", Vue 是前端框架",
        "在 \", 中开发",
        "使用 \", 框架",
        "通过 \", 学习"
    ]
    
    print("\n空白问题测试:")
    for text in blank_issue_cases:
        has_issue = has_blank_terminology_issues(text)
        print(f"文本: {text}")
        print(f"检测结果: {'有问题' if has_issue else '正常'}")
        print()

def test_no_translate_terms():
    """测试不翻译术语列表"""
    print("\n=== 测试不翻译术语列表 ===")
    print("当前不翻译的术语:")
    for term in sorted(NO_TRANSLATE_TERMS):
        print(f"  - {term}")

if __name__ == "__main__":
    test_blank_issue_detection()
    test_no_translate_terms()
    
    print("\n=== 测试完成 ===") 