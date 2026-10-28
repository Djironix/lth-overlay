"""OBS / naršyklės šaltinis: kiekvienas overlay kaip atskiras Browser Source.

Paprastas HTTP serveris tik 127.0.0.1 (niekas iš tinklo neprieina, Windows ugniasienė neklausia).
Kadrai piešiami UI gijoje atskiromis (niekada nerodomomis) valdiklių kopijomis - tik tų valdiklių,
kuriuos OBS tuo metu prašo, todėl išjungtas OBS nieko nekainuoja. PNG išlaiko permatomumą.

URL:
  /                      sąrašas su nuorodomis
  /w/<valdiklis>         vienas valdiklis (Browser Source dydis = valdiklio dydis)
  /layout?screen=0       visas išdėstymas pagal monitorių (Browser Source = monitoriaus rezoliucija)
  /f/<valdiklis>.png     paskutinis kadras (have=<seq>: 204, jei nepasikeitė)
  /layout.json           valdiklių padėtys
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Qt, QTimer

from .registry import BY_NAME, WIDGETS

DEFAULT_PORT = 8399
IDLE_S = 3.0  # tiek sekundžių be užklausų - valdiklio kadrai nebepiešiami
BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360606060000000050001"
    "a5f645400000000049454e44ae426082")  # 1x1 permatomas

PAGE_ONE = """<!doctype html><html><head><meta charset="utf-8"><title>LTH %(title)s</title>
<style>html,body{margin:0;background:transparent;overflow:hidden}img{display:block;image-rendering:auto}</style>
</head><body><img id="i" alt=""><script>
const name=%(name)s, iv=%(iv)d; let seq=-1, last=null; const img=document.getElementById('i');
async function loop(){
  try{
    const r=await fetch('/f/'+name+'.png?have='+seq+'%(demo)s',{cache:'no-store'});
    if(r.status===200){ seq=+(r.headers.get('X-Seq')||0); const u=URL.createObjectURL(await r.blob());
      img.onload=()=>{ if(last) URL.revokeObjectURL(last); last=u; }; img.src=u; }
  }catch(e){ await new Promise(s=>setTimeout(s,1500)); }
  setTimeout(loop, iv);
}
loop();
</script></body></html>"""

PAGE_LAYOUT = """<!doctype html><html><head><meta charset="utf-8"><title>LTH layout</title>
<style>html,body{margin:0;background:transparent;overflow:hidden;width:100vw;height:100vh}
img{position:absolute;display:block}</style></head><body><script>
const screen_i=%(screen)d, iv=%(iv)d, demo=%(demo)s; const els={};
function frameLoop(name){
  const st={seq:-1,last:null};
  async function loop(){
    const el=els[name]; if(!el) return;
    try{
      const r=await fetch('/f/'+name+'.png?have='+st.seq+(demo?'&demo=1':''),{cache:'no-store'});
      if(r.status===200){ st.seq=+(r.headers.get('X-Seq')||0); const u=URL.createObjectURL(await r.blob());
        el.onload=()=>{ if(st.last) URL.revokeObjectURL(st.last); st.last=u; }; el.src=u; }
    }catch(e){ await new Promise(s=>setTimeout(s,1500)); }
    setTimeout(loop, iv);
  }
  loop();
}
async function layout(){
  try{
    const r=await fetch('/layout.json?screen='+screen_i,{cache:'no-store'}); const L=await r.json();
    const seen=new Set();
    for(const w of L.widgets){
      seen.add(w.name);
      let el=els[w.name];
      if(!el){ el=document.createElement('img'); document.body.appendChild(el); els[w.name]=el; frameLoop(w.name); }
      el.style.left=w.x+'px'; el.style.top=w.y+'px';
    }
    for(const n of Object.keys(els)){ if(!seen.has(n)){ els[n].remove(); delete els[n]; } }
  }catch(e){}
  setTimeout(layout, 1000);
}
layout();
</script></body></html>"""


def _index_html(server) -> str:
    rows = []
    for spec in WIDGETS:
        url = f"{server.base_url()}/w/{spec.name}"
        rows.append(f'<tr><td>{spec.title}</td><td><a href="/w/{spec.name}?demo=1">{url}</a></td></tr>')
    screens = "".join(f'<li><a href="/layout?screen={i}&demo=1">{server.base_url()}/layout?screen={i}</a> '
                      f'({n}, {r[2]}x{r[3]})</li>' for i, (n, r) in enumerate(server.screens_info()))
    return ("<!doctype html><html><head><meta charset='utf-8'><title>LTH Overlays for OBS</title><style>"
            "body{font-family:system-ui,sans-serif;background:#15171c;color:#e7e7ea;margin:32px}"
            "a{color:#ecbe58}td{padding:4px 14px 4px 0}h1{font-size:20px}</style></head><body>"
            "<h1>LTH Overlays - OBS browser sources</h1>"
            "<p>In OBS add a <b>Browser</b> source and paste a URL. Add <code>?demo=1</code> to see sample data "
            "while iRacing is not running.</p><h2>Whole layout (one source per monitor)</h2><ul>"
            f"{screens}</ul><h2>Single widgets</h2><table>{''.join(rows)}</table></body></html>")


class _Handler(BaseHTTPRequestHandler):
    server_version = "LTH"
    obs = None  # ObsServer

    def log_message(self, *a):  # tylus
        pass

    def _send(self, code, body: bytes = b"", ctype="text/html; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        obs = self.obs
        u = urlparse(self.path)
        q = parse_qs(u.query)
        demo = q.get("demo", ["0"])[0] == "1"
        path = u.path.rstrip("/") or "/"
        try:
            if path == "/":
                return self._send(200, _index_html(obs).encode())
            if path.startswith("/f/") and path.endswith(".png"):
                name = path[3:-4]
                if name not in BY_NAME:
                    return self._send(404, b"unknown widget", "text/plain")
                have = int(q.get("have", ["-1"])[0] or -1)
                seq, png = obs.frame(name, demo)
                if png is None or seq == have:
                    return self._send(204)
                return self._send(200, png, "image/png", {"X-Seq": str(seq),
                                                          "Access-Control-Expose-Headers": "X-Seq"})
            if path.startswith("/w/"):
                name = path[3:]
                if name not in BY_NAME:
                    return self._send(404, b"unknown widget", "text/plain")
                html = PAGE_ONE % {"title": BY_NAME[name].title, "name": json.dumps(name),
                                   "iv": obs.interval_ms(), "demo": "&demo=1" if demo else ""}
                return self._send(200, html.encode())
            if path == "/layout":
                scr = int(q.get("screen", ["0"])[0] or 0)
                html = PAGE_LAYOUT % {"screen": scr, "iv": obs.interval_ms(), "demo": "true" if demo else "false"}
                return self._send(200, html.encode())
            if path == "/layout.json":
                scr = int(q.get("screen", ["0"])[0] or 0)
                return self._send(200, json.dumps(obs.layout(scr)).encode(), "application/json")
            return self._send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            try:
                self._send(500, str(e).encode(), "text/plain")
            except OSError:
                pass


class ObsServer(QObject):
    """HTTP gija + UI laikmatis, piešiantis prašomus valdiklius."""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._lock = threading.Lock()
        self._frames = {}  # (name, demo) -> (seq, png)
        self._wanted = {}  # (name, demo) -> paskutinės užklausos laikas
        self._inst = {}  # name -> nematomas valdiklis
        self._state = {}  # (name, demo) -> paskutinis turinio raktas
        self._seq = 0
        self._layout = {}  # screen -> dict
        self._httpd = None
        self._thread = None
        self.error = ""
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)

    # ---- nustatymai ----
    @property
    def cfg(self) -> dict:
        return self.ctx.config.data.setdefault("obs", {"enabled": False, "port": DEFAULT_PORT, "fps": 30})

    def port(self) -> int:
        return int(self.cfg.get("port", DEFAULT_PORT) or DEFAULT_PORT)

    def fps(self) -> int:
        return max(5, min(60, int(self.cfg.get("fps", 30) or 30)))

    def interval_ms(self) -> int:
        return int(1000 / self.fps())

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port()}"

    def running(self) -> bool:
        return self._httpd is not None

    # ---- paleidimas ----
    def apply(self):
        """Įjungia / išjungia pagal nustatymus (port pakeitus - perkrauna)."""
        want = bool(self.cfg.get("enabled"))
        if self.running() and (not want or self._httpd.server_address[1] != self.port()):
            self.stop()
        if want and not self.running():
            self.start()
        if self.running():
            self.timer.setInterval(self.interval_ms())

    def start(self) -> bool:
        handler = type("Handler", (_Handler,), {"obs": self})
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port()), handler)
        except OSError as e:
            self._httpd = None
            self.error = f"Port {self.port()} is busy ({e.strerror or e}). Pick another port."
            return False
        self._httpd.daemon_threads = True
        self.error = ""
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="lth-obs", daemon=True)
        self._thread.start()
        self._refresh_layout()
        self.timer.start(self.interval_ms())
        return True

    def stop(self):
        self.timer.stop()
        if self._httpd is not None:
            httpd, self._httpd = self._httpd, None
            threading.Thread(target=lambda: (httpd.shutdown(), httpd.server_close()), daemon=True).start()
        for w in self._inst.values():
            w.deleteLater()
        self._inst.clear()
        with self._lock:
            self._frames.clear()
            self._wanted.clear()
        self._state.clear()

    # ---- HTTP gijai (tik su užraktu) ----
    def frame(self, name: str, demo: bool):
        key = (name, demo)
        with self._lock:
            self._wanted[key] = time.monotonic()
            return self._frames.get(key, (0, None))

    def layout(self, screen: int) -> dict:
        with self._lock:
            return self._layout.get(screen) or {"widgets": [], "width": 1920, "height": 1080}

    def screens_info(self):
        with self._lock:
            return list(self._screens) if hasattr(self, "_screens") else []

    # ---- UI gija ----
    def _refresh_layout(self):
        screens = self.ctx.screens()
        out = {}
        for i, (name, rect) in enumerate(screens):
            items = []
            for spec in WIDGETS:
                c = self.ctx.config.widget(spec.name)
                if not c.get("visible"):
                    continue
                live = self.ctx.widgets.get(spec.name)
                if live is None:
                    continue
                g = live.geometry()
                sr = self.ctx.screen_for_rect(g) if hasattr(self.ctx, "screen_for_rect") else None
                if sr is None or sr != rect:
                    continue
                items.append({"name": spec.name, "x": g.x() - rect.x(), "y": g.y() - rect.y()})
            out[i] = {"widgets": items, "width": rect.width(), "height": rect.height()}
        with self._lock:
            self._layout = out
            self._screens = [(n, (r.x(), r.y(), r.width(), r.height())) for n, r in screens]

    def _widget(self, name):
        w = self._inst.get(name)
        if w is None:
            w = BY_NAME[name].load()(self.ctx)
            w.preview_mode = True  # be greito laikmačio ir redagavimo rėmelio - kadrus piešiam patys
            w.obs_mode = True
            self._inst[name] = w
        return w

    def _tick(self):
        now = time.monotonic()
        with self._lock:
            wanted = [k for k, t in self._wanted.items() if now - t < IDLE_S]
            for k in [k for k, t in self._wanted.items() if now - t >= IDLE_S]:
                self._wanted.pop(k, None)
                self._frames.pop(k, None)
                self._state.pop(k, None)
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % max(1, self.fps()) == 0:
            self._refresh_layout()
        if not wanted:
            return
        live = self.ctx.engine.latest
        for name, demo in wanted:
            snap = live
            if not snap.connected and not getattr(BY_NAME[name].load(), "OBS_ALWAYS", False):
                if not demo:
                    self._store((name, demo), ("blank",), None)
                    continue
                snap = self.ctx.preview_snapshot()
            try:
                self._render(name, demo, snap)
            except Exception:  # noqa: BLE001 - vienas valdiklis neturi sustabdyti kitų
                pass

    def _render(self, name, demo, snap):
        w = self._widget(name)
        if w.obs_demo != demo:
            w.obs_demo = demo
            w._key = object()
        w.push(snap)
        changed = False
        if w.FAST_CAPABLE and snap.connected and w.cfg.get("smooth", True):
            timing = w.fast_source()
            if timing is not None:
                changed = bool(w.fast_tick(timing))
        width = w.target_width()
        h = w.final_height()
        if w.width() != width or w.height() != h:
            w.resize(width, h)
        key = (w._key, width, h, self.ctx.theme, demo)
        if not changed and self._state.get((name, demo)) == key:
            return
        self._state[(name, demo)] = key
        img = w.grab().toImage()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG", 85)  # greitesnis suspaudimas (dydis lokaliai nesvarbus)
        buf.close()
        self._store((name, demo), key, bytes(ba.data()))

    def _store(self, key, state, png):
        with self._lock:
            old = self._frames.get(key)
            if png is None:
                if old is not None and old[1] == BLANK_PNG:
                    return
                png = BLANK_PNG
            self._seq += 1
            self._frames[key] = (self._seq, png)

    def all_widgets_changed(self):
        for w in self._inst.values():
            w.apply_settings()
        self._state.clear()
