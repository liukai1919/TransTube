#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试中文内容跳过翻译功能
"""

import sys
import os
sys.path.append('backend')

from utils.translator import _translate_batch

def test_chinese_skip():
    """测试中文内容跳过翻译"""
    
    # 测试用例1：纯中文内容
    print("=== 测试用例1：纯中文内容 ===")
    chinese_batch = [
        "这是一个中文句子",
        "另一个中文句子",
        "第三个中文句子"
    ]
    
    result1 = _translate_batch(chinese_batch, "zh")
    print(f"输入: {chinese_batch}")
    print(f"输出: {result1}")
    print(f"是否跳过翻译: {result1 == chinese_batch}")
    print()
    
    # 测试用例2：混合中英文内容
    print("=== 测试用例2：混合中英文内容 ===")
    mixed_batch = [
        "这是一个中文句子",
        "This is an English sentence",
        "另一个中文句子",
        "Another English sentence"
    ]
    
    result2 = _translate_batch(mixed_batch, "zh")
    print(f"输入: {mixed_batch}")
    print(f"输出: {result2}")
    print()
    
    # 测试用例3：纯英文内容
    print("=== 测试用例3：纯英文内容 ===")
    english_batch = [
        "This is an English sentence",
        "Another English sentence",
        "Third English sentence"
    ]
    
    result3 = _translate_batch(english_batch, "zh")
    print(f"输入: {english_batch}")
    print(f"输出: {result3}")
    print()

if __name__ == "__main__":
    test_chinese_skip() 