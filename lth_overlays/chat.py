"""Twitch ir YouTube chat skaitymas (be prisijungimo, be API raktų).

Twitch: anoniminis IRC (justinfan) per TLS - oficialiai palaikomas tik skaitymui.
YouTube: tas pats vidinis API, kurį naudoja youtube.com „Popout chat“ langas. Raktas nereikalingas,
bet YouTube gali jį pakeisti - tada reikės atnaujinti programą (rodoma būsena „YouTube: error“).

Gijos veikia tik kol kas nors (Chat valdiklis ekrane ar OBS) skaito žinutes - po 30 s be
skaitymo jos pačios sustoja.
"""
from __future__ import annotations

import collections
import json
import random
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

IDLE_STOP_S = 30.0
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


class ChatMsg(tuple):
    """(id, laikas, platforma 't'/'y', autorius, autoriaus id, spalva '#rrggbb' arba '', tekstas, rūšis)"""
    __slots__ = ()

    def __new__(cls, mid, ts, platform, author, author_id, color, text, kind="msg"):
        return tuple.__new__(cls, (mid, ts, platform, author, author_id, color, text, kind))

    mid = property(lambda s: s[0])
    ts = property(lambda s: s[1])
    platform = property(lambda s: s[2])
    author = property(lambda s: s[3])
    author_id = property(lambda s: s[4])
    color = property(lambda s: s[5])
    text = property(lambda s: s[6])
    kind = property(lambda s: s[7])


# ====================================================================== Twitch
def twitch_channel(value: str) -> str:
    """'https://twitch.tv/Name', '#name', 'name' -> 'name'."""
    v = (value or "").strip()
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]{2,25})", v)
    if m:
        v = m.group(1)
    v = v.lstrip("#@").strip().lower()
    return v if re.fullmatch(r"[a-z0-9_]{2,25}", v) else ""


def _unescape_tag(v: str) -> str:
    return (v.replace("\\s", " ").replace("\\:", ";").replace("\\r", "\r").replace("\\n", "\n")
            .replace("\\\\", "\\"))


def parse_irc(line: str):
    """IRC eilutė -> (tags, prefix, command, params, trailing)."""
    tags = {}
    if line.startswith("@"):
        raw, _, line = line[1:].partition(" ")
        for kv in raw.split(";"):
            k, _, v = kv.partition("=")
            tags[k] = _unescape_tag(v)
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    trailing = None
    if " :" in line:
        line, _, trailing = line.partition(" :")
    parts = line.split()
    cmd = parts[0] if parts else ""
    return tags, prefix, cmd, parts[1:], trailing


def twitch_event(line: str):
    """-> ('msg', ChatMsg) | ('del', msg_id) | ('clear_user', user_id) | ('clear', None) | ('ping', arg) | None"""
    tags, prefix, cmd, params, trailing = parse_irc(line)
    if cmd == "PING":
        return ("ping", trailing or (params[0] if params else "tmi.twitch.tv"))
    if cmd == "PRIVMSG" and trailing is not None:
        nick = prefix.split("!")[0]
        text = trailing
        kind = "msg"
        if text.startswith("\x01ACTION ") and text.endswith("\x01"):
            text, kind = text[8:-1], "action"
        name = tags.get("display-name") or nick
        mid = tags.get("id") or f"t{time.time_ns()}"
        return ("msg", ChatMsg(mid, time.time(), "t", name, tags.get("user-id", nick), tags.get("color", ""),
                               text, kind))
    if cmd == "CLEARMSG":
        return ("del", tags.get("target-msg-id", ""))
    if cmd == "CLEARCHAT":
        uid = tags.get("target-user-id")
        return ("clear_user", uid) if uid else ("clear", None)
    return None


# ====================================================================== YouTube
def youtube_target(value: str):
    """-> ('video', id) | ('channel', url) | None"""
    v = (value or "").strip()
    if not v:
        return None
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", v)
    if m:
        return ("video", m.group(1))
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", v) and not v.startswith("@"):
        return ("video", v)
    m = re.search(r"youtube\.com/((?:@|channel/|c/|user/)[^/?#\s]+)", v)
    if m:
        return ("channel", f"https://www.youtube.com/{m.group(1)}/live")
    if v.startswith("@"):
        return ("channel", f"https://www.youtube.com/{v}/live")
    return None


def _runs_text(msg: dict) -> str:
    out = []
    for r in (msg or {}).get("runs", []):
        if "text" in r:
            out.append(r["text"])
        elif "emoji" in r:
            e = r["emoji"]
            sc = e.get("shortcuts") or []
            eid = e.get("emojiId", "")
            out.append(eid if len(eid) <= 2 else (sc[0] if sc else ""))
    return "".join(out)


def youtube_events(actions: list) -> list:
    """YouTube 'actions' -> [('msg', ChatMsg) | ('del', id) | ('clear_user', channel_id)]"""
    out = []
    for a in actions or []:
        a = a.get("replayChatItemAction", {}).get("actions", [a])[0] if "replayChatItemAction" in a else a
        add = a.get("addChatItemAction")
        if add:
            item = add.get("item", {})
            for key, kind in (("liveChatTextMessageRenderer", "msg"), ("liveChatPaidMessageRenderer", "paid"),
                              ("liveChatMembershipItemRenderer", "member")):
                r = item.get(key)
                if not r:
                    continue
                text = _runs_text(r.get("message"))
                if kind == "paid":
                    amount = (r.get("purchaseAmountText") or {}).get("simpleText", "")
                    text = f"{amount}  {text}".strip()
                elif kind == "member":
                    text = _runs_text(r.get("headerSubtext")) or text
                ts = int(r.get("timestampUsec", 0) or 0) / 1e6 or time.time()
                out.append(("msg", ChatMsg(r.get("id", f"y{time.time_ns()}"), ts, "y",
                                           (r.get("authorName") or {}).get("simpleText", "?"),
                                           r.get("authorExternalChannelId", ""), "", text, kind)))
            continue
        rem = a.get("removeChatItemAction")
        if rem:
            out.append(("del", rem.get("targetItemId", "")))
            continue
        rem = a.get("removeChatItemByAuthorAction")
        if rem:
            out.append(("clear_user", rem.get("externalChannelId", "")))
    return out


def _yt_continuation(cont_list) -> tuple[str, int]:
    for c in cont_list or []:
        for key in ("invalidationContinuationData", "timedContinuationData", "reloadContinuationData"):
            d = c.get(key)
            if d and d.get("continuation"):
                return d["continuation"], int(d.get("timeoutMs", 4000) or 4000)
    return "", 4000


def _initial_data(html: str):
    m = re.search(r"(?:window\[\"ytInitialData\"\]|var ytInitialData)\s*=\s*", html)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
        return data
    except ValueError:
        return None


def parse_live_chat_page(html: str):
    """Popout chat puslapis -> (api_key, client_version, continuation, pradinės actions)."""
    key = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION"\s*:\s*"([^"]+)"', html) or \
        re.search(r'"clientVersion"\s*:\s*"([^"]+)"', html)
    data = _initial_data(html) or {}
    lcr = (data.get("contents", {}).get("liveChatRenderer") or {})
    cont, _ = _yt_continuation(lcr.get("continuations"))
    if not cont:
        m = re.search(r'"continuation"\s*:\s*"([^"]+)"', html)
        cont = m.group(1) if m else ""
    return (key.group(1) if key else "", ver.group(1) if ver else "2.20240101.00.00", cont,
            lcr.get("actions") or [])


# ====================================================================== centras
class ChatHub:
    def __init__(self):
        self._lock = threading.Lock()
        self.messages = collections.deque(maxlen=200)
        self.seq = 0
        self.status = {"t": "", "y": ""}
        self._cfg = ("", "")
        self._threads = {}
        self._stop = {}
        self._touch = 0.0

    # ---- valdikliams (UI gija) ----
    def configure(self, twitch: str, youtube: str):
        cfg = (twitch_channel(twitch), (youtube or "").strip())
        if cfg == self._cfg:
            return
        self._cfg = cfg
        for ev in self._stop.values():
            ev.set()
        self._threads.clear()
        self._stop.clear()
        with self._lock:
            self.status = {"t": "", "y": ""}
            self.messages.clear()
            self.seq += 1

    def touch(self):
        self._touch = time.monotonic()
        tw, yt = self._cfg
        for plat, val, target in (("t", tw, self._run_twitch), ("y", yt, self._run_youtube)):
            th = self._threads.get(plat)
            if val and (th is None or not th.is_alive()):
                ev = threading.Event()
                th = threading.Thread(target=target, args=(val, ev), name=f"lth-chat-{plat}", daemon=True)
                self._stop[plat] = ev
                self._threads[plat] = th
                th.start()

    def snapshot(self, n: int):
        with self._lock:
            return self.seq, list(self.messages)[-n:], dict(self.status)

    def stop(self):
        for ev in self._stop.values():
            ev.set()

    # ---- gijoms ----
    def _apply(self, events, plat=None, ev=None):
        if not events or (ev is not None and self._stop.get(plat) is not ev):
            return
        with self._lock:
            for kind, v in events:
                if kind == "msg":
                    self.messages.append(v)
                elif kind == "del":
                    keep = [m for m in self.messages if m.mid != v]
                    self.messages.clear()
                    self.messages.extend(keep)
                elif kind == "clear_user":
                    keep = [m for m in self.messages if m.author_id != v]
                    self.messages.clear()
                    self.messages.extend(keep)
                elif kind == "clear":
                    self.messages.clear()
            self.seq += 1

    def _set_status(self, plat, text, ev=None):
        if ev is not None and self._stop.get(plat) is not ev:
            return  # sena (perkonfigūruota) gija
        with self._lock:
            if self.status.get(plat) != text:
                self.status[plat] = text
                self.seq += 1

    def _alive(self, ev) -> bool:
        return not ev.is_set() and time.monotonic() - self._touch < IDLE_STOP_S

    # ---- Twitch ----
    def _run_twitch(self, channel, ev):
        backoff = 2.0
        while self._alive(ev):
            self._set_status("t", "connecting", ev)
            try:
                raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=15)
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
                sock.settimeout(1.0)
                nick = f"justinfan{random.randint(10000, 99999)}"
                sock.sendall(f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\nPASS SCHMOOPIIE\r\nNICK {nick}\r\n"
                             f"JOIN #{channel}\r\n".encode())
                buf = b""
                last_rx = time.monotonic()
                joined = False
                while self._alive(ev):
                    try:
                        chunk = sock.recv(8192)
                        if not chunk:
                            raise ConnectionError("closed")
                        buf += chunk
                        last_rx = time.monotonic()
                    except (socket.timeout, TimeoutError):
                        if time.monotonic() - last_rx > 330:
                            raise ConnectionError("timeout")
                        continue
                    *lines, buf = buf.split(b"\r\n")
                    events = []
                    for ln in lines:
                        s = ln.decode("utf-8", "replace")
                        if not joined and " JOIN #" in s:
                            joined = True
                            backoff = 2.0
                            self._set_status("t", "live", ev)
                        e = twitch_event(s)
                        if e is None:
                            continue
                        if e[0] == "ping":
                            sock.sendall(f"PONG :{e[1]}\r\n".encode())
                        else:
                            events.append(e)
                    self._apply(events, "t", ev)
                sock.close()
            except (OSError, ConnectionError, ssl.SSLError) as e:
                self._set_status("t", f"offline ({type(e).__name__}), retrying", ev)
                ev.wait(backoff)
                backoff = min(60.0, backoff * 2)
        self._set_status("t", "", ev)

    # ---- YouTube ----
    @staticmethod
    def _http(url, data=None, timeout=15) -> str:
        headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                   "Cookie": "CONSENT=YES+cb; SOCS=CAI"}  # ES sutikimo puslapis
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def _resolve_video(self, target) -> str:
        kind, v = target
        if kind == "video":
            return v
        html = self._http(v)
        m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', html)
        if m:
            return m.group(1)
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})".{0,400}?"isLive":true', html)
        return m.group(1) if m else ""

    def _run_youtube(self, value, ev):
        target = youtube_target(value)
        if target is None:
            self._set_status("y", "invalid link", ev)
            return
        backoff = 5.0
        while self._alive(ev):
            try:
                self._set_status("y", "connecting", ev)
                vid = self._resolve_video(target)
                if not vid:
                    self._set_status("y", "not live", ev)
                    ev.wait(30)
                    continue
                html = self._http(f"https://www.youtube.com/live_chat?is_popout=1&v={vid}")
                key, ver, cont, actions = parse_live_chat_page(html)
                if not cont:
                    self._set_status("y", "chat not available", ev)
                    ev.wait(30)
                    continue
                self._apply(youtube_events(actions)[-30:], "y", ev)
                self._set_status("y", "live", ev)
                backoff = 5.0
                url = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false" + \
                      (f"&key={urllib.parse.quote(key)}" if key else "")
                while self._alive(ev) and cont:
                    data = json.loads(self._http(url, {"context": {"client": {"clientName": "WEB",
                                                                              "clientVersion": ver}},
                                                       "continuation": cont}))
                    lcc = data.get("continuationContents", {}).get("liveChatContinuation", {})
                    self._apply(youtube_events(lcc.get("actions")), "y", ev)
                    cont, wait_ms = _yt_continuation(lcc.get("continuations"))
                    ev.wait(max(1.0, min(8.0, wait_ms / 1000.0)))
                if self._alive(ev):
                    self._set_status("y", "stream ended", ev)
                    ev.wait(30)
            except (OSError, urllib.error.URLError, ValueError) as e:
                self._set_status("y", f"error ({type(e).__name__}), retrying", ev)
                ev.wait(backoff)
                backoff = min(120.0, backoff * 2)
        self._set_status("y", "", ev)


DEMO = (("t", "Kartingas", "#9147ff", "Nice save in T3!"),
        ("y", "Marius R.", "", "what tyres are you on?"),
        ("t", "lth_fan", "#ecbe58", "LTH LTH LTH"),
        ("t", "PitWall", "#1e90ff", "Gap to P3 is coming down, push"),
        ("y", "Ieva", "", "Labas is Kauno!"),
        ("t", "slowcorner", "#00c87a", "that overtake was clean"))


def demo_messages() -> list:
    now = time.time()
    return [ChatMsg(f"demo{i}", now - (len(DEMO) - i) * 4, p, a, a, c, t)
            for i, (p, a, c, t) in enumerate(DEMO)]
