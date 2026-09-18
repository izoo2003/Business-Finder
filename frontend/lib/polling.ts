/** Pause timers when the tab is hidden; avoid overlapping in-flight polls. */

export function startVisiblePoll(
  tick: () => void | Promise<void>,
  getDelayMs: () => number,
): () => void {
  let timer: number | null = null;
  let inFlight = false;
  let cancelled = false;

  async function run() {
    if (cancelled || document.hidden || inFlight) return;
    inFlight = true;
    try {
      await tick();
    } finally {
      inFlight = false;
      schedule();
    }
  }

  function schedule() {
    if (cancelled || timer != null) return;
    if (document.hidden) return;
    timer = window.setTimeout(() => {
      timer = null;
      void run();
    }, getDelayMs());
  }

  function onVisibility() {
    if (document.hidden) {
      if (timer != null) {
        window.clearTimeout(timer);
        timer = null;
      }
      return;
    }
    void run();
  }

  document.addEventListener("visibilitychange", onVisibility);
  void run();

  return () => {
    cancelled = true;
    document.removeEventListener("visibilitychange", onVisibility);
    if (timer != null) window.clearTimeout(timer);
  };
}
