import { useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';

export function Background() {
  const video = useRef<HTMLVideoElement>(null);
  const [paused, setPaused] = useState(() => {
    try {
      return (
        localStorage.getItem('devvault-motion') === 'paused' ||
        matchMedia('(prefers-reduced-motion: reduce)').matches
      );
    } catch {
      return true;
    }
  });
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => {
      if (media.matches) setPaused(true);
    };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    const element = video.current;
    function sync() {
      if (paused || document.hidden) element?.pause();
      else element?.play().catch(() => setPaused(true));
    }
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => document.removeEventListener('visibilitychange', sync);
  }, [paused]);
  function toggle() {
    const next = !paused;
    setPaused(next);
    try {
      localStorage.setItem('devvault-motion', next ? 'paused' : 'playing');
    } catch {
      /* Preference storage is optional. */
    }
  }
  return (
    <>
      <div className="ambient-background" aria-hidden="true">
        <img src="/media/vault-poster.svg" alt="" />
        {!failed && (
          <video
            src="/media/vault-motion.webm"
            ref={video}
            muted
            loop
            playsInline
            preload={paused ? 'none' : 'metadata'}
            poster="/media/vault-poster.svg"
            onError={() => setFailed(true)}
          />
        )}
        <div className="ambient-shade" />
      </div>
      <button
        className="motion-toggle"
        onClick={toggle}
        disabled={failed}
        aria-label={
          failed
            ? 'Static background: video unavailable'
            : paused
              ? 'Play background video'
              : 'Pause background video'
        }
      >
        {paused || failed ? <Play size={12} /> : <Pause size={12} />}
        <span>{failed ? 'Static background' : paused ? 'Motion paused' : 'Ambient motion'}</span>
      </button>
    </>
  );
}
