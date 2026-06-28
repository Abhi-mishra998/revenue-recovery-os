// Tiny count-up hook — animates a number from 0 to `target` over `duration` ms.
import { useEffect, useState, useRef } from "react";

export function useCountUp(target, { duration = 900, decimals = 0 } = {}) {
  const [value, setValue] = useState(target == null ? null : 0);
  const startTsRef = useRef(null);
  const fromRef = useRef(0);
  const toRef = useRef(0);

  useEffect(() => {
    if (target == null || isNaN(target)) {
      setValue(null);
      return;
    }
    fromRef.current = typeof value === "number" ? value : 0;
    toRef.current = Number(target);
    startTsRef.current = null;
    let raf;

    const tick = (ts) => {
      if (!startTsRef.current) startTsRef.current = ts;
      const elapsed = ts - startTsRef.current;
      const t = Math.min(1, elapsed / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      const v = fromRef.current + (toRef.current - fromRef.current) * eased;
      setValue(decimals === 0 ? Math.round(v) : Number(v.toFixed(decimals)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, decimals]); // eslint-disable-line react-hooks/exhaustive-deps

  return value;
}
