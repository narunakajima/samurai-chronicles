"""
sc_build_site.py — episode JSON から index.html を自動生成

使い方:
  python3 sc_build_site.py

episodes/*.json を読み込んで index.html を上書き生成する。
各エピソードの youtube_url が設定されていれば個別リンク、
未設定の場合はチャンネルトップにフォールバック。

/sc-upload 後に自動実行されることを想定。
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
OUTPUT_HTML = BASE_DIR / "index.html"
CHANNEL_URL = "https://www.youtube.com/@Samurai-Chronicles-JP"

THUMB_CLASSES = ["t1", "t2", "t3", "t4"]

EPISODE_IDS = [
    "ep001", "ep002", "ep003", "ep004", "ep005", "ep006", "ep007",
    "ep008", "ep009", "ep010", "ep011", "ep012", "ep013", "ep014",
]


def load_episodes() -> list[dict]:
    episodes = []
    for ep_id in EPISODE_IDS:
        p = EPISODES_DIR / f"{ep_id}.json"
        if not p.exists() or p.stat().st_size == 0:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️  {ep_id}.json が読み込めませんでした（スキップ）")
            continue
        episodes.append(d)
    return episodes


def episode_cards_html(episodes: list[dict]) -> str:
    lines = []
    for i, ep in enumerate(episodes):
        ep_id = ep.get("episode_id", "")
        num_str = ep_id.replace("ep", "").lstrip("0") or "0"
        num_padded = ep_id.replace("ep", "")  # "001"
        title = ep.get("youtube_title") or ep.get("episode_title", "Coming Soon")
        url = ep.get("youtube_url") or CHANNEL_URL
        thumb_cls = THUMB_CLASSES[i % len(THUMB_CLASSES)]
        delay_cls = f" reveal-delay-{(i % 4) + 1}" if (i % 4) != 0 else ""

        lines.append(f"""
        <a class="episode-card reveal{delay_cls}" href="{url}" target="_blank" rel="noopener">
          <div class="episode-thumb {thumb_cls}"><span class="episode-thumb-num">{num_padded}</span></div>
          <div class="episode-info">
            <p class="episode-num">EPISODE {num_padded}</p>
            <p class="episode-title">{title}</p>
          </div>
        </a>""")
    return "\n".join(lines)


def build():
    episodes = load_episodes()
    if not episodes:
        print("❌ エピソードが見つかりませんでした")
        sys.exit(1)

    ep_count = len(episodes)
    cards_html = episode_cards_html(episodes)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Samurai Chronicles | 2,600 Years of Japanese History</title>
  <meta name="description" content="Samurai Chronicles brings you the untold stories of Japan's 2,600-year history — wars, betrayals, forgotten heroes, and legendary warriors. New episodes every day.">
  <meta property="og:title" content="Samurai Chronicles">
  <meta property="og:description" content="2,600 years of Japanese history, told one untold story at a time.">
  <meta property="og:image" content="LOGO.PNG">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    :root {{
      --crimson: #8B0000;
      --crimson-dark: #5c0000;
      --crimson-light: #a80000;
      --gold: #C9A84C;
      --gold-light: #e0c068;
      --gold-dim: #9a7a38;
      --black: #1a1a1a;
      --black-soft: #222222;
      --white: #f5f0e8;
      --white-dim: #c8bfb0;
    }}

    html {{ scroll-behavior: smooth; }}

    body {{
      background-color: var(--black);
      color: var(--white);
      font-family: 'EB Garamond', serif;
      overflow-x: hidden;
    }}

    /* ─── SCROLL ANIMATION ─── */
    .reveal {{
      opacity: 0;
      transform: translateY(28px);
      transition: opacity 0.7s ease, transform 0.7s ease;
    }}
    .reveal.visible {{ opacity: 1; transform: translateY(0); }}
    .reveal-delay-1 {{ transition-delay: 0.1s; }}
    .reveal-delay-2 {{ transition-delay: 0.2s; }}
    .reveal-delay-3 {{ transition-delay: 0.3s; }}
    .reveal-delay-4 {{ transition-delay: 0.4s; }}

    /* ─── HERO ─── */
    .hero {{
      min-height: 100svh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 60px 24px 80px;
      position: relative;
      background:
        radial-gradient(ellipse at 50% 0%, rgba(139, 0, 0, 0.35) 0%, transparent 65%),
        radial-gradient(ellipse at 50% 100%, rgba(0, 0, 0, 0.8) 0%, transparent 60%),
        var(--black);
    }}
    .hero::before {{
      content: '';
      position: absolute;
      inset: 0;
      background-image: repeating-linear-gradient(
        0deg, transparent, transparent 60px,
        rgba(139, 0, 0, 0.03) 60px, rgba(139, 0, 0, 0.03) 61px
      );
      pointer-events: none;
    }}
    .hero-logo {{
      width: min(220px, 55vw);
      height: min(220px, 55vw);
      border-radius: 50%;
      overflow: hidden;
      box-shadow:
        0 0 0 2px rgba(201, 168, 76, 0.4),
        0 0 0 4px rgba(139, 0, 0, 0.3),
        0 0 60px rgba(201, 168, 76, 0.15),
        0 20px 80px rgba(0, 0, 0, 0.7);
      animation: fadeInDown 1s ease both;
      position: relative;
      z-index: 1;
    }}
    .hero-logo img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .hero-tagline {{
      margin-top: 40px;
      animation: fadeInUp 1s 0.25s ease both;
      position: relative;
      z-index: 1;
    }}
    .hero-tagline p {{
      font-family: 'Cinzel', serif;
      font-weight: 400;
      font-size: clamp(1rem, 4vw, 1.35rem);
      letter-spacing: 0.05em;
      color: var(--white-dim);
      line-height: 1.7;
    }}
    .hero-tagline p em {{ font-style: normal; color: var(--gold); }}
    .gold-rule {{
      width: 80px;
      height: 1px;
      background: linear-gradient(to right, transparent, var(--gold), transparent);
      margin: 28px auto;
    }}
    .hero-cta {{
      margin-top: 0;
      animation: fadeInUp 1s 0.45s ease both;
      position: relative;
      z-index: 1;
    }}
    .btn-primary {{
      display: inline-block;
      padding: 16px 36px;
      background: var(--crimson);
      border: 1px solid rgba(201, 168, 76, 0.5);
      color: var(--white);
      font-family: 'Cinzel', serif;
      font-weight: 600;
      font-size: 0.9rem;
      letter-spacing: 0.12em;
      text-decoration: none;
      border-radius: 2px;
      transition: all 0.3s ease;
      box-shadow: 0 4px 20px rgba(139, 0, 0, 0.4);
    }}
    .btn-primary:hover {{
      background: var(--crimson-light);
      border-color: var(--gold);
      color: var(--gold-light);
      box-shadow: 0 6px 30px rgba(139, 0, 0, 0.6);
      transform: translateY(-2px);
    }}

    /* ─── STATS STRIP ─── */
    .stats-strip {{
      background: var(--crimson-dark);
      border-top: 1px solid rgba(201, 168, 76, 0.25);
      border-bottom: 1px solid rgba(201, 168, 76, 0.25);
      padding: 28px 24px;
    }}
    .stats-inner {{
      max-width: 860px;
      margin: 0 auto;
      display: flex;
      justify-content: center;
      gap: clamp(32px, 8vw, 80px);
      flex-wrap: wrap;
    }}
    .stat-item {{ text-align: center; }}
    .stat-num {{
      font-family: 'Cinzel', serif;
      font-weight: 700;
      font-size: clamp(1.6rem, 5vw, 2.2rem);
      color: var(--gold);
      line-height: 1;
    }}
    .stat-label {{
      font-family: 'Cinzel', serif;
      font-size: 0.6rem;
      letter-spacing: 0.2em;
      color: var(--white-dim);
      opacity: 0.75;
      margin-top: 6px;
      text-transform: uppercase;
    }}

    /* ─── SECTION BASE ─── */
    section {{ padding: 80px 24px; }}
    .section-inner {{ max-width: 860px; margin: 0 auto; }}
    .section-label {{
      font-family: 'Cinzel', serif;
      font-size: 0.65rem;
      letter-spacing: 0.3em;
      color: var(--gold);
      text-transform: uppercase;
      text-align: center;
      margin-bottom: 16px;
    }}
    .section-heading {{
      font-family: 'Cinzel', serif;
      font-weight: 700;
      font-size: clamp(1.4rem, 5vw, 2rem);
      text-align: center;
      letter-spacing: 0.06em;
      color: var(--white);
      margin-bottom: 40px;
    }}

    /* ─── ABOUT ─── */
    .about {{
      background: var(--black-soft);
      border-top: 1px solid rgba(201, 168, 76, 0.15);
      border-bottom: 1px solid rgba(201, 168, 76, 0.15);
    }}
    .about-text {{
      text-align: center;
      font-size: clamp(1rem, 3vw, 1.15rem);
      line-height: 2;
      color: var(--white-dim);
      max-width: 600px;
      margin: 0 auto 40px;
    }}
    .about-text strong {{ color: var(--gold); font-weight: 500; font-style: italic; }}
    .about-pillars {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 20px;
      max-width: 720px;
      margin: 0 auto;
    }}
    .pillar {{
      text-align: center;
      padding: 24px 16px;
      border: 1px solid rgba(201, 168, 76, 0.2);
      border-radius: 3px;
      background: rgba(139, 0, 0, 0.06);
    }}
    .pillar-icon {{ font-size: 1.8rem; margin-bottom: 12px; }}
    .pillar-label {{
      font-family: 'Cinzel', serif;
      font-size: 0.7rem;
      letter-spacing: 0.2em;
      color: var(--gold);
      text-transform: uppercase;
    }}
    .pillar-desc {{
      font-size: 0.85rem;
      color: var(--white-dim);
      line-height: 1.6;
      margin-top: 8px;
      opacity: 0.8;
    }}

    /* ─── EPISODES ─── */
    .episodes {{ background: var(--black); }}
    .episodes-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 20px;
    }}
    .episode-card {{
      display: block;
      text-decoration: none;
      background: var(--black-soft);
      border: 1px solid rgba(201, 168, 76, 0.2);
      border-radius: 3px;
      overflow: hidden;
      transition: all 0.3s ease;
    }}
    .episode-card:hover {{
      border-color: rgba(201, 168, 76, 0.5);
      transform: translateY(-4px);
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    }}
    .episode-thumb {{
      width: 100%;
      aspect-ratio: 16 / 9;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
    }}
    .episode-thumb.t1 {{ background: linear-gradient(135deg, #1c0505 0%, #4a0000 50%, #1a1a1a 100%); }}
    .episode-thumb.t2 {{ background: linear-gradient(135deg, #1a0a00 0%, #3d1500 50%, #1a1a1a 100%); }}
    .episode-thumb.t3 {{ background: linear-gradient(135deg, #0a0a1c 0%, #00003d 50%, #1a1a1a 100%); }}
    .episode-thumb.t4 {{ background: linear-gradient(135deg, #0f0a00 0%, #3d2600 50%, #1a1a1a 100%); }}
    .episode-thumb-num {{
      font-family: 'Cinzel', serif;
      font-weight: 700;
      font-size: clamp(1.8rem, 5vw, 2.6rem);
      color: rgba(201, 168, 76, 0.18);
      letter-spacing: 0.1em;
      user-select: none;
      transition: color 0.3s ease;
    }}
    .episode-card:hover .episode-thumb-num {{ color: rgba(201, 168, 76, 0.35); }}
    .episode-thumb::after {{
      content: '▶';
      position: absolute;
      font-size: 1.4rem;
      color: rgba(201, 168, 76, 0.35);
      transition: color 0.3s ease, transform 0.3s ease;
    }}
    .episode-card:hover .episode-thumb::after {{
      color: rgba(201, 168, 76, 0.75);
      transform: scale(1.15);
    }}
    .episode-info {{ padding: 16px; }}
    .episode-num {{
      font-family: 'Cinzel', serif;
      font-size: 0.6rem;
      letter-spacing: 0.2em;
      color: var(--gold-dim);
      margin-bottom: 6px;
    }}
    .episode-title {{
      font-family: 'EB Garamond', serif;
      font-size: 0.95rem;
      color: var(--white-dim);
      line-height: 1.5;
    }}

    /* ─── FOLLOW SECTION ─── */
    .follow {{
      background: var(--black-soft);
      border-top: 1px solid rgba(201, 168, 76, 0.15);
      border-bottom: 1px solid rgba(201, 168, 76, 0.15);
    }}
    .follow-box {{
      max-width: 520px;
      margin: 0 auto;
      border: 1px solid rgba(201, 168, 76, 0.25);
      border-radius: 4px;
      padding: 36px 32px 28px;
      background: rgba(139, 0, 0, 0.05);
      backdrop-filter: blur(4px);
      position: relative;
    }}
    .follow-box-label {{
      font-family: 'Cinzel', serif;
      font-size: 0.62rem;
      letter-spacing: 0.25em;
      color: var(--gold);
      text-transform: uppercase;
      position: absolute;
      top: -0.7em;
      left: 24px;
      background: var(--black-soft);
      padding: 0 10px;
    }}
    .follow-intro {{
      text-align: center;
      font-size: clamp(0.9rem, 2.8vw, 1rem);
      line-height: 1.9;
      color: var(--white-dim);
      opacity: 0.85;
      margin-bottom: 28px;
    }}
    .sns-list {{ display: flex; flex-direction: column; gap: 12px; }}
    .sns-link {{
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px 20px;
      border: 1px solid rgba(201, 168, 76, 0.2);
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.02);
      color: var(--white-dim);
      text-decoration: none;
      transition: all 0.3s ease;
    }}
    .sns-link:hover {{
      background: rgba(139, 0, 0, 0.15);
      border-color: rgba(201, 168, 76, 0.5);
      color: var(--white);
      transform: translateY(-2px);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
    }}
    .sns-icon {{ width: 24px; height: 24px; flex-shrink: 0; opacity: 0.85; }}
    .sns-name {{
      font-family: 'Cinzel', serif;
      font-weight: 600;
      font-size: 0.85rem;
      letter-spacing: 0.15em;
    }}
    .sns-badge {{
      font-family: 'Cinzel', serif;
      font-size: 0.58rem;
      letter-spacing: 0.15em;
      color: var(--gold);
      margin-left: auto;
      border: 1px solid rgba(201, 168, 76, 0.5);
      padding: 3px 8px;
      border-radius: 2px;
      text-transform: uppercase;
    }}

    /* ─── FOOTER ─── */
    footer {{
      background: #111;
      border-top: 1px solid rgba(201, 168, 76, 0.2);
      padding: 40px 24px;
      text-align: center;
    }}
    .footer-logo-text {{
      font-family: 'Cinzel', serif;
      font-weight: 700;
      font-size: 1.1rem;
      letter-spacing: 0.12em;
      color: var(--gold);
      margin-bottom: 16px;
    }}
    .footer-links {{
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }}
    .footer-link {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--white-dim);
      text-decoration: none;
      font-size: 0.85rem;
      letter-spacing: 0.05em;
      transition: color 0.2s ease;
    }}
    .footer-link:hover {{ color: var(--gold); }}
    .footer-link svg {{ width: 18px; height: 18px; flex-shrink: 0; }}
    .footer-copy {{
      font-family: 'Cinzel', serif;
      font-size: 0.65rem;
      letter-spacing: 0.2em;
      color: var(--white-dim);
      opacity: 0.45;
    }}

    /* ─── ANIMATIONS ─── */
    @keyframes fadeInDown {{
      from {{ opacity: 0; transform: translateY(-24px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeInUp {{
      from {{ opacity: 0; transform: translateY(24px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    /* ─── RESPONSIVE ─── */
    @media (max-width: 480px) {{
      .episodes-grid {{ grid-template-columns: 1fr 1fr; gap: 12px; }}
      section {{ padding: 60px 20px; }}
      .follow-box {{ padding: 32px 20px 24px; }}
    }}
    @media (max-width: 320px) {{
      .episodes-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

  <!-- ─── HERO ─── -->
  <section class="hero" id="top">
    <div class="hero-logo">
      <img src="LOGO.PNG" alt="Samurai Chronicles">
    </div>
    <div class="hero-tagline">
      <div class="gold-rule"></div>
      <p><em>2,600 years</em> of Japanese history,</p>
      <p>told one untold story at a time.</p>
      <div class="gold-rule"></div>
    </div>
    <div class="hero-cta">
      <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">
        Watch on YouTube &rarr;
      </a>
    </div>
  </section>

  <!-- ─── STATS STRIP ─── -->
  <div class="stats-strip reveal">
    <div class="stats-inner">
      <div class="stat-item">
        <p class="stat-num">{ep_count}</p>
        <p class="stat-label">Episodes</p>
      </div>
      <div class="stat-item">
        <p class="stat-num">2,600</p>
        <p class="stat-label">Years of History</p>
      </div>
      <div class="stat-item">
        <p class="stat-num">Daily</p>
        <p class="stat-label">New Episodes</p>
      </div>
    </div>
  </div>

  <!-- ─── ABOUT ─── -->
  <section class="about" id="about">
    <div class="section-inner">
      <p class="section-label reveal">About</p>
      <h2 class="section-heading reveal reveal-delay-1">The Untold Stories of Japan</h2>
      <p class="about-text reveal reveal-delay-2">
        Samurai Chronicles brings you the untold stories
        of Japan's <strong>2,600-year history</strong> — wars, betrayals,
        forgotten heroes, and legendary warriors.
        Produced in the style of BBC and Netflix documentaries.
        New episodes every day.
      </p>
      <div class="about-pillars">
        <div class="pillar reveal reveal-delay-1">
          <div class="pillar-icon">⚔️</div>
          <p class="pillar-label">Battles</p>
          <p class="pillar-desc">The decisive clashes that forged a nation</p>
        </div>
        <div class="pillar reveal reveal-delay-2">
          <div class="pillar-icon">🏯</div>
          <p class="pillar-label">Warriors</p>
          <p class="pillar-desc">Legendary samurai and their forgotten stories</p>
        </div>
        <div class="pillar reveal reveal-delay-3">
          <div class="pillar-icon">📜</div>
          <p class="pillar-label">Betrayals</p>
          <p class="pillar-desc">The plots and conspiracies that changed history</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ─── EPISODES ─── -->
  <section class="episodes" id="episodes">
    <div class="section-inner">
      <p class="section-label reveal">Episodes</p>
      <h2 class="section-heading reveal reveal-delay-1">Latest Stories</h2>
      <div class="episodes-grid">
{cards_html}
      </div>
    </div>
  </section>

  <!-- ─── FOLLOW ─── -->
  <section class="follow" id="follow">
    <div class="section-inner">
      <p class="section-label reveal">Follow</p>
      <h2 class="section-heading reveal reveal-delay-1">Watch & Follow</h2>
      <div class="follow-box reveal reveal-delay-2">
        <span class="follow-box-label">Samurai Chronicles</span>
        <p class="follow-intro">
          New episodes released every day.<br>
          Subscribe so you never miss a story.
        </p>
        <div class="sns-list">
          <a class="sns-link" href="{CHANNEL_URL}" target="_blank" rel="noopener">
            <svg class="sns-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
            </svg>
            <span class="sns-name">YouTube</span>
            <span class="sns-badge">Subscribe</span>
          </a>
        </div>
      </div>
    </div>
  </section>

  <!-- ─── FOOTER ─── -->
  <footer>
    <p class="footer-logo-text">SAMURAI CHRONICLES</p>
    <div class="footer-links">
      <a class="footer-link" href="{CHANNEL_URL}" target="_blank" rel="noopener">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
        </svg>
        YouTube
      </a>
      <a class="footer-link" href="#episodes">Episodes</a>
      <a class="footer-link" href="#about">About</a>
    </div>
    <p class="footer-copy">&copy; 2026 Samurai Chronicles. All rights reserved.</p>
  </footer>

  <script>
    const observer = new IntersectionObserver((entries) => {{
      entries.forEach(entry => {{
        if (entry.isIntersecting) {{
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }}
      }});
    }}, {{ threshold: 0.1, rootMargin: '0px 0px -40px 0px' }});
    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
  </script>

</body>
</html>"""

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"  ✓ index.html を生成しました（エピソード数: {ep_count}）")


if __name__ == "__main__":
    build()
