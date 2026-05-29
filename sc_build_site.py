"""
sc_build_site.py — Samurai Chronicles 公式サイト生成

生成ファイル:
  index.html      トップページ（新着 + About + Subscribe）
  episodes.html   全エピソード一覧
  playlists.html  キャラクター別再生リスト

使い方:
  python3 sc_build_site.py

/sc-upload 後に自動実行。
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
CHAR_PLAYLISTS_JSON = BASE_DIR / "character_playlists.json"
CHANNEL_URL = "https://www.youtube.com/@Samurai-Chronicles-JP"

# ──────────────────────────────────────────────
# データ読み込み
# ──────────────────────────────────────────────

def is_published(ep: dict) -> bool:
    """scheduled_at が現在時刻より過去なら公開済みとみなす（JST=UTC+9）。"""
    s = ep.get("scheduled_at", "")
    if not s:
        return True
    try:
        from datetime import timedelta
        dt_jst = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        dt_utc = dt_jst.replace(tzinfo=timezone.utc) - timedelta(hours=9)
        return datetime.now(timezone.utc) >= dt_utc
    except Exception:
        return True


def load_episodes() -> list[dict]:
    eps = []
    for p in sorted(EPISODES_DIR.glob("ep[0-9]*.json")):
        if p.stat().st_size == 0:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not (d.get("youtube_title") or d.get("episode_title")):
            continue
        if not is_published(d):
            continue
        eps.append(d)
    eps.reverse()  # 最新順
    return eps


def load_playlists() -> list[dict]:
    if not CHAR_PLAYLISTS_JSON.exists():
        return []
    data = json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
    result = []
    for char, info in data.items():
        if not info.get("playlist_id"):
            continue
        result.append({
            "char": char,
            "display_name": info["display_name"],
            "playlist_id": info["playlist_id"],
            "episodes": info["episodes"],
        })
    result.sort(key=lambda x: len(x["episodes"]), reverse=True)
    return result


def video_id(ep: dict) -> str:
    url = ep.get("youtube_url", "")
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else ""


def thumb_html(ep: dict, fallback: str) -> str:
    """YouTube サムネイル img タグ（video_id がなければフォールバック span）。"""
    vid = video_id(ep)
    if vid:
        return f'<img src="https://img.youtube.com/vi/{vid}/mqdefault.jpg" alt="" loading="lazy">'
    return f'<span class="episode-thumb-num">{fallback}</span>'


# ──────────────────────────────────────────────
# 共通パーツ
# ──────────────────────────────────────────────

COMMON_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --crimson: #8B0000; --crimson-dark: #5c0000; --crimson-light: #a80000;
      --gold: #C9A84C; --gold-light: #e0c068; --gold-dim: #9a7a38;
      --black: #1a1a1a; --black-soft: #222222;
      --white: #f5f0e8; --white-dim: #c8bfb0;
    }
    html { scroll-behavior: smooth; }
    body { background: var(--black); color: var(--white); font-family: 'EB Garamond', serif; overflow-x: hidden; }

    /* ── reveal ── */
    .reveal { opacity: 0; transform: translateY(28px); transition: opacity .7s ease, transform .7s ease; }
    .reveal.visible { opacity: 1; transform: none; }
    .reveal-delay-1 { transition-delay: .1s; }
    .reveal-delay-2 { transition-delay: .2s; }
    .reveal-delay-3 { transition-delay: .3s; }
    .reveal-delay-4 { transition-delay: .4s; }

    /* ── NAV ── */
    .site-nav {
      position: sticky; top: 0; z-index: 100;
      background: rgba(26,26,26,.95); backdrop-filter: blur(8px);
      border-bottom: 1px solid rgba(201,168,76,.2);
      padding: 0 24px; height: 56px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .nav-logo {
      font-family: 'Cinzel', serif; font-weight: 700; font-size: .85rem;
      letter-spacing: .15em; color: var(--gold); text-decoration: none;
    }
    .nav-links { display: flex; gap: 28px; }
    .nav-link {
      font-family: 'Cinzel', serif; font-size: .65rem; letter-spacing: .2em;
      color: var(--white-dim); text-decoration: none; text-transform: uppercase;
      transition: color .2s;
    }
    .nav-link:hover, .nav-link.active { color: var(--gold); }

    /* ── section base ── */
    section { padding: 80px 24px; }
    .section-inner { max-width: 900px; margin: 0 auto; }
    .section-label {
      font-family: 'Cinzel', serif; font-size: .65rem; letter-spacing: .3em;
      color: var(--gold); text-transform: uppercase; text-align: center; margin-bottom: 14px;
    }
    .section-heading {
      font-family: 'Cinzel', serif; font-weight: 700;
      font-size: clamp(1.4rem, 5vw, 2rem); text-align: center;
      letter-spacing: .06em; color: var(--white); margin-bottom: 40px;
    }
    .gold-rule {
      width: 80px; height: 1px;
      background: linear-gradient(to right, transparent, var(--gold), transparent);
      margin: 24px auto;
    }

    /* ── button ── */
    .btn-primary {
      display: inline-block; padding: 14px 32px;
      background: var(--crimson); border: 1px solid rgba(201,168,76,.5);
      color: var(--white); font-family: 'Cinzel', serif; font-weight: 600;
      font-size: .85rem; letter-spacing: .12em; text-decoration: none;
      border-radius: 2px; transition: all .3s; box-shadow: 0 4px 20px rgba(139,0,0,.4);
    }
    .btn-primary:hover {
      background: var(--crimson-light); border-color: var(--gold);
      color: var(--gold-light); transform: translateY(-2px);
      box-shadow: 0 6px 30px rgba(139,0,0,.6);
    }
    .btn-outline {
      display: inline-block; padding: 12px 28px;
      border: 1px solid rgba(201,168,76,.5); color: var(--gold);
      font-family: 'Cinzel', serif; font-size: .8rem; letter-spacing: .12em;
      text-decoration: none; border-radius: 2px; transition: all .3s;
    }
    .btn-outline:hover { background: rgba(201,168,76,.08); border-color: var(--gold); }

    /* ── stats strip ── */
    .stats-strip {
      background: var(--crimson-dark);
      border-top: 1px solid rgba(201,168,76,.25); border-bottom: 1px solid rgba(201,168,76,.25);
      padding: 28px 24px;
    }
    .stats-inner {
      max-width: 860px; margin: 0 auto;
      display: flex; justify-content: center; gap: clamp(32px,8vw,80px); flex-wrap: wrap;
    }
    .stat-item { text-align: center; }
    .stat-num {
      font-family: 'Cinzel', serif; font-weight: 700;
      font-size: clamp(1.6rem,5vw,2.2rem); color: var(--gold); line-height: 1;
    }
    .stat-label {
      font-family: 'Cinzel', serif; font-size: .6rem; letter-spacing: .2em;
      color: var(--white-dim); opacity: .75; margin-top: 6px; text-transform: uppercase;
    }

    /* ── episode card ── */
    .episodes-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: 20px;
    }
    .episode-card {
      display: block; text-decoration: none;
      background: var(--black-soft); border: 1px solid rgba(201,168,76,.2);
      border-radius: 3px; overflow: hidden; transition: all .3s;
    }
    .episode-card:hover {
      border-color: rgba(201,168,76,.5); transform: translateY(-4px);
      box-shadow: 0 12px 40px rgba(0,0,0,.5);
    }
    .episode-thumb {
      width: 100%; aspect-ratio: 16/9; background: #111;
      display: flex; align-items: center; justify-content: center;
      position: relative; overflow: hidden;
    }
    .episode-thumb img {
      width: 100%; height: 100%; object-fit: cover; display: block;
      transition: transform .4s, filter .4s; filter: brightness(.92);
    }
    .episode-card:hover .episode-thumb img { transform: scale(1.04); filter: brightness(1); }
    .episode-thumb-num {
      font-family: 'Cinzel', serif; font-weight: 700;
      font-size: clamp(1.8rem,5vw,2.6rem); color: rgba(201,168,76,.25); letter-spacing: .1em;
    }
    .episode-thumb::after {
      content: '▶'; position: absolute; font-size: 1.6rem;
      color: rgba(255,255,255,0); transition: color .3s, transform .3s;
      text-shadow: 0 2px 12px rgba(0,0,0,.8); pointer-events: none;
    }
    .episode-card:hover .episode-thumb::after { color: rgba(255,255,255,.9); transform: scale(1.15); }
    .episode-info { padding: 14px 16px; }
    .episode-num {
      font-family: 'Cinzel', serif; font-size: .58rem; letter-spacing: .2em;
      color: var(--gold-dim); margin-bottom: 6px;
    }
    .episode-title { font-size: .9rem; color: var(--white-dim); line-height: 1.5; }

    /* ── footer ── */
    footer {
      background: #111; border-top: 1px solid rgba(201,168,76,.2);
      padding: 40px 24px; text-align: center;
    }
    .footer-logo { font-family: 'Cinzel', serif; font-weight: 700; font-size: 1rem; letter-spacing: .12em; color: var(--gold); margin-bottom: 16px; }
    .footer-links { display: flex; justify-content: center; gap: 24px; margin-bottom: 20px; flex-wrap: wrap; }
    .footer-link { color: var(--white-dim); text-decoration: none; font-size: .85rem; transition: color .2s; }
    .footer-link:hover { color: var(--gold); }
    .footer-copy { font-family: 'Cinzel', serif; font-size: .62rem; letter-spacing: .18em; color: var(--white-dim); opacity: .4; }

    /* ── responsive ── */
    @media (max-width: 480px) {
      .episodes-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
      section { padding: 60px 20px; }
    }
    @media (max-width: 320px) { .episodes-grid { grid-template-columns: 1fr; } }
"""

COMMON_FONTS = """
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">"""

REVEAL_JS = """
  <script>
    const obs = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
  </script>"""


def nav_html(active: str) -> str:
    links = [("/", "Top"), ("/episodes", "Episodes"), ("/playlists", "Playlists")]
    items = ""
    for href, label in links:
        cls = ' class="nav-link active"' if label.lower() == active else ' class="nav-link"'
        items += f'<a{cls} href="{href}">{label.upper()}</a>'
    return f"""
  <nav class="site-nav">
    <a class="nav-logo" href="/">SAMURAI CHRONICLES</a>
    <div class="nav-links">{items}</div>
  </nav>"""


def footer_html() -> str:
    return f"""
  <footer>
    <p class="footer-logo">SAMURAI CHRONICLES</p>
    <div class="footer-links">
      <a class="footer-link" href="{CHANNEL_URL}" target="_blank" rel="noopener">YouTube</a>
      <a class="footer-link" href="/episodes">Episodes</a>
      <a class="footer-link" href="/playlists">Playlists</a>
    </div>
    <p class="footer-copy">&copy; 2026 Samurai Chronicles. All rights reserved.</p>
  </footer>"""


def head_html(title: str, desc: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:image" content="LOGO.PNG">{COMMON_FONTS}
  <style>{COMMON_CSS}</style>
</head>
<body>"""


# ──────────────────────────────────────────────
# index.html — トップ
# ──────────────────────────────────────────────

def build_index(episodes: list[dict], playlists: list[dict]):
    latest = episodes[0] if episodes else {}
    ep_count = len(episodes)
    pl_count = len(playlists)

    # 新着エピソードカード
    ep_num = latest.get("episode_id", "").replace("ep", "").lstrip("0") or "?"
    ep_title = latest.get("youtube_title") or latest.get("episode_title", "")
    ep_url = latest.get("youtube_url") or CHANNEL_URL
    vid = video_id(latest)
    thumb = f'<img src="https://img.youtube.com/vi/{vid}/mqdefault.jpg" alt="{ep_title}" loading="lazy" style="width:100%;height:100%;object-fit:cover;">' if vid else f'<span class="episode-thumb-num" style="font-size:clamp(2rem,8vw,4rem);">{ep_num}</span>'

    # 次の3件
    recent_cards = ""
    for i, ep in enumerate(episodes[1:4]):
        ep_n = ep.get("episode_id","").replace("ep","")
        t = thumb_html(ep, ep_n)
        u = ep.get("youtube_url") or CHANNEL_URL
        tl = ep.get("youtube_title") or ep.get("episode_title", "")
        delay = f" reveal-delay-{i+1}"
        recent_cards += f"""
        <a class="episode-card reveal{delay}" href="{u}" target="_blank" rel="noopener">
          <div class="episode-thumb">{t}</div>
          <div class="episode-info">
            <p class="episode-num">EPISODE {ep_n}</p>
            <p class="episode-title">{tl}</p>
          </div>
        </a>"""

    html = head_html(
        "Samurai Chronicles | 2,600 Years of Japanese History",
        "Samurai Chronicles brings you the untold stories of Japan's history — new episodes every day."
    )
    html += nav_html("top")
    html += f"""

  <!-- ── HERO ── -->
  <section style="min-height:100svh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 24px 80px;background:radial-gradient(ellipse at 50% 0%,rgba(139,0,0,.35) 0%,transparent 65%),var(--black);position:relative;">
    <div style="width:min(200px,50vw);height:min(200px,50vw);border-radius:50%;overflow:hidden;box-shadow:0 0 0 2px rgba(201,168,76,.4),0 0 0 4px rgba(139,0,0,.3),0 0 60px rgba(201,168,76,.15),0 20px 80px rgba(0,0,0,.7);animation:fadeInDown 1s ease both;position:relative;z-index:1;">
      <img src="LOGO.PNG" alt="Samurai Chronicles" style="width:100%;height:100%;object-fit:cover;display:block;">
    </div>
    <div style="margin-top:40px;animation:fadeInUp 1s .25s ease both;position:relative;z-index:1;">
      <div class="gold-rule"></div>
      <p style="font-family:'Cinzel',serif;font-size:clamp(1rem,4vw,1.3rem);letter-spacing:.05em;color:var(--white-dim);line-height:1.8;">
        <span style="color:var(--gold);font-style:normal;">2,600 years</span> of Japanese history,<br>told one untold story at a time.
      </p>
      <div class="gold-rule"></div>
    </div>
    <div style="margin-top:8px;animation:fadeInUp 1s .45s ease both;display:flex;gap:16px;flex-wrap:wrap;justify-content:center;">
      <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">Watch on YouTube &rarr;</a>
      <a class="btn-outline" href="/episodes">All Episodes</a>
    </div>
  </section>

  <!-- ── STATS ── -->
  <div class="stats-strip reveal">
    <div class="stats-inner">
      <div class="stat-item"><p class="stat-num">{ep_count}</p><p class="stat-label">Episodes</p></div>
      <div class="stat-item"><p class="stat-num">2,600</p><p class="stat-label">Years of History</p></div>
      <div class="stat-item"><p class="stat-num">{pl_count}</p><p class="stat-label">Playlists</p></div>
      <div class="stat-item"><p class="stat-num">Daily</p><p class="stat-label">New Episodes</p></div>
    </div>
  </div>

  <!-- ── NEW EPISODE ── -->
  <section style="background:var(--black-soft);border-top:1px solid rgba(201,168,76,.15);border-bottom:1px solid rgba(201,168,76,.15);">
    <div class="section-inner">
      <p class="section-label reveal">Latest</p>
      <h2 class="section-heading reveal reveal-delay-1">New Episode</h2>
      <div class="reveal reveal-delay-2" style="max-width:640px;margin:0 auto 40px;">
        <a href="{ep_url}" target="_blank" rel="noopener" style="display:block;border:1px solid rgba(201,168,76,.3);border-radius:4px;overflow:hidden;text-decoration:none;transition:all .3s;background:var(--black);" onmouseover="this.style.borderColor='rgba(201,168,76,.7)';this.style.transform='translateY(-4px)';this.style.boxShadow='0 12px 40px rgba(0,0,0,.5)'" onmouseout="this.style.borderColor='rgba(201,168,76,.3)';this.style.transform='';this.style.boxShadow=''">
          <div style="width:100%;aspect-ratio:16/9;background:#111;display:flex;align-items:center;justify-content:center;overflow:hidden;">{thumb}</div>
          <div style="padding:20px 24px;">
            <p style="font-family:'Cinzel',serif;font-size:.6rem;letter-spacing:.25em;color:var(--gold);margin-bottom:8px;">EPISODE {ep_num}</p>
            <p style="font-family:'Cinzel',serif;font-size:clamp(1rem,3vw,1.25rem);color:var(--white);line-height:1.5;">{ep_title}</p>
          </div>
        </a>
      </div>
      <h3 class="reveal" style="font-family:'Cinzel',serif;font-size:.75rem;letter-spacing:.25em;color:var(--white-dim);text-align:center;text-transform:uppercase;margin-bottom:24px;opacity:.7;">Recent Episodes</h3>
      <div class="episodes-grid" style="grid-template-columns:repeat(3,1fr);">{recent_cards}
      </div>
      <div class="reveal" style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-top:40px;">
        <a class="btn-outline" href="/episodes">View All Episodes &rarr;</a>
        <a class="btn-outline" href="/playlists">View Playlists &rarr;</a>
      </div>
    </div>
  </section>

  <!-- ── ABOUT ── -->
  <section style="background:var(--black);">
    <div class="section-inner">
      <p class="section-label reveal">About</p>
      <h2 class="section-heading reveal reveal-delay-1">The Untold Stories of Japan</h2>
      <p class="reveal reveal-delay-2" style="text-align:center;font-size:clamp(1rem,3vw,1.15rem);line-height:2;color:var(--white-dim);max-width:600px;margin:0 auto 48px;">
        Samurai Chronicles brings you the untold stories of Japan's
        <strong style="color:var(--gold);font-weight:500;font-style:italic;">2,600-year history</strong>
        — wars, betrayals, forgotten heroes, and legendary warriors.
        Produced in the style of BBC and Netflix documentaries. New episodes every day.
      </p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px;max-width:720px;margin:0 auto;">
        <div class="reveal reveal-delay-1" style="text-align:center;padding:24px 16px;border:1px solid rgba(201,168,76,.2);border-radius:3px;background:rgba(139,0,0,.06);">
          <div style="font-size:1.8rem;margin-bottom:12px;">⚔️</div>
          <p style="font-family:'Cinzel',serif;font-size:.7rem;letter-spacing:.2em;color:var(--gold);text-transform:uppercase;">Battles</p>
          <p style="font-size:.85rem;color:var(--white-dim);line-height:1.6;margin-top:8px;opacity:.8;">The decisive clashes that forged a nation</p>
        </div>
        <div class="reveal reveal-delay-2" style="text-align:center;padding:24px 16px;border:1px solid rgba(201,168,76,.2);border-radius:3px;background:rgba(139,0,0,.06);">
          <div style="font-size:1.8rem;margin-bottom:12px;">🏯</div>
          <p style="font-family:'Cinzel',serif;font-size:.7rem;letter-spacing:.2em;color:var(--gold);text-transform:uppercase;">Warriors</p>
          <p style="font-size:.85rem;color:var(--white-dim);line-height:1.6;margin-top:8px;opacity:.8;">Legendary samurai and their forgotten stories</p>
        </div>
        <div class="reveal reveal-delay-3" style="text-align:center;padding:24px 16px;border:1px solid rgba(201,168,76,.2);border-radius:3px;background:rgba(139,0,0,.06);">
          <div style="font-size:1.8rem;margin-bottom:12px;">📜</div>
          <p style="font-family:'Cinzel',serif;font-size:.7rem;letter-spacing:.2em;color:var(--gold);text-transform:uppercase;">Betrayals</p>
          <p style="font-size:.85rem;color:var(--white-dim);line-height:1.6;margin-top:8px;opacity:.8;">The plots and conspiracies that changed history</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ── SUBSCRIBE ── -->
  <section style="background:var(--black-soft);border-top:1px solid rgba(201,168,76,.15);">
    <div class="section-inner" style="text-align:center;">
      <p class="section-label reveal">Subscribe</p>
      <h2 class="section-heading reveal reveal-delay-1">Never Miss a Story</h2>
      <p class="reveal reveal-delay-2" style="color:var(--white-dim);line-height:1.9;margin-bottom:32px;">New episodes released every day. Subscribe so you never miss a story.</p>
      <div class="reveal reveal-delay-3">
        <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">
          Subscribe on YouTube &rarr;
        </a>
      </div>
    </div>
  </section>

  <style>
    @keyframes fadeInDown {{ from {{ opacity:0;transform:translateY(-24px); }} to {{ opacity:1;transform:none; }} }}
    @keyframes fadeInUp {{ from {{ opacity:0;transform:translateY(24px); }} to {{ opacity:1;transform:none; }} }}
  </style>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "index.html").write_text(html, encoding="utf-8")
    print("  ✓ index.html")


# ──────────────────────────────────────────────
# episodes.html — 全エピソード一覧
# ──────────────────────────────────────────────

def build_episodes(episodes: list[dict]):
    cards = ""
    for i, ep in enumerate(episodes):
        num = ep.get("episode_id", "").replace("ep", "")
        thumb = thumb_html(ep, num)
        url = ep.get("youtube_url") or CHANNEL_URL
        title = ep.get("youtube_title") or ep.get("episode_title", "")
        delay = f" reveal-delay-{(i % 4) + 1}" if (i % 4) != 0 else ""
        cards += f"""
        <a class="episode-card reveal{delay}" href="{url}" target="_blank" rel="noopener">
          <div class="episode-thumb">{thumb}</div>
          <div class="episode-info">
            <p class="episode-num">EPISODE {num}</p>
            <p class="episode-title">{title}</p>
          </div>
        </a>"""

    html = head_html(
        "Episodes | Samurai Chronicles",
        "All episodes of Samurai Chronicles — 2,600 years of Japanese history."
    )
    html += nav_html("episodes")
    html += f"""

  <section style="padding-top:60px;">
    <div class="section-inner">
      <p class="section-label reveal">All Episodes</p>
      <h1 class="section-heading reveal reveal-delay-1" style="font-size:clamp(1.4rem,5vw,2rem);">Every Story We've Told</h1>
      <div class="episodes-grid">{cards}
      </div>
    </div>
  </section>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "episodes.html").write_text(html, encoding="utf-8")
    print(f"  ✓ episodes.html（{len(episodes)}件）")


# ──────────────────────────────────────────────
# playlists.html — キャラクター別再生リスト
# ──────────────────────────────────────────────

def build_playlists(playlists: list[dict]):
    cards = ""
    for i, pl in enumerate(playlists):
        pl_url = f"https://www.youtube.com/playlist?list={pl['playlist_id']}"
        eps = pl["episodes"]
        ep_count = len(eps)
        # サムネイル: 最初の動画のサムネ
        first_vid = next((e["video_id"] for e in eps if e.get("video_id")), None)
        char_abbr = pl["display_name"].split()[0].upper()
        thumb = f'<img src="https://img.youtube.com/vi/{first_vid}/mqdefault.jpg" alt="{pl["display_name"]}" loading="lazy">' if first_vid else f'<span class="episode-thumb-num" style="font-size:1rem;letter-spacing:.05em;">{char_abbr}</span>'
        delay = f" reveal-delay-{(i % 4) + 1}" if (i % 4) != 0 else ""
        cards += f"""
        <a class="episode-card reveal{delay}" href="{pl_url}" target="_blank" rel="noopener">
          <div class="episode-thumb">{thumb}</div>
          <div class="episode-info">
            <p class="episode-num">{ep_count} EPISODE{'S' if ep_count != 1 else ''}</p>
            <p class="episode-title" style="font-family:'Cinzel',serif;font-size:.85rem;letter-spacing:.05em;">{pl["display_name"]}</p>
          </div>
        </a>"""

    if not playlists:
        cards = '<p style="text-align:center;color:var(--white-dim);opacity:.6;padding:40px 0;">No playlists yet. Coming soon.</p>'

    html = head_html(
        "Playlists | Samurai Chronicles",
        "Browse Samurai Chronicles by character — curated playlists for every legendary warrior."
    )
    html += nav_html("playlists")
    html += f"""

  <section style="padding-top:60px;">
    <div class="section-inner">
      <p class="section-label reveal">By Character</p>
      <h1 class="section-heading reveal reveal-delay-1" style="font-size:clamp(1.4rem,5vw,2rem);">Follow Every Warrior</h1>
      <p class="reveal reveal-delay-2" style="text-align:center;color:var(--white-dim);line-height:1.9;margin-bottom:48px;max-width:520px;margin-left:auto;margin-right:auto;">
        Each playlist follows one legendary figure across every episode they appear in.<br>Watch their full story from beginning to end.
      </p>
      <div class="episodes-grid">{cards}
      </div>
    </div>
  </section>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "playlists.html").write_text(html, encoding="utf-8")
    print(f"  ✓ playlists.html（{len(playlists)}件）")


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

def build():
    episodes = load_episodes()
    if not episodes:
        print("❌ エピソードが見つかりませんでした")
        sys.exit(1)
    playlists = load_playlists()

    print(f"  エピソード: {len(episodes)}件 / プレイリスト: {len(playlists)}件")
    build_index(episodes, playlists)
    build_episodes(episodes)
    build_playlists(playlists)
    print("  ✓ サイト生成完了")


if __name__ == "__main__":
    build()
