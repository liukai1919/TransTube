import React, { useState } from 'react';
import styles from '../styles/Home.module.css';

// 简化版组件，避免复杂的 hooks 结构
export default function Home() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // 处理表单提交
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 发送请求到后端 API
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
      setResult(data);
    } catch (err) {
      console.error('Error:', err);
      setError(err.message || '处理视频时出错');
    } finally {
      setLoading(false);
    }
  };

  // 下载文件
  const handleDownload = async (fileUrl, fileName) => {
    try {
      const response = await fetch(fileUrl);
      if (!response.ok) throw new Error('下载失败');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('下载出错:', err);
      setError('下载文件时出错: ' + err.message);
    }
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

        {error && (
          <div className={styles.error}>
            <p>{error}</p>
          </div>
        )}

        {loading && (
          <div className={styles.loading}>
            <p>正在处理视频，请稍候...</p>
            <div className={styles.spinner}></div>
          </div>
        )}

        {result && (
          <div className={styles.result}>
            <h2>处理完成</h2>
            {result.video_url && (
              <div className={styles.videoContainer}>
                <video controls className={styles.video}>
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
                >
                  下载视频
                </button>
              )}
              {result.subtitle_url && (
                <button
                  onClick={() => handleDownload(result.subtitle_url, `字幕_${new Date().toISOString().split('T')[0]}.srt`)}
                  className={styles.downloadButton}
                >
                  下载字幕
                </button>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
