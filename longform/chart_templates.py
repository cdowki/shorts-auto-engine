# chart_templates.py — 긴 영상·숏폼 위 카드에 쓰는 도표 틀 13가지 (쇼츠창 2026-11-03)
# 10/20~11/3 블로그 43편 215구간을 세어 정한 틀: 13개로 97.7%를 덮음 (긴영상_설계와_인수인계 참고)
# 각 틀: draw(b, t, d) — b = 투명 층(1080x1920 RGBA), t = 장면 안 시각(초), d = 장면표의 chart 데이터
# 카드 영역: 가로 60~1020, 세로 110~610 (렌더러가 아래로 +30 옮겨 얹음)
# 요소는 d['times'](초 목록)가 있으면 그 시각에, 없으면 0.4초부터 d.get('gap', 1.0)초 간격으로 차례로 나타남
import math
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
FONT_B = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
NAVY = (36, 78, 120)
ORANGE = (240, 140, 50)
GRAY = (150, 160, 170)
DARK = (40, 48, 60)
WHITE = (255, 255, 255)
RED = (214, 84, 60)
GREEN = (46, 140, 90)
LIGHT = (235, 240, 245)
X0, X1, Y0, Y1 = 60, 1020, 110, 610
CX = 540
_fc = {}


def F(size, black=False):
    k = (size, black)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FONT_B if black else FONT, size, index=1)
    return _fc[k]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ap(t, start, dur=0.5):
    return ease((t - start) / dur)


def layer(w, h):
    im = Image.new('RGBA', (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def put(base, lay, x, y, alpha=1.0):
    if alpha <= 0:
        return
    if alpha < 1:
        a = lay.getchannel('A').point(lambda v: int(v * alpha))
        lay = lay.copy()
        lay.putalpha(a)
    base.alpha_composite(lay, (int(x), int(y)))


def fit(s, maxw, size, black=False, minsize=24):
    # 글자가 maxw 안에 들어갈 때까지 글자 크기를 줄임
    while size > minsize and F(size, black).getlength(s) > maxw:
        size -= 2
    return size


def text_layer(s, size, color, black=False, pad=6):
    f = F(size, black)
    bb = f.getbbox(s)
    im, d = layer(bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2)
    d.text((pad - bb[0], pad - bb[1]), s, font=f, fill=color + (255,))
    return im


def put_text(b, s, size, color, cx, y, t, start, black=False, slide=24, maxw=900, left=None):
    a = ap(t, start)
    if a <= 0:
        return
    size = fit(s, maxw, size, black)
    lay = text_layer(s, size, color, black)
    x = (cx - lay.width / 2) if left is None else left
    put(b, lay, x, y + (1 - a) * slide, a)


def pill(s, size, bg, fg, padx=26, pady=14, maxw=900):
    size = fit(s, maxw - padx * 2, size)
    f = F(size)
    bb = f.getbbox(s)
    w = bb[2] - bb[0] + padx * 2
    h = bb[3] - bb[1] + pady * 2
    im, d = layer(w, h)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg + (255,))
    d.text((padx - bb[0], pady - bb[1]), s, font=f, fill=fg + (255,))
    return im


def box(lines, w, h, border, fill=WHITE, sizes=None, colors=None, radius=26):
    im, d = layer(w, h)
    d.rounded_rectangle((3, 3, w - 4, h - 4), radius=radius, fill=fill + (255,), outline=border + (255,), width=6)
    sizes = list(sizes or [44] * len(lines))
    colors = colors or [DARK] * len(lines)
    sizes = [fit(s, w - 40, sz) for s, sz in zip(lines, sizes)]
    tot = sum(F(s).getbbox('가')[3] + 12 for s in sizes)
    y = (h - tot) / 2
    for s, sz, c in zip(lines, sizes, colors):
        f = F(sz)
        bb = f.getbbox(s)
        d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1] + 4), s, font=f, fill=c + (255,))
        y += f.getbbox('가')[3] + 12
    return im


def arrow(d, x1, y1, x2, y2, color, width=8, head=26):
    d.line((x1, y1, x2, y2), fill=color + (255,), width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    p1 = (x2 - head * math.cos(ang - 0.5), y2 - head * math.sin(ang - 0.5))
    p2 = (x2 - head * math.cos(ang + 0.5), y2 - head * math.sin(ang + 0.5))
    d.polygon([(x2, y2), p1, p2], fill=color + (255,))


def times(d, n, first=0.4):
    ts = d.get('times')
    if ts and len(ts) >= n:
        return ts[:n]
    g = d.get('gap', 1.0)
    return [first + k * g for k in range(n)]


def heading(b, t, d, y=Y0 + 14):
    # 틀 맨 위의 작은 제목(선택)
    if d.get('title'):
        put_text(b, d['title'], 46, DARK, CX, y, t, 0.05, black=True)
        return 100
    return 10


# ── 1. 체크목록: 번호 붙은 2~4줄 ─────────────────────
def t_checklist(b, t, d):
    top = Y0 + heading(b, t, d)
    items = d['items'][:4]
    ts = times(d, len(items))
    rowh = min(110, (Y1 - top) / len(items))
    top += max(0, (Y1 - top - rowh * len(items)) / 2)
    for i, (s, st) in enumerate(zip(items, ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        y = top + i * rowh + (1 - a) * 20
        c, cd = layer(66, 66)
        cd.ellipse((0, 0, 65, 65), fill=NAVY + (255,))
        cd.line((16, 34, 28, 46, 50, 20), fill=WHITE + (255,), width=8, joint='curve')
        put(b, c, 110, y + 4, a)
        size = fit(s, 760, 46)
        put(b, text_layer(s, size, DARK), 200, y + 2, a)


# ── 2. 숫자강조: 카드 1~4장, 이름 + 큰 숫자 ───────────────
def t_numbers(b, t, d):
    top = Y0 + heading(b, t, d)
    cards = d['cards'][:4]
    n = len(cards)
    ts = times(d, n)
    cols = 2 if n == 4 else n
    rows = 2 if n == 4 else 1
    gw = (X1 - X0 - 20 * (cols - 1)) / cols
    gh = min(250, (Y1 - top - 20 * (rows - 1)) / rows)
    for i, (c, st) in enumerate(zip(cards, ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        r, k = divmod(i, cols)
        x = X0 + k * (gw + 20)
        y = top + r * (gh + 20)
        col = ORANGE if c.get('hl') else NAVY
        im = box([c['label'], c['value']], int(gw), int(gh), col, sizes=[36, 74 if rows == 1 else 60], colors=[DARK, col])
        put(b, im, x, y + (1 - a) * 24, a)


# ── 3. 단계흐름: 상자 3~5개를 화살표로 ───────────────────
def t_steps(b, t, d):
    top = Y0 + heading(b, t, d)
    steps = d['steps'][:5]
    n = len(steps)
    ts = times(d, n)
    if n <= 3:
        bw = (X1 - X0 - 70 * (n - 1)) / n
        bh = min(200, Y1 - top - 20)
        y = top + (Y1 - top - bh) / 2
        for i, (s, st) in enumerate(zip(steps, ts)):
            a = ap(t, st)
            if a <= 0:
                continue
            x = X0 + i * (bw + 70)
            put(b, box([f'{i + 1}', s], int(bw), int(bh), NAVY if i < n - 1 else ORANGE, sizes=[34, 40], colors=[GRAY, DARK]), x, y, a)
            if i > 0:
                al, ad = layer(70, 40)
                arrow(ad, 6, 20, 64, 20, GRAY, 7, 20)
                put(b, al, x - 70, y + bh / 2 - 20, a)
    else:
        rowh = (Y1 - top) / n
        for i, (s, st) in enumerate(zip(steps, ts)):
            a = ap(t, st)
            if a <= 0:
                continue
            y = top + i * rowh
            p = pill(f'{i + 1}. {s}', 40, NAVY if i < n - 1 else ORANGE, WHITE, maxw=860)
            put(b, p, CX - p.width / 2, y + (1 - a) * 16, a)
            if i < n - 1:
                al, ad = layer(40, max(10, rowh - p.height))
                arrow(ad, 20, 2, 20, max(8, rowh - p.height - 4), GRAY, 5, 14)
                put(b, al, CX - 20, y + p.height, a)


# ── 4. 나란히비교: 상자 2~3개, 제목 + 2~3줄 ───────────────
def t_compare(b, t, d):
    top = Y0 + heading(b, t, d)
    cols = d['cols'][:3]
    n = len(cols)
    ts = times(d, n)
    bw = (X1 - X0 - 30 * (n - 1)) / n
    bh = Y1 - top - 10
    palette = [NAVY, ORANGE, GREEN]
    for i, (c, st) in enumerate(zip(cols, ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        lines = [c['head']] + c['lines'][:3]
        im = box(lines, int(bw), int(bh), palette[i], sizes=[44] + [34] * (len(lines) - 1), colors=[palette[i]] + [DARK] * (len(lines) - 1))
        put(b, im, X0 + i * (bw + 30), top + (1 - a) * 24, a)


# ── 5. 조건분기: 기준 하나 → 두 갈래(조건 + 결과) ─────────
def t_branch(b, t, d):
    ts = times(d, 3, first=0.3)
    a0 = ap(t, ts[0])
    top = pill(d['root'], 46, RED if d.get('warn') else NAVY, WHITE, padx=40)
    put(b, top, CX - top.width / 2, Y0 + 15, a0)
    a1, a2 = ap(t, ts[1]), ap(t, ts[2])
    if a1 > 0 or a2 > 0:
        lay, dd = layer(W, 110)
        if a1 > 0:
            arrow(dd, CX, 6, 290, 100, GRAY, 7)
        if a2 > 0:
            arrow(dd, CX, 6, 790, 100, GRAY, 7)
        put(b, lay, 0, Y0 + 95, max(a1, a2))
    for k, (br, a, x, col) in enumerate([(d['left'], a1, 70, NAVY), (d['right'], a2, 570, ORANGE)]):
        if a <= 0:
            continue
        im = box([br['if'], br['then']], 440, 270, col, sizes=[36, 46], colors=[col, DARK])
        put(b, im, x, Y0 + 220 + (1 - a) * 24, a)


# ── 6. 큰제목: 2줄 문장 ─────────────────────────────
def t_title(b, t, d):
    lines = d['lines'][:2]
    st = d.get('start', 0.1)
    for i, s in enumerate(lines):
        put_text(b, s, 92, NAVY if i == 0 else ORANGE, CX, Y0 + 110 + i * 140, t, st + i * 0.3, black=True, maxw=940)


# ── 7. 타임라인: 가로축 위 시점 2~4개 ────────────────────
def t_timeline(b, t, d):
    top = Y0 + heading(b, t, d)
    pts = d['points'][:4]
    n = len(pts)
    ts = times(d, n)
    ly = top + (Y1 - top) / 2 - 10
    xa, xb = X0 + 60, X1 - 60
    g = ease((t - ts[0] + 0.3) / (ts[-1] - ts[0] + 0.8)) if n > 1 else ap(t, ts[0])
    if g > 0:
        lay, dd = layer(W, 40)
        dd.line((xa, 20, xa + (xb - xa) * g, 20), fill=GRAY + (255,), width=8)
        put(b, lay, 0, ly - 20, 1)
    for i, (p, st) in enumerate(zip(pts, ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        x = xa + (xb - xa) * (i / (n - 1) if n > 1 else 0.5)
        col = ORANGE if p.get('hl') else NAVY
        dot, dd = layer(44, 44)
        dd.ellipse((0, 0, 43, 43), fill=col + (255,), outline=WHITE + (255,), width=5)
        put(b, dot, x - 22, ly - 22, a)
        w = (xb - xa) / max(1, n - 1) - 20 if n > 1 else 600
        top_s = fit(p['when'], w, 42, True)
        lw = text_layer(p['when'], top_s, col, True)
        put(b, lw, min(max(X0, x - lw.width / 2), X1 - lw.width), ly - 110 + (1 - a) * 16, a)
        bs = fit(p['what'], w, 34)
        lb = text_layer(p['what'], bs, DARK)
        put(b, lb, min(max(X0, x - lb.width / 2), X1 - lb.width), ly + 40 + (1 - a) * 16, a)


# ── 8. 짝짓기목록: 왼쪽 알약 → 오른쪽 값 ─────────────────
def t_pairs(b, t, d):
    top = Y0 + heading(b, t, d)
    rows = d['rows'][:4]
    ts = times(d, len(rows))
    rowh = min(125, (Y1 - top) / len(rows))
    top += max(0, (Y1 - top - rowh * len(rows)) / 2)
    lw = max(F(fit(r[0], 380, 40)).getlength(r[0]) for r in rows) + 52
    for i, ((l, r), st) in enumerate(zip(rows, ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        y = top + i * rowh
        lp = pill(l, 40, NAVY, WHITE, maxw=440)
        put(b, lp, X0 + 20 + (1 - a) * -40, y, a)
        al, ad = layer(90, 40)
        arrow(ad, 5, 20, 85, 20, GRAY, 7)
        ax = X0 + 30 + lw
        put(b, al, ax, y + lp.height / 2 - 20, a)
        rs = fit(r, X1 - ax - 110, 46, True)
        put(b, text_layer(r, rs, ORANGE if i == d.get('hl', -1) else DARK, True), ax + 105, y + 2, a)


# ── 9. 항목나열: 알약 3~7개 ─────────────────────────
def t_chips(b, t, d):
    top = Y0 + heading(b, t, d) + 10
    chips = d['chips'][:7]
    ts = times(d, len(chips), first=0.5)
    ps = [pill(c, 40, NAVY, WHITE, maxw=440) for c in chips]
    rows, cur, wsum = [], [], 0
    for p in ps:
        if cur and wsum + 24 + p.width > X1 - X0 - 20:
            rows.append(cur)
            cur, wsum = [], 0
        cur.append(p)
        wsum += p.width + (24 if wsum else 0)
    if cur:
        rows.append(cur)
    used = len(rows) * 100 + (90 if d.get('result') else 0)
    top += max(0, (Y1 - top - used) / 2 - 10)
    k = 0
    for r, row in enumerate(rows):
        tw = sum(p.width for p in row) + 24 * (len(row) - 1)
        x = CX - tw / 2
        for p in row:
            a = ap(t, ts[k])
            put(b, p, x, top + r * 100 + (1 - a) * 20, a)
            x += p.width + 24
            k += 1
    if d.get('result'):
        put_text(b, d['result'], 48, ORANGE, CX, top + len(rows) * 100 + 20, t, ts[-1] + 0.8, black=True)


# ── 10. 막대비교: 막대 2~5개 (고른 값 강조 가능) ───────────
def t_bars(b, t, d):
    top = Y0 + heading(b, t, d)
    bars = d['bars'][:5]
    n = len(bars)
    ts = times(d, n)
    vmax = max(x['value'] for x in bars) or 1
    base_y, maxh = Y1 - 70, Y1 - 70 - top - 70
    gap = 50 if n <= 3 else 30
    bw = min(190, (X1 - X0 - 80 - gap * (n - 1)) / n)
    x0 = CX - (bw * n + gap * (n - 1)) / 2
    for i, (bar, st) in enumerate(zip(bars, ts)):
        g = ease((t - st) / 1.0)
        if g <= 0:
            continue
        hgt = maxh * bar['value'] / vmax * g
        x = x0 + i * (bw + gap)
        col = ORANGE if bar.get('hl') else (GRAY if bar.get('dim') else NAVY)
        lay, dd = layer(bw, maxh + 2)
        dd.rounded_rectangle((0, maxh - hgt, bw - 1, maxh), radius=14, fill=col + (255,))
        put(b, lay, x, base_y - maxh, 1)
        shown = bar.get('text', '')
        if not shown:
            v = bar['value'] * g
            shown = (f'{v:.1f}' if isinstance(bar['value'], float) and bar['value'] % 1 else f'{round(v):,}') + bar.get('unit', '')
        vs = fit(shown, bw + gap - 10, 44, True)
        v = text_layer(shown, vs, col if col != GRAY else DARK, True)
        put(b, v, x + bw / 2 - v.width / 2, base_y - hgt - 62, 1)
        ls = fit(bar['label'], bw + gap - 6, 32)
        lb = text_layer(bar['label'], ls, DARK)
        put(b, lb, x + bw / 2 - lb.width / 2, base_y + 8, min(1, g * 2))
    if d.get('note'):
        put_text(b, d['note'], 28, GRAY, CX, Y1 - 6, t, ts[-1] + 0.8, slide=0)


# ── 11. 포함제외: O 목록 / X 목록 ───────────────────────
def t_inout(b, t, d):
    top = Y0 + heading(b, t, d)
    ins, outs = d['in'][:4], d['out'][:4]
    ts = times(d, 2)
    for k, (items, st, col, mark, x, head) in enumerate([
            (ins, ts[0], GREEN, 'O', X0, d.get('in_head', '해당')),
            (outs, ts[1], RED, 'X', CX + 15, d.get('out_head', '제외'))]):
        a = ap(t, st)
        if a <= 0:
            continue
        w, h = 465, Y1 - top - 10
        im, dd = layer(w, h)
        dd.rounded_rectangle((3, 3, w - 4, h - 4), radius=26, fill=WHITE + (255,), outline=col + (255,), width=6)
        f = F(44, True)
        dd.text((30, 22), f'{mark}  {head}', font=f, fill=col + (255,))
        rowh = min(78, (h - 110) / max(1, len(items)))
        for i, s in enumerate(items):
            sz = fit(s, w - 60, 36)
            dd.text((34, 100 + i * rowh), s, font=F(sz), fill=DARK + (255,))
        put(b, im, x, top + (1 - a) * 24, a)


# ── 12. 계산식: A ○ B = C ──────────────────────────
def t_formula(b, t, d):
    top = Y0 + heading(b, t, d)
    terms = d['terms'][:3]
    ops = d['ops']
    res = d['result']
    n = len(terms) + 1
    ts = times(d, n)
    y = top + 40
    bh = 190
    opw = 64
    bw = (X1 - X0 - opw * (n - 1)) / n
    for i, (tm, st) in enumerate(zip(terms + [res], ts)):
        a = ap(t, st)
        if a <= 0:
            continue
        x = X0 + i * (bw + opw)
        last = i == n - 1
        im = box([tm['label'], tm['value']], int(bw), bh, ORANGE if last else NAVY, sizes=[32, 52], colors=[DARK, ORANGE if last else NAVY],
                 fill=(255, 243, 228) if last else WHITE)
        put(b, im, x, y + (1 - a) * 20, a)
        if i > 0:
            o = ops[i - 1] if i - 1 < len(ops) else '='
            if last:
                o = '='
            ol = text_layer(o, 64, GRAY, True)
            put(b, ol, x - opw / 2 - ol.width / 2, y + bh / 2 - ol.height / 2, a)
    if d.get('note'):
        put_text(b, d['note'], 32, GRAY, CX, y + bh + 40, t, ts[-1] + 0.6, slide=0)


# ── 13. 누적막대: 막대 하나를 2~3조각 ────────────────────
def t_stack(b, t, d):
    top = Y0 + heading(b, t, d)
    parts = d['parts'][:3]
    ts = times(d, len(parts))
    tot = sum(p['value'] for p in parts) or 1
    x, y, full, hh = X0 + 20, top + 60, X1 - X0 - 40, 110
    palette = [NAVY, ORANGE, GREEN]
    acc = 0
    for i, (p, st) in enumerate(zip(parts, ts)):
        g = ease((t - st) / 0.9)
        w = full * p['value'] / tot
        if g > 0:
            lay, dd = layer(full + 2, hh + 2)
            dd.rectangle((acc, 0, acc + max(4, w * g), hh), fill=palette[i] + (255,))
            put(b, lay, x, y, 1)
            lbl = p.get('text') or f"{p['value']}{p.get('unit', '%')}"
            lt = text_layer(lbl, fit(lbl, max(60, w - 10), 46, True), WHITE, True)
            if w > lt.width + 10:
                put(b, lt, x + acc + w / 2 - lt.width / 2, y + hh / 2 - lt.height / 2, ap(t, st + 0.5))
            nm = text_layer(p['label'], fit(p['label'], max(120, w), 36), palette[i])
            put(b, nm, x + acc + min(max(0, w / 2 - nm.width / 2), full - acc - nm.width), y + hh + 20, ap(t, st + 0.5))
        acc += w
    if d.get('note'):
        put_text(b, d['note'], 40, DARK, CX, y + hh + 110, t, ts[-1] + 1.0, black=True)


TEMPLATES = {
    '체크목록': t_checklist, '숫자강조': t_numbers, '단계흐름': t_steps, '나란히비교': t_compare,
    '조건분기': t_branch, '큰제목': t_title, '타임라인': t_timeline, '짝짓기목록': t_pairs,
    '항목나열': t_chips, '막대비교': t_bars, '포함제외': t_inout, '계산식': t_formula, '누적막대': t_stack,
}


def draw_chart(b, t, chart):
    # 장면표의 chart = {"type": "막대비교", ...데이터}
    fn = TEMPLATES.get(chart.get('type'))
    if fn:
        fn(b, t, chart)
