import React, { useState, useEffect } from 'react';
import styles from '../styles/Home.module.css';

// 简化版组件，避免复杂的 hooks 结构
export default function Home() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');

  // 轮询任务状态
  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const response = await fetch(`http://localhost:8000/api/task/${taskId}`);
          if (!response.ok) throw new Error('获取任务状态失败');
          
          const data = await response.json();
          setProgress(data.progress);
          setStatus(data.message);
          
          if (data.status === 'completed') {
            setResult(data.result);
            setLoading(false);
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setError(data.error || '处理失败');
            setLoading(false);
            clearInterval(interval);
          }
        } catch (err) {
          console.error('获取任务状态失败:', err);
          setError('获取任务状态失败: ' + err.message);
          setLoading(false);
          clearInterval(interval);
        }
      }, 1000);
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
          setError(null);          // 清空旧错误
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

    try {
      const response = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        throw new Error(`请求失败 (${response.status}): ${response.statusText}`);
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
      
      // 先检查文件是否可访问
      const headResponse = await fetch(fileUrl, { method: 'HEAD' });
      if (!headResponse.ok) {
        throw new Error(`文件不可访问 (${headResponse.status})`);
      }
      
      // 获取文件大小
      const contentLength = headResponse.headers.get('content-length');
      const totalSize = contentLength ? parseInt(contentLength, 10) : 0;
      
      // 开始下载
      setStatus('正在下载...');
      const response = await fetch(fileUrl);
      if (!response.ok) {
        throw new Error(`下载失败 (${response.status})`);
      }
      
      // 创建可读流
      const reader = response.body.getReader();
      let receivedLength = 0;
      const chunks = [];
      
      while(true) {
        const {done, value} = await reader.read();
        
        if (done) {
          break;
        }
        
        chunks.push(value);
        receivedLength += value.length;
        
        // 更新下载进度
        if (totalSize) {
          const progress = (receivedLength / totalSize) * 100;
          setProgress(progress);
          setStatus(`下载中... ${progress.toFixed(1)}%`);
        }
      }
      
      // 合并数据块
      const blob = new Blob(chunks);
      
      // 创建下载链接
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      
      // 触发下载
      document.body.appendChild(a);
      a.click();
      
      // 清理
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      setStatus('下载完成');
      setProgress(0);
      
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
      
      video.onloadeddata = () => {
        resolve(true);
      };
      
      video.onerror = () => {
        resolve(false);
      };
      
      // 设置超时
      setTimeout(() => {
        resolve(false);
      }, 5000);
    });
  };

  return (
    <div className={styles.container}>
      <main className={styles.main}>
        <h1 className={styles.title}>YouTrans</h1>
        <p className={styles.description}>YouTube 视频中文字幕生成器</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="输入 YouTube 视频链接"
            className={styles.input}
            disabled={loading}
            required
          />
          <button 
            type="submit" 
            className={styles.button}
            disabled={loading}
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
          </div>
        )}

        {result && (
          <div className={styles.result}>
            <h2>处理完成</h2>
            {result.video_url && (
              <div className={styles.videoContainer}>
                <video
                  key={result.video_url}   // 强制重新渲染
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
            )}
            <div className={styles.buttons}>
              {result.video_url && (
                <button
                  onClick={() => handleDownload(result.video_url, `视频_${new Date().toISOString().split('T')[0]}.mp4`)}
                  className={styles.downloadButton}
                  disabled={status === '正在下载...'}
                >
                  {status === '正在下载...' ? '下载中...' : '下载视频'}
                </button>
              )}
              {result.srt_url && (
                <button
                  onClick={() => handleDownload(result.srt_url, `字幕_${new Date().toISOString().split('T')[0]}.srt`)}
                  className={styles.downloadButton}
                  disabled={status === '正在下载...'}
                >
                  {status === '正在下载...' ? '下载中...' : '下载字幕'}
                </button>
              )}
            </div>
            {status && (
              <div className={styles.downloadStatus}>
                <p>{status}</p>
                {progress > 0 && (
                  <div className={styles.progressBar}>
                    <div 
                      className={styles.progressBarInner} 
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}