#!/usr/bin/env python3
"""
播放列表检测和处理示例
演示如何使用改进后的 get_playlist_info 功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from utils.downloader import get_playlist_info

def test_playlist_detection():
    """测试各种YouTube URL的播放列表检测"""
    
    test_urls = [
        # 明确的播放列表URL
        "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        
        # 播放列表中的视频URL
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        
        # 带有索引的播放列表视频
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf&index=2",
        
        # 单个视频URL
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        
        # 短链接格式
        "https://youtu.be/dQw4w9WgXcQ",
        
        # 短链接带播放列表
        "https://youtu.be/dQw4w9WgXcQ?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
    ]
    
    for url in test_urls:
        print(f"\n测试URL: {url}")
        print("-" * 80)
        
        info = get_playlist_info(url)
        
        if info:
            if info['type'] == 'playlist':
                print(f"类型: 播放列表")
                print(f"播放列表标题: {info['playlist_title']}")
                print(f"播放列表ID: {info['playlist_id']}")
                print(f"上传者: {info['uploader']}")
                print(f"视频数量: {info['video_count']}")
                print(f"总时长: {info.get('total_duration', 0) // 60} 分钟")
                
                if info['videos']:
                    print("\n前5个视频:")
                    for video in info['videos'][:5]:
                        print(f"  {video['index']}. {video['title']}")
                        print(f"     ID: {video['id']}")
                        print(f"     时长: {video['duration']}秒")
            else:
                print(f"类型: 单个视频")
                print(f"视频标题: {info['title']}")
                print(f"视频ID: {info['video_id']}")
                print(f"上传者: {info['uploader']}")
                print(f"时长: {info['duration']}秒")
        else:
            print("无法获取信息")


def demonstrate_api_usage():
    """演示如何通过API使用播放列表功能"""
    
    print("\n\n=== API 使用示例 ===\n")
    
    print("1. 检查URL类型:")
    print("""
    POST /api/check-playlist
    Content-Type: application/x-www-form-urlencoded
    
    video_url=https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf
    """)
    
    print("\n2. 处理播放列表:")
    print("""
    POST /api/process-playlist
    Content-Type: application/x-www-form-urlencoded
    
    video_url=https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf
    target_lang=zh
    max_videos=5  # 可选，限制处理数量
    """)
    
    print("\n3. 查询批量任务状态:")
    print("""
    GET /api/batch/{batch_id}
    """)


if __name__ == "__main__":
    print("YouTube 播放列表检测功能演示")
    print("=" * 80)
    
    # 运行测试
    test_playlist_detection()
    
    # 显示API用法
    demonstrate_api_usage()
    
    print("\n\n提示：")
    print("- 使用 yt-dlp 的 extract_info 方法进行准确的播放列表检测")
    print("- 支持各种YouTube URL格式，包括播放列表、播放列表中的视频等")
    print("- 自动区分单个视频和播放列表")
    print("- 对于大型播放列表，建议使用 max_videos 参数限制处理数量") 