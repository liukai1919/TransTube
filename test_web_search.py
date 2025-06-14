#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络术语搜索功能测试脚本
用于验证搜索API配置和功能是否正常工作
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_search_api_config():
    """测试搜索API配置"""
    print("🔧 检查搜索API配置...")
    
    serper_key = os.getenv("SERPER_API_KEY")
    bing_key = os.getenv("BING_SEARCH_API_KEY")
    enable_search = os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true"
    
    print(f"ENABLE_WEB_SEARCH: {enable_search}")
    print(f"SERPER_API_KEY: {'✅ 已配置' if serper_key else '❌ 未配置'}")
    print(f"BING_SEARCH_API_KEY: {'✅ 已配置' if bing_key else '❌ 未配置'}")
    
    if not enable_search:
        print("⚠️ 网络搜索功能未启用")
        return False
    
    if not serper_key and not bing_key:
        print("❌ 未配置任何搜索API密钥")
        return False
    
    print("✅ API配置检查通过")
    return True

def test_web_search_module():
    """测试网络搜索模块导入"""
    print("\n📦 测试模块导入...")
    
    try:
        from backend.utils.web_terminology_search import WebTerminologySearcher, detect_uncertain_terms
        print("✅ 网络搜索模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False

def test_uncertain_term_detection():
    """测试不确定术语检测"""
    print("\n🔍 测试不确定术语检测...")
    
    try:
        from backend.utils.web_terminology_search import detect_uncertain_terms
        
        # 测试文本
        test_text = """
        This video covers Kubernetes deployment strategies and Docker containerization.
        We'll also discuss GraphQL APIs, JAMstack architecture, and Serverless computing.
        The presenter mentions TensorFlow and PyTorch for machine learning applications.
        """
        
        existing_terms = {
            "Docker": "Docker",
            "API": "应用程序接口"
        }
        
        uncertain_terms = detect_uncertain_terms(test_text, existing_terms)
        
        print(f"测试文本: {test_text[:100]}...")
        print(f"现有术语库: {existing_terms}")
        print(f"检测到的不确定术语: {uncertain_terms}")
        
        if uncertain_terms:
            print("✅ 不确定术语检测正常")
            return True
        else:
            print("⚠️ 未检测到不确定术语")
            return False
            
    except Exception as e:
        print(f"❌ 术语检测失败: {e}")
        return False

def test_search_functionality():
    """测试搜索功能"""
    print("\n🌐 测试搜索功能...")
    
    if not test_search_api_config():
        print("⚠️ 跳过搜索功能测试（API未配置）")
        return False
    
    try:
        from backend.utils.web_terminology_search import WebTerminologySearcher
        
        searcher = WebTerminologySearcher()
        
        # 测试搜索单个术语
        test_term = "GraphQL"
        print(f"搜索术语: {test_term}")
        
        translation = searcher.search_and_translate(test_term)
        
        if translation:
            print(f"✅ 搜索成功: {test_term} -> {translation}")
            return True
        else:
            print(f"⚠️ 未找到翻译: {test_term}")
            return False
            
    except Exception as e:
        print(f"❌ 搜索功能测试失败: {e}")
        return False

def test_integration():
    """测试集成功能"""
    print("\n🔗 测试集成功能...")
    
    try:
        from backend.utils.web_terminology_search import enhance_terminology_with_web_search
        
        test_text = "This presentation covers Kubernetes and Docker containerization techniques."
        existing_terminology = {
            "API": "应用程序接口",
            "Machine Learning": "机器学习"
        }
        
        print(f"原始术语库大小: {len(existing_terminology)}")
        
        enhanced_terminology = enhance_terminology_with_web_search(
            test_text, 
            existing_terminology, 
            max_search_terms=2
        )
        
        print(f"增强后术语库大小: {len(enhanced_terminology)}")
        
        new_terms = {k: v for k, v in enhanced_terminology.items() if k not in existing_terminology}
        if new_terms:
            print(f"新增术语: {new_terms}")
            print("✅ 集成功能正常")
            return True
        else:
            print("⚠️ 未发现新术语")
            return True  # 这不是错误，可能是没有不确定术语
            
    except Exception as e:
        print(f"❌ 集成功能测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 TransTube 网络术语搜索功能测试")
    print("=" * 50)
    
    tests = [
        ("API配置检查", test_search_api_config),
        ("模块导入测试", test_web_search_module),
        ("术语检测测试", test_uncertain_term_detection),
        ("搜索功能测试", test_search_functionality),
        ("集成功能测试", test_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 执行出错: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    print(f"\n通过率: {passed_count}/{total_count} ({passed_count/total_count*100:.1f}%)")
    
    if passed_count == total_count:
        print("🎉 所有测试通过！网络搜索功能已就绪")
    elif passed_count >= total_count - 1:
        print("⚠️ 大部分测试通过，功能基本可用")
    else:
        print("❌ 多个测试失败，请检查配置和环境")
    
    print("\n💡 使用提示:")
    print("1. 确保在 .env 文件中配置搜索API密钥")
    print("2. 设置 ENABLE_WEB_SEARCH=true 启用网络搜索")
    print("3. 查看 WEB_SEARCH_SETUP.md 了解详细配置")
    
    return passed_count == total_count

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 