import { useState, useEffect } from 'react';
import styles from '../styles/Videos.module.css';
import Link from 'next/link';

export default function Videos() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchVideos();
  }, []);

  const fetchVideos = async () => {
    try {
      const response = await fetch('/api/videos');
      if (!response.ok) {
        throw new Error('获取视频列表失败');
      }
      const data = await response.json();
      setVideos(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}小时${minutes}分${remainingSeconds}秒`;
    } else if (minutes > 0) {
      return `${minutes}分${remainingSeconds}秒`;
    } else {
      return `${remainingSeconds}秒`;
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>{error}</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>已处理的视频</h1>
        <Link href="/" className={styles.newVideoButton}>
          处理新视频
        </Link>
      </div>

      {videos.length === 0 ? (
        <div className={styles.empty}>
          <p>还没有处理过的视频</p>
          <Link href="/" className={styles.newVideoButton}>
            开始处理第一个视频
          </Link>
        </div>
      ) : (
        <div className={styles.videoGrid}>
          {videos.map((video) => (
            <div key={video.video_url} className={styles.videoCard}>
              {video.video_url ? (
                <video
                  className={styles.thumbnail}
                  src={video.video_url}
                  preload="metadata"
                  controls
                  crossOrigin="anonymous"
                />
              ) : (
                <div className={styles.thumbnailPlaceholder}>
                  <span>视频时长过长，请下载后观看</span>
                </div>
              )}
              <div className={styles.videoInfo}>
                <h3>{video.title}</h3>
                <p className={styles.duration}>{formatDuration(video.duration)}</p>
                <div className={styles.actions}>
                  {video.video_url && (
                    <a
                      href={video.video_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.watchButton}
                    >
                      观看视频
                    </a>
                  )}
                  <a
                    href={`/api/download/video/${video.download_url.split('/').pop()}`}
                    download={video.title ? `${video.title}.mp4` : 'video.mp4'}
                    className={styles.downloadButton}
                  >
                    下载视频
                  </a>
                  <a 
                    href={`/api/download/subtitle/${video.srt_url.split('/').pop()}`} 
                    download 
                    className={styles.downloadButton}
                  >
                    下载字幕
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
} 