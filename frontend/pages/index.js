import React, { useState, useEffect } from 'react';
import styles from '../styles/Home.module.css';
import Link from 'next/link';

// 简化版组件，避免复杂的 hooks 结构
export default function Home() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const [deletingAll, setDeletingAll] = useState(false);

  // 轮询任务状态
  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const response = await fetch(`/api/task/${taskId}`);
          if (!response.ok) throw new Error('获取任务状态失败');
          
          const data = await response.json();
          setProgress(data.progress);
          setStatus(data.message);
          
          if (data.status === 'completed') {
            setResult(data.result);
            setLoading(false);
            clearInterval(interval);
            setTaskId(null);
          } else if (data.status === 'failed') {
            setError(data.error || '处理失败');
            setLoading(false);
            clearInterval(interval);
            setTaskId(null);
          }
        } catch (err) {
          console.error('获取任务状态失败:', err);
          setError('获取任务状态失败: ' + err.message);
          setLoading(false);
          clearInterval(interval);
          setTaskId(null);
        }
      }, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [taskId]);

  // -------------------- 检测生成的视频链接是否可播放 --------------------
  useEffect(() => {
    // 当 result 更新且包含 video_url 时，主动做一次 5 秒可播放探测
    if (result?.video_url) {
      (async () => {
        const playable = await checkVideoPlayable(result.video_url);
        if (!playable) {
          setError('视频无法在线播放，请尝试下载后观看');
        } else {
          // setError(null); // Clear old error only if playable, might hide other errors
        }
      })();
    }
  }, [result]);
  // -------------------------------------------------------------------

  // 处理表单提交
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(0);
    setStatus('初始化中...');
    setTaskId(null);

    try {
      const formData = new FormData();
      formData.append('video_url', url);
      formData.append('target_lang', 'zh');

      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(`请求失败 (${response.status}): ${errorData.detail}`);
      }

      const data = await response.json();
      setTaskId(data.task_id);
    } catch (err) {
      console.error('Error:', err);
      setError(err.message || '处理视频时出错');
      setLoading(false);
    }
  };

  // 下载文件
  const handleDownload = async (fileUrl, fileName) => {
    try {
      setError(null);
      setStatus('正在准备下载...');
      setProgress(0);
      
      // 从URL中提取文件类型和文件名
      const urlParts = fileUrl.split('/');
      const filename = urlParts[urlParts.length - 1];
      const fileType = fileUrl.includes('/videos/') ? 'video' : 'subtitle';
      
      // 使用新的下载端点
      const downloadUrl = `/api/download/${fileType}/${filename}`;
      
      console.log('开始下载:', downloadUrl, '文件名:', fileName);
      
      // 检查文件是否可访问
      const headResponse = await fetch(downloadUrl, { 
        method: 'HEAD',
        headers: {
          'Accept': '*/*'
        }
      });
      
      if (!headResponse.ok) {
        const errorText = await headResponse.text();
        throw new Error(`文件不可访问 (${headResponse.status}): ${errorText}`);
      }
      
      const contentLength = headResponse.headers.get('content-length');
      const totalSize = contentLength ? parseInt(contentLength, 10) : 0;
      
      setStatus('正在下载...');
      const response = await fetch(downloadUrl, {
        headers: {
          'Accept': '*/*'
        }
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`下载失败 (${response.status}): ${errorText}`);
      }
      
      // 检查响应类型
      const contentType = response.headers.get('content-type');
      if (!contentType || (!contentType.includes('video/') && !contentType.includes('text/'))) {
        console.warn('意外的内容类型:', contentType);
      }
      
      const reader = response.body.getReader();
      let receivedLength = 0;
      const chunks = [];
      
      while(true) {
        const {done, value} = await reader.read();
        if (done) break;
        chunks.push(value);
        receivedLength += value.length;
        if (totalSize) {
          const downloadProgress = (receivedLength / totalSize) * 100;
          setProgress(downloadProgress);
          setStatus(`下载中... ${downloadProgress.toFixed(1)}%`);
        } else {
          setStatus(`已下载 ${(receivedLength / 1024 / 1024).toFixed(2)} MB`);
        }
      }
      
      const blob = new Blob(chunks);
      const downloadUrl2 = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl2;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl2);
      document.body.removeChild(a);
      
      setStatus('下载完成!');
      setProgress(100);
      setTimeout(() => {
        setStatus('');
        setProgress(0);
      }, 3000);
      
    } catch (err) {
      console.error('下载出错:', err);
      setError('下载文件时出错: ' + err.message);
      setStatus('');
      setProgress(0);
    }
  };

  // 检查视频是否可播放
  const checkVideoPlayable = (videoUrl) => {
    return new Promise((resolve) => {
      const video = document.createElement('video');
      video.src = videoUrl;
      video.onloadeddata = () => resolve(true);
      video.onerror = () => resolve(false);
      video.onstalled = () => resolve(false);
      setTimeout(() => {
        video.onloadeddata = null;
        video.onerror = null;
        video.onstalled = null;
        resolve(false);
      } , 5000);
    });
  };

  // 新增：处理删除所有视频和数据的函数
  const handleDeleteAll = async () => {
    if (!window.confirm('确定要删除所有已处理的视频、字幕和任务数据吗？此操作不可恢复。')) {
      return;
    }
    setDeletingAll(true);
    setError(null);
    setStatus('正在删除所有数据...');
    try {
      const response = await fetch('/api/videos/all', { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.message || '删除失败');
      }
      setStatus(data.message || '所有数据已成功删除！');
      setResult(null);
    } catch (err) {
      console.error('删除所有数据时出错:', err);
      setError('删除所有数据时出错: ' + err.message);
      setStatus('');
    } finally {
      setDeletingAll(false);
      setTimeout(() => {
        setStatus('');
      }, 5000);
    }
  };

  return (
    <div className={styles.container}>
      <main className={styles.main}>
        <h1 className={styles.title}>
          视频翻译工具
        </h1>

        <p className={styles.description}>
          输入视频URL，自动生成中文字幕
        </p>

        <div className={styles.managementLinks}>
          <Link href="/videos" className={styles.link}>
            查看已处理的视频
          </Link>
          <button 
            onClick={handleDeleteAll} 
            className={`${styles.button} ${styles.deleteButton}`}
            disabled={loading || deletingAll}
            title="删除所有已处理的视频、字幕和任务数据"
          >
            {deletingAll ? '删除中...' : '清空所有数据'}
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="输入 YouTube 视频链接"
            className={styles.input}
            disabled={loading || deletingAll}
            required
          />
          <button 
            type="submit" 
            className={styles.button}
            disabled={loading || deletingAll}
          >
            {loading ? '处理中...' : '开始处理'}
          </button>
        </form>

        {loading && (
          <div className={styles.taskStatus}>
            <div className={styles.progress}>
              <div className={styles.progressBar}>
                <div 
                  className={styles.progressBarInner} 
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className={styles.progressInfo}>
                <span>{status}</span>
                <span>{progress.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className={styles.error}>
            <p>{error}</p>
            <button onClick={() => setError(null)} className={styles.dismissButton}>好的</button>
          </div>
        )}

        {result && (
          <div className={styles.result}>
            <h2>处理完成</h2>
            <div className={styles.resultItem}>
              <h4>{result.title || '处理完成的视频'}</h4>
              {result.video_url ? (
                <div className={styles.videoContainer}>
                  <video
                    key={result.video_url}
                    controls
                    preload="metadata"
                    crossOrigin="anonymous"
                    className={styles.video}
                    onError={(e) => {
                      console.error('视频播放错误:', e);
                      setError('视频播放失败，请尝试下载后观看');
                    }}
                    onLoadedData={() => setError(null)}
                  >
                    <source src={result.video_url} type="video/mp4" />
                    您的浏览器不支持视频播放
                  </video>
                </div>
              ) : (
                <div className={styles.longVideoNotice}>
                  <p>视频时长超过30分钟，请下载后观看</p>
                  <p>视频标题: {result.title}</p>
                  <p>视频时长: {Math.floor(result.duration / 60)}分{Math.floor(result.duration % 60)}秒</p>
                </div>
              )}
              <div className={styles.downloadLinks}>
                {result.download_url && (
                  <button
                    onClick={() => handleDownload(result.download_url, result.title ? `${result.title.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_.-]/g, '_')}_sub.mp4` : 'video_sub.mp4')}
                    className={styles.button}
                    disabled={status.startsWith('下载中') || status === '正在准备下载...'}
                  >
                    下载视频 (MP4)
                  </button>
                )}
                {result.srt_url && (
                  <button
                    onClick={() => handleDownload(result.srt_url, result.title ? `${result.title.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_.-]/g, '_')}_zh.srt` : 'subtitles_zh.srt')}
                    className={styles.button}
                    disabled={status.startsWith('下载中') || status === '正在准备下载...'}
                  >
                    下载字幕 (SRT)
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}