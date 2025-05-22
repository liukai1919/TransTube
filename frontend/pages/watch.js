import { useRouter } from 'next/router';
import { useState, useEffect } from 'react';
import styles from '../styles/Watch.module.css';
import Link from 'next/link';

export default function Watch() {
  const router = useRouter();
  const { v: videoUrl } = router.query;
  const [error, setError] = useState(null);

  if (!videoUrl) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>未找到视频</div>
        <Link href="/videos" className={styles.backButton}>
          返回视频列表
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <Link href="/videos" className={styles.backButton}>
          返回视频列表
        </Link>
      </div>

      <div className={styles.videoContainer}>
        <video
          key={videoUrl}
          controls
          preload="metadata"
          crossOrigin="anonymous"
          className={styles.video}
          onError={(e) => {
            console.error('视频播放错误:', e);
            setError('视频播放失败，请尝试下载后观看');
          }}
        >
          <source src={videoUrl} type="video/mp4" />
          您的浏览器不支持视频播放
        </video>
        {error && <div className={styles.error}>{error}</div>}
      </div>
    </div>
  );
} 