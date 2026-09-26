import { useEffect, useRef, useState } from 'react'
import './DeepSearchLoader.css'

// The magnifier orbits with a resting keyframe every 28.5 frames (~0.48 s at 60 fps). We only ever
// stop ON one of those, so the motion is never cut off mid-swing — without waiting for the whole
// 3.6 s loop (216 frames) on every search.
const ORBIT_STEP = 28.5
const LAST_FRAME = 216 // animation length (op) — the 3.6 s loop

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * "Deep search" animation, overlaid on the results area (absolutely positioned → no layout shift).
 * active=true  → fade in (200 ms) and play from the start.
 * active=false → keep playing to the next orbit keyframe, pause there, fade out (200 ms), then onHidden().
 */
export default function DeepSearchLoader({ active, onHidden, label }) {
  const containerRef = useRef(null)
  const animRef = useRef(null)
  const stopAt = useRef(null)
  const lastFrame = useRef(0)
  const pendingPlay = useRef(false)
  const [finishing, setFinishing] = useState(false)
  const [ready, setReady] = useState(false) // engine + animation loaded
  const [prevActive, setPrevActive] = useState(active)

  // "adjust state when a prop changes" — during render, not in an effect
  if (active !== prevActive) {
    setPrevActive(active)
    setFinishing(!active && ready && !reducedMotion()) // nothing to finish if the engine isn't loaded
  }
  const visible = active || finishing

  // one animation instance for the component's lifetime. The engine is its own chunk, fetched right
  // after first paint, so the page itself isn't slowed down by it.
  useEffect(() => {
    let anim
    let cancelled = false
    const onFrame = (e) => {
      const frame = e.currentTime
      const wrapped = frame < lastFrame.current // loop restarted
      lastFrame.current = frame
      if (stopAt.current !== null && (frame >= stopAt.current || wrapped)) {
        anim.pause()
        stopAt.current = null
        setFinishing(false) // → fade out
      }
    }
    Promise.all([
      import('lottie-web/build/player/lottie_light'), // svg-only build
      import('./assets/lottie/search_emerald_dark.json'),
    ]).then(([{ default: lottie }, { default: animationData }]) => {
      if (cancelled) return
      anim = lottie.loadAnimation({
        container: containerRef.current,
        renderer: 'svg',
        loop: true,
        autoplay: false,
        animationData,
        rendererSettings: { preserveAspectRatio: 'xMidYMid meet' },
      })
      anim.addEventListener('enterFrame', onFrame)
      animRef.current = anim
      setReady(true)
      if (pendingPlay.current) anim.goToAndPlay(0, true) // a search started before the engine arrived
    })
    return () => {
      cancelled = true
      anim?.removeEventListener('enterFrame', onFrame)
      anim?.destroy()
      animRef.current = null
    }
  }, [])

  // drive the animation from `active`
  useEffect(() => {
    pendingPlay.current = active && !reducedMotion()
    const anim = animRef.current
    if (!anim) return
    if (active) {
      stopAt.current = null
      lastFrame.current = 0
      if (reducedMotion()) anim.goToAndStop(0, true)
      else anim.goToAndPlay(0, true)
    } else if (!reducedMotion()) {
      // finish to the next resting keyframe — and never before the first, so it reads as a gesture, not a flicker
      const cur = anim.currentFrame ?? 0
      stopAt.current = Math.min(LAST_FRAME, Math.max(ORBIT_STEP, Math.ceil((cur + 0.01) / ORBIT_STEP) * ORBIT_STEP))
    } else {
      anim.pause()
    }
  }, [active])

  return (
    <div
      className={`deep-search${visible ? ' is-visible' : ''}`}
      aria-hidden={!visible}
      onTransitionEnd={(e) => {
        if (e.target === e.currentTarget && e.propertyName === 'opacity' && !visible) onHidden?.()
      }}
    >
      <div className="deep-search__canvas" ref={containerRef} />
      <p className="deep-search__label" role="status">{visible ? (label ?? 'Searching deeply…') : ''}</p>
    </div>
  )
}
