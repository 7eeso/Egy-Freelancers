/* Site-wide behaviour: mobile menu + hero video controls. Smooth anchor scrolling is handled in CSS. */
document.addEventListener("DOMContentLoaded", () => {
  /* ---- Mobile navigation ---- */
  const header = document.getElementById("site-header");
  const toggle = document.querySelector("[data-nav-toggle]");
  if (header && toggle) {
    const setOpen = (open) => {
      header.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Close" : "Menu";
    };
    toggle.addEventListener("click", () => setOpen(!header.classList.contains("is-open")));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && header.classList.contains("is-open")) { setOpen(false); toggle.focus(); } });
    document.addEventListener("click", (e) => { if (header.classList.contains("is-open") && !header.contains(e.target)) setOpen(false); });
    header.querySelectorAll(".site-menu a").forEach((a) => a.addEventListener("click", () => setOpen(false)));
    window.matchMedia("(min-width: 961px)").addEventListener("change", (e) => { if (e.matches) setOpen(false); });
  }

  /* ---- Hero video: fallback, pause control, reduced motion ---- */
  const media = document.querySelector("[data-hero-media]");
  const video = media && media.querySelector("video");
  if (video) {
    const button = media.querySelector("[data-video-toggle]");
    const useFallback = () => { media.classList.add("is-fallback"); if (button) button.hidden = true; };
    // 'error' does not bubble from <source>, so listen in the capture phase.
    video.addEventListener("error", useFallback, true);

    const setPlaying = (play) => {
      if (play) { const p = video.play(); if (p && p.catch) p.catch(() => {}); }
      else video.pause();
    };
    if (button) {
      button.hidden = false;
      // keep the label truthful even when the browser pauses/resumes the video itself
      const sync = () => { button.textContent = video.paused ? "Play video" : "Pause video"; };
      video.addEventListener("play", sync);
      video.addEventListener("pause", sync);
      button.addEventListener("click", () => setPlaying(video.paused));
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      video.removeAttribute("autoplay");
      setPlaying(false);
    }
  }
});

/* ---- UI polish: JS flag, header shadow, scroll reveal, counters, rotating word, password meter ---- */
document.documentElement.classList.add("js");
document.addEventListener("DOMContentLoaded", () => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const header = document.getElementById("site-header");
  if (header) { const f = () => header.classList.toggle("is-scrolled", window.scrollY > 8); f(); addEventListener("scroll", f, { passive: true }); }

  const targets = document.querySelectorAll(".reveal, .reveal-group > *");
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
    }), { threshold: 0.12 });
    document.querySelectorAll(".reveal-group").forEach((g) => [...g.children].forEach((c, i) => c.style.transitionDelay = `${Math.min(i, 6) * 70}ms`));
    targets.forEach((t) => io.observe(t));
  } else targets.forEach((t) => t.classList.add("is-in"));

  document.querySelectorAll("[data-count]").forEach((el) => {
    const end = Number(el.dataset.count) || 0;
    if (reduce || end === 0) { el.textContent = end.toLocaleString("en-EG"); return; }
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return; io.disconnect();
      const t0 = performance.now();
      const tick = (t) => { const p = Math.min((t - t0) / 1100, 1); el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3))).toLocaleString("en-EG"); if (p < 1) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    }); io.observe(el);
  });

  const rot = document.querySelector("[data-rotate]");
  if (rot && !reduce) {
    const words = rot.dataset.rotate.split("|"); let i = 0;
    setInterval(() => { rot.classList.add("is-out"); setTimeout(() => { i = (i + 1) % words.length; rot.textContent = words[i]; rot.classList.remove("is-out"); }, 350); }, 2800);
  }

  const pw = document.querySelector("[data-strength]");
  const meter = document.querySelector(".strength");
  if (pw && meter) pw.addEventListener("input", () => {
    const v = pw.value; let s = 0;
    if (v.length >= 10) s++; if (v.length >= 14) s++; if (/[a-z]/i.test(v) && /\d/.test(v)) s++; if (/[^A-Za-z0-9]/.test(v)) s++;
    meter.dataset.level = v ? String(Math.max(s, 1)) : "0";
  });
});
