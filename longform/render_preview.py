# render_preview.py — 긴 영상 시험본(목소리 없음): 장면 그림 9장 + 움직이는 차트 + 자막
# 1080x1920(세로) 또는 WIDE=1이면 1920x1080(가로, 긴 영상), 24fps, 장면 길이는 장면표 sec 값. 장면 사이 0.4초 겹쳐 넘김.
import json, math, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

SCENES = sys.argv[1]
IMGDIR = sys.argv[2]
OUT = sys.argv[3]
W, H, FPS, XF = 1080, 1920, 24, 0.4
# 가로판(11/6): WIDE=1 이면 결과 영상을 1920x1080(16:9)으로 — 세로 3분 이하는 유튜브가 쇼츠로 분류해 긴 영상 시청 시간에 안 들어가므로.
# 도표·자막·그림은 세로판과 같은 방식으로 만든 뒤 가로 화면에 다시 배치함(도표 틀은 고치지 않음)
WIDE = os.environ.get('WIDE', '') == '1'
OW, OH = (1920, 1080) if WIDE else (W, H)
# 자막 — 세로판: 2줄까지·폭 800 / 가로판(11/6 비광도기님): 1줄·폭 1700, 바닥에 늘 깔린 고정 검정 띠(글자 수와 관계없이 같은 크기)
SUB_W, SUB_LINES = (1700, 1) if WIDE else (800, 2)
BAR_H = 120
BOTTOM_SAFE = 250   # 가로판 자막 띠 아래 빈칸 — 재생 막대·단추·아래 그늘이 덮는 아래쪽을 피함(11/6 비광도기님, 100은 재생 막대에 가려 250으로 올림)
BAR_Y = OH - BOTTOM_SAFE - BAR_H
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
FONT_B = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
NAVY = (36, 78, 120)
ORANGE = (240, 140, 50)
GRAY = (150, 160, 170)
DARK = (40, 48, 60)
WHITE = (255, 255, 255)
RED = (214, 84, 60)
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
    im = Image.new('RGBA', (int(w), int(h)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def put(base, lay, x, y, alpha=1.0):
    if alpha <= 0:
        return
    if alpha < 1:
        a = lay.getchannel('A').point(lambda v: int(v * alpha))
        lay = lay.copy()
        lay.putalpha(a)
    base.alpha_composite(lay, (int(x), int(y)))


def text_layer(s, size, color, black=False, pad=6):
    f = F(size, black)
    bb = f.getbbox(s)
    im, d = layer(bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2)
    d.text((pad - bb[0], pad - bb[1]), s, font=f, fill=color + (255,))
    return im


def put_text(base, s, size, color, cx, y, t, start, black=False, slide=30, left=None):
    a = ap(t, start)
    if a <= 0:
        return
    lay = text_layer(s, size, color, black)
    x = (cx - lay.width / 2) if left is None else left
    put(base, lay, x, y + (1 - a) * slide, a)


def pill(s, size, bg, fg, padx=26, pady=14):
    f = F(size)
    bb = f.getbbox(s)
    w = bb[2] - bb[0] + padx * 2
    h = bb[3] - bb[1] + pady * 2
    im, d = layer(w, h)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg + (255,))
    d.text((padx - bb[0], pady - bb[1]), s, font=f, fill=fg + (255,))
    return im


def box(lines, w, h, border, fill=WHITE, sizes=None, colors=None):
    im, d = layer(w, h)
    d.rounded_rectangle((3, 3, w - 4, h - 4), radius=26, fill=fill + (255,), outline=border + (255,), width=6)
    sizes = sizes or [44] * len(lines)
    colors = colors or [DARK] * len(lines)
    tot = sum(F(s).getbbox('가')[3] + 14 for s in sizes)
    y = (h - tot) / 2
    for s, sz, c in zip(lines, sizes, colors):
        f = F(sz)
        bb = f.getbbox(s)
        d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1] + 4), s, font=f, fill=c + (255,))
        y += f.getbbox('가')[3] + 14
    return im


def arrow(d, x1, y1, x2, y2, color, width=8):
    d.line((x1, y1, x2, y2), fill=color + (255,), width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 26
    p1 = (x2 - L * math.cos(ang - 0.5), y2 - L * math.sin(ang - 0.5))
    p2 = (x2 - L * math.cos(ang + 0.5), y2 - L * math.sin(ang + 0.5))
    d.polygon([(x2, y2), p1, p2], fill=color + (255,))


# ── 장면별 차트 (카드 영역 y 110~610) ─────────────────
CX = 540


def s1(b, t):
    put_text(b, '퇴직금 IRP,', 96, NAVY, CX, 210, t, -1, black=True)
    put_text(b, '해지하면 세금은?', 96, ORANGE, CX, 350, t, -1, black=True)


def s2(b, t):
    put_text(b, '결론부터', 46, ORANGE, CX, 135, t, 0.2)
    rows = [('60일 안 IRP 이체', '세금 미룸', 0.6), ('연금으로 수령', '세금 70%만', 6.5), ('중도 해지', '세금 다시 냄', 10.0)]
    for i, (l, r, st) in enumerate(rows):
        a = ap(t, st)
        if a <= 0:
            continue
        y = 225 + i * 125
        lp = pill(l, 42, NAVY, WHITE)
        put(b, lp, 80 + (1 - a) * -40, y, a)
        al, ad = layer(90, 40)
        arrow(ad, 5, 20, 85, 20, GRAY, 7)
        put(b, al, 90 + lp.width, y + lp.height / 2 - 20, a)
        put(b, text_layer(r, 48, ORANGE if i == 1 else DARK, True), 195 + lp.width, y + 2, a)


def s3(b, t):
    # IRP 계좌 상자
    a0 = ap(t, 0.2)
    inside = t > 2.6
    acc = box(['IRP 계좌', '세금 안 뗀 퇴직금'] if inside else ['IRP 계좌'], 330, 190, NAVY, sizes=[50, 34] if inside else [50], colors=[NAVY, ORANGE] if inside else [NAVY])
    put(b, acc, 650, 170, a0)
    # 퇴직금 상자가 들어감
    m = ease((t - 0.8) / 1.8)
    x = 90 + m * 600
    sc = 1 - 0.45 * m
    if t > 0.2:
        cash = box(['퇴직금'], int(250 * sc) + 1, int(150 * sc) + 1, ORANGE, fill=(255, 243, 228), sizes=[max(20, int(46 * sc))], colors=[ORANGE])
        if m < 0.98:
            put(b, cash, x, 190 + (150 - 150 * sc) / 2 + 20 * m, ap(t, 0.2))
    if m > 0.05 and m < 0.98:
        al, ad = layer(260, 40)
        arrow(ad, 5, 20, 250, 20, GRAY, 6)
        put(b, al, 370, 245, 1 - m)
    put_text(b, '세금은 꺼낼 때 냅니다', 50, NAVY, CX, 400, t, 2.8, black=True)
    put_text(b, '이미 떼였다면 → 환급 절차 따로', 38, DARK, CX, 495, t, 5.2)


def s4(b, t):
    put_text(b, '연금으로 받으면 줄어드는 퇴직소득세', 40, DARK, CX, 130, t, 0.1)
    labels = ['연금 외', '10년 이하', '10~20년', '20년 초과']
    vals = [100, 70, 60, 50]
    starts = [0.4, 1.4, 4.8, 6.6]
    cols = [GRAY, NAVY, NAVY, ORANGE]
    base_y, maxh, bw, gap, x0 = 515, 235, 150, 70, 120
    _, _ = None, None
    for i in range(4):
        g = ease((t - starts[i]) / 1.0)
        if g <= 0:
            continue
        hgt = maxh * vals[i] / 100 * g
        x = x0 + i * (bw + gap)
        lay, d = layer(bw, maxh + 2)
        d.rounded_rectangle((0, maxh - hgt, bw - 1, maxh), radius=14, fill=cols[i] + (255,))
        put(b, lay, x, base_y - maxh, 1)
        v = text_layer(f'{int(round(vals[i] * g))}%', 44, cols[i] if i else DARK, True)
        put(b, v, x + bw / 2 - v.width / 2, base_y - hgt - 62, 1)
        lb = text_layer(labels[i], 32, DARK)
        put(b, lb, x + bw / 2 - lb.width / 2, base_y + 8, min(1, g * 2))
    put_text(b, '연금 수령 연차 기준 · 2026년 수령분부터', 28, GRAY, CX, 572, t, 6.8, slide=0)


def s5(b, t):
    put_text(b, '서로 다른 돈, 별개의 혜택', 46, DARK, CX, 130, t, 0.1, black=True)
    a1, a2 = ap(t, 0.5), ap(t, 4.0)
    l1 = box(['퇴직금', '→ 세금 미룸'], 420, 300, NAVY, sizes=[46, 40], colors=[NAVY, DARK])
    l2 = box(['내가 더 넣은 돈', '→ 세액공제'], 420, 300, ORANGE, sizes=[46, 40], colors=[ORANGE, DARK])
    put(b, l1, 80, 240 + (1 - a1) * 30, a1)
    put(b, l2, 580, 240 + (1 - a2) * 30, a2)


def s6(b, t):
    put_text(b, '세액공제 한도 · 공제율', 46, DARK, CX, 130, t, 0.1, black=True)
    g = ease((t - 0.5) / 2.0)
    x0, y0, full, hh = 90, 240, 900, 90
    if g > 0:
        lay, d = layer(full + 4, hh + 4)
        w1 = min(full * 600 / 900, full * g)
        d.rounded_rectangle((0, 0, full, hh), radius=20, fill=(235, 240, 245, 255))
        d.rounded_rectangle((0, 0, max(30, full * g), hh), radius=20, fill=ORANGE + (255,))
        d.rounded_rectangle((0, 0, max(30, w1), hh), radius=20, fill=NAVY + (255,))
        put(b, lay, x0, y0, 1)
        if g > 0.6:
            put(b, text_layer('연금저축 600만', 34, WHITE), x0 + 30, y0 + 18, ap(t, 1.6))
        if g > 0.95:
            put(b, text_layer('+IRP', 34, WHITE), x0 + 640, y0 + 18, ap(t, 2.4))
    put_text(b, '합쳐서 연 900만 원까지', 44, NAVY, CX, 350, t, 2.6, black=True)
    a = ap(t, 4.6)
    if a > 0:
        p1 = pill('총급여 5,500만 원 이하  16.5%', 34, NAVY, WHITE)
        p2 = pill('초과  13.2%', 34, GRAY, WHITE)
        put(b, p1, 90, 470 + (1 - a) * 20, a)
        put(b, p2, 110 + p1.width, 470 + (1 - a) * 20, ap(t, 5.4))


def s7(b, t):
    a0 = ap(t, 0.3)
    top = pill('중도 해지', 50, RED, WHITE, padx=40)
    put(b, top, CX - top.width / 2, 125, a0)
    a1, a2 = ap(t, 1.5), ap(t, 6.0)
    if a1 > 0 or a2 > 0:
        lay, d = layer(W, 120)
        if a1 > 0:
            arrow(d, CX, 10, 290, 100, GRAY, 7)
        if a2 > 0:
            arrow(d, CX, 10, 790, 100, GRAY, 7)
        put(b, lay, 0, 205, max(a1, a2))
    bl = box(['퇴직금 부분', '퇴직소득세', '(연금 감면 없음)'], 440, 260, NAVY, sizes=[36, 44, 30], colors=[NAVY, DARK, GRAY])
    br = box(['공제받은 돈 + 수익', '기타소득세', '16.5%'], 440, 260, ORANGE, sizes=[36, 44, 48], colors=[ORANGE, DARK, ORANGE])
    put(b, bl, 70, 330 + (1 - a1) * 30, a1)
    put(b, br, 570, 330 + (1 - a2) * 30, a2)


def s8(b, t):
    put_text(b, '부득이한 사유라면', 46, DARK, CX, 125, t, 0.1, black=True)
    chips = ['천재지변', '사망', '해외이주', '파산·개인회생', '요양']
    rows = [chips[:3], chips[3:]]
    k = 0
    for r, row in enumerate(rows):
        ps = [pill(c, 40, NAVY, WHITE) for c in row]
        tw = sum(p.width for p in ps) + 24 * (len(ps) - 1)
        x = CX - tw / 2
        for p in ps:
            a = ap(t, 0.6 + k * 0.7)
            put(b, p, x, 230 + r * 105 + (1 - a) * 20, a)
            x += p.width + 24
            k += 1
    put_text(b, '→ 연금소득으로 과세', 50, ORANGE, CX, 470, t, 5.5, black=True)


def s9(b, t):
    put_text(b, '해지 전 꼭 확인', 64, ORANGE, CX, 140, t, 0.2, black=True)
    for i, (s, st) in enumerate([('재원별 금액 — 금융회사', 1.5), ('국세청 상담센터 126', 4.5)]):
        a = ap(t, st)
        if a <= 0:
            continue
        num, nd = layer(70, 70)
        nd.ellipse((0, 0, 69, 69), fill=NAVY + (255,))
        f = F(40)
        bb = f.getbbox(str(i + 1))
        nd.text((35 - (bb[2] - bb[0]) / 2 - bb[0], 35 - (bb[3] - bb[1]) / 2 - bb[1]), str(i + 1), font=f, fill=WHITE + (255,))
        y = 290 + i * 120
        put(b, num, 120, y + (1 - a) * 20, a)
        put(b, text_layer(s, 50, DARK, True), 215, y + 2 + (1 - a) * 20, a)


CHARTS = [s1, s2, s3, s4, s5, s6, s7, s8, s9]

# ── 자동 장면표의 도표 틀 (chart 칸이 있으면 이것으로 그림, 11/3) ──────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_templates import draw_chart  # noqa: E402

_chart_ready = {}


def _chart_count(c):
    # 틀마다 차례로 나타나는 요소 수
    t = c.get('type')
    k = {'체크목록': 'items', '숫자강조': 'cards', '단계흐름': 'steps', '나란히비교': 'cols', '타임라인': 'points',
         '짝짓기목록': 'rows', '항목나열': 'chips', '막대비교': 'bars', '누적막대': 'parts'}.get(t)
    if k:
        return len(c.get(k) or [])
    return {'조건분기': 3, '포함제외': 2, '계산식': len(c.get('terms') or []) + 1}.get(t, 1)


def chart_for(i, sc):
    # 요소가 대사 앞 60% 동안 고르게 나타나게 시각을 정함. 첫 장면 제목은 0초부터 보이게
    if i not in _chart_ready:
        c = dict(sc['chart'])
        n = _chart_count(c)
        if c.get('type') == '큰제목':
            c['start'] = -1 if i == 0 else 0.2
        elif n > 0:
            span = min(sc['sec'] * 0.6, 1.6 * max(1, n - 1))
            c['times'] = [0.4 + (span * k / (n - 1) if n > 1 else 0) for k in range(n)]
        _chart_ready[i] = c
    return _chart_ready[i]



# ── 자막 ─────────────────────────────────────────
def sentences(txt):
    # 문장(. ? !)마다, 쉼표 구절을 2줄 안에 들어가는 만큼 묶어 한 조각으로 (너무 짧은 조각 깜빡임 방지)
    f = F(50)
    out = []
    for sent in re.split(r'(?<=[.?!])\s+', txt.strip()):
        cur = ''
        for p in [x for x in re.split(r'(?<=,)\s+', sent) if x]:
            test = (cur + ' ' + p).strip()
            if len(wrap(test, f, SUB_W)) <= SUB_LINES:
                cur = test
                continue
            if cur:
                out.append(cur)
            lines = wrap(p, f, SUB_W)
            for k in range(0, len(lines) - SUB_LINES, SUB_LINES):
                out.append(' '.join(lines[k:k + SUB_LINES]))
            cur = ' '.join(lines[(len(lines) - 1) // SUB_LINES * SUB_LINES:]) if len(lines) > SUB_LINES else p
        if cur:
            out.append(cur)
    return out


def wrap(s, f, maxw):
    words = s.split(' ')
    lines, cur = [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if f.getlength(test) <= maxw:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def subtitle_layer(s):
    f = F(50)
    if WIDE:
        # 가로판: 글자만 (검정 띠는 frame_wide가 늘 깔아 둠)
        line = ' '.join(wrap(s, f, SUB_W))
        im, d = layer(OW, BAR_H)
        w = f.getlength(line)
        d.text(((OW - w) / 2, (BAR_H - 72) / 2 + 4), line, font=f, fill=WHITE + (255,))
        return im
    lines = wrap(s, f, 800)
    lh = 72
    h = lh * len(lines) + 40
    im, d = layer(860, h)
    d.rounded_rectangle((0, 0, 859, h - 1), radius=28, fill=(20, 30, 45, 200))
    for i, ln in enumerate(lines):
        w = f.getlength(ln)
        d.text(((860 - w) / 2, 18 + i * lh), ln, font=f, fill=WHITE + (255,))
    return im


# ── 준비 ─────────────────────────────────────────
data = json.load(open(SCENES, encoding='utf-8'))['scenes']
HEAD_SAFE = 850   # 머리 꼭대기가 이보다 위에 있으면 그림을 내려 깜 (판 흐림 끝 800 + 여유 50)


def head_top(im):
    # 흰머리 인물의 머리 꼭대기(원본 그림 기준 세로 위치). 못 찾으면 None
    import numpy as np
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    white = (mn > 222) & ((mx - mn) < 14)
    dark = mx < 70
    band = np.median(a[20:60].reshape(-1, 3), axis=0)
    rowdev = (np.abs(a - band).mean(axis=2) > 18).mean(axis=1)
    seam = next((y for y in range(60, h) if rowdev[y] > 0.25), int(h * 0.3))
    first = next((y for y in range(60, h) if rowdev[y] > 0.02), seam)   # 단색 바탕: 처음 무언가 나타나는 줄
    for y in range(max(0, min(seam, first) - 30), h):
        row = white[y]
        run = 0
        for x in range(w):
            run = run + 1 if row[x] else 0
            if run >= 12 and dark[max(0, y - 8):y, max(0, x - 12):x + 1].any():
                return y
    return None




def draw_board_symbol(win, kind):
    # 그림 속 큰 흰 칠판·화면을 찾아, 사람·테두리에서 떨어진 빈 네모 안에만 글자 없는 기호를 그림
    import numpy as np
    from scipy import ndimage
    a = np.asarray(win).astype(int)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    white = (mn > 232) & ((mx - mn) < 14)
    lab, n = ndimage.label(white)
    if n == 0:
        return None
    sizes = ndimage.sum(white, lab, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    comp = lab == k
    ys, xs = np.where(comp)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    if comp.sum() < 0.08 * W * H or comp.sum() / ((y1 - y0 + 1) * (x1 - x0 + 1)) < 0.85:
        return None
    m = comp.copy()
    m[1250:, :] = False                      # 자막 자리 위만
    m = ndimage.binary_erosion(m, iterations=24)
    st = 4
    G = m[::st, ::st]
    R, C = G.shape
    h = np.zeros(C, int)
    best = (0, None)
    for r in range(R):
        h = np.where(G[r], h + 1, 0)
        stack = []
        for c in range(C + 1):
            cur = h[c] if c < C else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                if hh * (c - s0) > best[0]:
                    best = (hh * (c - s0), (s0, r - hh + 1, c, r + 1))
                start = s0
            stack.append((start, cur))
    if best[1] is None:
        return None
    c0, r0, c1, r1 = best[1]
    X0, Y0, X1, Y1 = c0 * st, r0 * st, c1 * st, r1 * st
    if X1 - X0 < 200 or Y1 - Y0 < 160:
        return None
    d = ImageDraw.Draw(win)
    OUTL, NV, NVD, OR, ORD = (30, 30, 30), (36, 78, 120), (20, 45, 75), (240, 130, 45), (190, 90, 25)
    pad = 10
    left, right, top, base = X0 + pad, X1 - pad - 20, Y0 + pad + 40, Y1 - pad
    hs = [1.0, 0.78, 0.62, 0.48] if kind == '내림막대' else [0.48, 0.62, 0.78, 1.0]
    nb = 4
    bw = (right - left) / (nb * 1.6)
    gap = (right - left - nb * bw) / (nb - 1)
    maxh = base - top
    for i, hh in enumerate(hs):
        x = left + i * (bw + gap)
        hg = maxh * hh
        d.rectangle((x + 8, base - hg + 8, x + bw + 8, base), fill=NVD)
        d.rectangle((x, base - hg, x + bw, base), fill=NV, outline=OUTL, width=4)
    pts = []
    if kind == '내림막대':
        xa, ya, xb, yb = left, top - 30, right, base - maxh * 0.42
        for k2 in range(41):
            t = k2 / 40
            pts.append((xa + (xb - xa) * t, ya + (yb - ya) * (t ** 1.6)))
    else:
        xa, ya, xb, yb = left, base - maxh * 0.42, right, top - 30
        for k2 in range(41):
            t = k2 / 40
            pts.append((xa + (xb - xa) * t, ya + (yb - ya) * (t ** 1.6)))
    d.line(pts, fill=ORD, width=26, joint='curve')
    d.line([(p[0], p[1] - 6) for p in pts], fill=OR, width=19, joint='curve')
    ang = math.atan2(pts[-1][1] - pts[-4][1], pts[-1][0] - pts[-4][0])
    L = 52
    tip = (pts[-1][0] + math.cos(ang) * 26, pts[-1][1] + math.sin(ang) * 26)
    d.polygon([tip, (tip[0] - L * math.cos(ang - 0.6), tip[1] - L * math.sin(ang - 0.6)),
               (tip[0] - L * math.cos(ang + 0.6), tip[1] - L * math.sin(ang + 0.6))], fill=OR, outline=OUTL)
    return (X0, Y0, X1, Y1)



# ── 목소리(TTS) 맞춤 ─────────────────────────────────
# 환경변수 TTS=<tts 폴더> 가 있으면: 문장별 mp3 길이로 장면 길이를 다시 정하고,
# 자막은 그 문장이 읽히는 동안에만, 쉼표 쉼(무음)에 맞춰 넘기고, 소리를 영상에 입힘
TTS_DIR = os.environ.get('TTS')
V_LEAD, V_GAP, V_TAIL, V_LAST_TAIL, SR = 0.35, 0.30, 0.50, 1.20, 48000
V_COMMA = 0.35   # 쉼표 구절 사이 쉼 (11/3 비광도기 결정: 쉼표에서 끊어 읽기)
voice = None


def _dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout.strip())


def _pauses(p):
    # 문장 안의 쉼(-35dB 아래로 0.06초 이상 — 낱말 사이 짧은 쉼까지) → [(시작, 끝)]
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', p, '-af', 'silencedetect=n=-35dB:d=0.06', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', r)]
    en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', r)]
    return list(zip(st, en))


if TTS_DIR:
    man = json.load(open(os.path.join(TTS_DIR, '_목록.json'), encoding='utf-8'))
    voice = [[] for _ in data]
    for it in man['items']:
        voice[it['scene'] - 1].append(it)
    for i, sc in enumerate(data):
        if not voice[i]:
            raise SystemExit(f'{i + 1}번 장면 음성 파일이 없습니다')
        sc['sec_old'] = sc['sec']
        off = V_LEAD
        voice[i].sort(key=lambda x: (x['n'], x.get('p', 1)))
        gap = 0.0
        for k, it in enumerate(voice[i]):
            p = os.path.join(TTS_DIR, it['file'])
            it['path'], it['dur'], it['off'], it['pauses'] = p, _dur(p), off, _pauses(p)
            gap = V_GAP if it.get('last', True) else V_COMMA
            off += it['dur'] + gap
        sc['sec'] = round(off - gap + (V_LAST_TAIL if i == len(data) - 1 else V_TAIL), 3)
    print('구절 사이 쉼', V_COMMA, '초 · 문장 사이', V_GAP, '초', flush=True)
    print('목소리 맞춤 장면 길이:', [(i + 1, sc['sec_old'], sc['sec']) for i, sc in enumerate(data)], flush=True)


_ASR = {}


def asr_words(it):
    # 위스퍼(음성인식)로 이 mp3의 낱말별 시작·끝 시각. 결과는 TTS 폴더 옆 기록 파일에 저장해 다시 쓰기
    cache = os.path.join(os.path.dirname(os.path.abspath(OUT)), '_낱말시각_' + os.path.basename(TTS_DIR.rstrip('/')) + '.json')
    if not _ASR:
        _ASR.update(json.load(open(cache, encoding='utf-8')) if os.path.exists(cache) else {'_': 1})
    if it['file'] not in _ASR:
        import whisper
        if 'm' not in card_cache_asr:
            card_cache_asr['m'] = whisper.load_model('small')
        r = card_cache_asr['m'].transcribe(it['path'], language='ko', word_timestamps=True, fp16=False)
        _ASR[it['file']] = [(w['word'], float(w['start']), float(w['end'])) for s in r['segments'] for w in s['words']]
        json.dump(_ASR, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return _ASR[it['file']]


card_cache_asr = {}


def _norm(s):
    return re.sub(r'[^0-9가-힣%]', '', s)


def _jamo(s):
    # 한글을 자모로 풀어 비교 (음성인식이 '미룰'을 '밀을'로 적어도 비슷하게 잡히도록)
    out = []
    for ch in _norm(s):
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out += [chr(0x1100 + o // 588), chr(0x1161 + (o % 588) // 28)] + ([chr(0x11A7 + o % 28)] if o % 28 else [])
        else:
            out.append(ch)
    return ''.join(out)


def _sim(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _env_minima(path, lo, hi):
    # 10ms 단위 소리 크기에서 움푹 꺼진 곳(낱말 사이 후보)
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    hop = 160
    e = np.array([np.sqrt((a[k:k + 320] ** 2).mean() + 1e-12) for k in range(0, len(a) - 320, hop)])
    e = np.convolve(e, np.ones(3) / 3, mode='same')
    out = []
    for k in range(2, len(e) - 2):
        tk = k * hop / 16000
        if lo <= tk <= hi and e[k] <= e[k - 1] and e[k] <= e[k + 1] and e[k] <= e[k - 2] and e[k] <= e[k + 2]:
            out.append((tk, float(e[k])))
    return out


def cut_verify(it, cur, nxt, t0):
    key = f"cut:{it['file']}:{_norm(cur)[-12:]}"
    if key in _ASR:
        return _ASR[key][0], _ASR[key][1]
    import whisper
    if 'm' not in card_cache_asr:
        card_cache_asr['m'] = whisper.load_model('small')
    m = card_cache_asr['m']
    last_w = _jamo(cur.split()[-1])
    first_w = _jamo(nxt.split()[0])
    cands = sorted(_env_minima(it['path'], t0 - 0.6, t0 + 0.6), key=lambda x: abs(x[0] - t0))[:10]
    cands = [c for c, _ in cands] or [t0]
    best = (-1, t0)
    tmp = os.path.join(os.path.dirname(os.path.abspath(OUT)), '_cut.wav')
    for c in cands:
        txt = []
        for args in (['-ss', f'{max(0.0, c - 2.2):.3f}', '-t', f'{min(c, 2.2):.3f}'], ['-ss', f'{c:.3f}', '-t', '2.2']):
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', it['path']] + args + [tmp], check=True)
            txt.append(_jamo(m.transcribe(tmp, language='ko', fp16=False, condition_on_previous_text=False)['text']))
        sa = _sim(last_w, txt[0][-len(last_w):])
        sb = _sim(first_w, txt[1][:len(first_w)])
        sc_ = min(sa, sb)
        if sc_ > best[0]:
            best = (sc_, c)
        if sc_ >= 0.75:
            break
    os.remove(tmp)
    how = f'잘라서 확인 {best[0]:.2f}' + ('' if best[0] >= 0.75 else ' — 확인 미달')
    _ASR[key] = [best[1], how]
    cache = os.path.join(os.path.dirname(os.path.abspath(OUT)), '_낱말시각_' + os.path.basename(TTS_DIR.rstrip('/')) + '.json')
    json.dump(_ASR, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return best[1], how


def voice_bounds(it, chunks):
    # 조각 경계 시각: 음성인식 낱말 사이 → 가까운(±0.25초) 무음이 있으면 그 가운데로 다듬음
    import difflib
    try:
        words = asr_words(it)
    except ImportError:
        # 서버(깃허브)에는 음성인식(위스퍼)을 설치하지 않음 — 글자 비율 자리 근처의 가장 조용한 곳으로 (11/4)
        words = []
    heard, owner = '', []
    for k, (w, a, b) in enumerate(words):
        nw = _norm(w)
        heard += nw
        owner += [k] * len(nw)
    ref = _norm(it['text'])
    rmap = {}
    for a, b, size in difflib.SequenceMatcher(None, ref, heard, autojunk=False).get_matching_blocks():
        for q in range(size):
            rmap[a + q] = b + q
    ps = it['pauses']
    out, acc, last = [], 0, 0.0
    tot = sum(len(_norm(c)) for c in chunks)
    for c in chunks[:-1]:
        acc += len(_norm(c))
        i0 = next((rmap[q] for q in range(acc - 1, -1, -1) if q in rmap), None)
        i1 = next((rmap[q] for q in range(acc, len(ref)) if q in rmap), None)
        if i0 is None or i1 is None or not words:
            t = it['dur'] * acc / tot
            how = '글자비율'
            near = [m for m in _env_minima(it['path'], t - 0.5, t + 0.5)]
            if near:
                t = min(near, key=lambda m: m[1])[0]
                how = '글자비율+조용한 곳'
        else:
            wa, wb = owner[i0], owner[i1]
            t = (words[wa][2] + words[wb][1]) / 2 if wa != wb else words[wa][2]
            how = '음성인식'
            t, how = cut_verify(it, c, chunks[chunks.index(c) + 1], t)
        t = max(t, last + 0.6)
        out.append(t)
        last = t
        print(f"   {it['file']} 경계 '{c[-6:]}|' {t:.2f}초 ({how})", flush=True)
    return out


V_EXACT = [0, 0]   # [구절 경계에서 정확히 넘긴 수, 구절 안에서 음성인식으로 넘긴 수]


def voice_subs(i, sc):
    # 같은 문장의 쉼표 구절들을 2줄에 들어가는 만큼 묶어 한 자막으로. 자막은 구절 파일이 시작하는 시각에 넘김(정확).
    # 구절 하나가 2줄을 넘을 때만 그 구절 안을 나누고, 그 경계는 음성인식으로 맞춤.
    f = F(50)
    clips = voice[i]
    groups, cur = [], []
    for it in clips:
        if cur and (cur[-1]['n'] != it['n'] or len(wrap(' '.join(x['text'] for x in cur + [it]), f, SUB_W)) > SUB_LINES):
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    marks = []   # (시작 시각, 자막 글)
    for g in groups:
        txt = ' '.join(x['text'] for x in g)
        if len(g) == 1 and len(wrap(txt, f, SUB_W)) > SUB_LINES:
            it = g[0]
            chunks = sentences(it['text'])
            edges = [0.0] + voice_bounds(it, chunks)
            V_EXACT[1] += len(chunks) - 1
            marks += [(it['off'] + e, c) for e, c in zip(edges, chunks)]
        else:
            marks.append((g[0]['off'], txt))
    V_EXACT[0] += len(groups) - 1
    items = []
    for k, (t0, c) in enumerate(marks):
        t1 = marks[k + 1][0] if k + 1 < len(marks) else sc['sec']
        items.append((t0, t1 - 0.05, subtitle_layer(c)))
    return items


def build_audio(starts, total, out_wav):
    import numpy as np
    buf = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for i in range(len(data)):
        for it in voice[i]:
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', it['path'], '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                                 capture_output=True).stdout
            a = np.frombuffer(raw, dtype=np.float32)
            p = int((starts[i] + it['off']) * SR)
            buf[p:p + len(a)] += a[:len(buf) - p]
    buf = buf[:int(total * SR)]
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-i', '-',
                    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', str(SR), out_wav], input=buf.tobytes(), check=True)


bases, subs, anchors, heads = [], [], [], []
for i, sc in enumerate(data):
    im = Image.open(os.path.join(IMGDIR, f'scene_{i + 1:02d}.png')).convert('RGB')
    bw = W
    bh = round(im.height * W / im.width)
    big = im.resize((bw, bh), Image.LANCZOS)
    ht = head_top(im)
    top_f = None if ht is None else ht * W / im.width - (bh - H)
    shift = 0 if WIDE or top_f is None or top_f >= HEAD_SAFE else int(HEAD_SAFE - top_f)   # 가로판은 위 판이 그림을 덮지 않음
    win = Image.new('RGB', (W, H), big.getpixel((W // 2, 5)))
    src_top = bh - H - shift
    win.paste(big.crop((0, max(0, src_top), W, bh - shift)), (0, max(0, -src_top)))
    if sc.get('board'):
        print(f'{i + 1}번 칠판 기호:', draw_board_symbol(win, sc['board']), flush=True)
    bases.append(win)
    anchors.append(min(1500, max(700, (top_f + shift + 200) if top_f is not None else 1300)))
    heads.append((None if top_f is None else round(top_f), shift))
    if voice:
        subs.append(voice_subs(i, sc))
        continue
    ss = sentences(sc['narration'])
    tot = sum(len(x) for x in ss)
    acc, items = 0.0, []
    for x in ss:
        d0 = sc['sec'] * acc / tot
        acc += len(x)
        items.append((d0, sc['sec'] * acc / tot, subtitle_layer(x)))
    subs.append(items)
card_cache = {}


PANEL_H, PANEL_FADE = 690, 110


def panel():
    # 화면 위쪽 전체를 덮는 판: 위는 연한 하늘색 → 아래로 흰색, 맨 아래 110칸은 서서히 투명해짐
    if 'p' not in card_cache:
        im = Image.new('RGBA', (W, PANEL_H + PANEL_FADE), (0, 0, 0, 0))
        px = im.load()
        top, bot = (226, 242, 250), (250, 252, 254)
        for y in range(PANEL_H + PANEL_FADE):
            k = min(1.0, y / PANEL_H)
            col = tuple(int(top[c] + (bot[c] - top[c]) * k) for c in range(3))
            a = 255 if y < PANEL_H else int(255 * (1 - (y - PANEL_H) / PANEL_FADE) ** 1.6)
            for x in range(W):
                px[x, y] = col + (a,)
        card_cache['p'] = im
    return card_cache['p']


def card():
    if 'c' not in card_cache:
        im, d = layer(W - 100, 520)
        d.rounded_rectangle((0, 0, W - 101, 519), radius=40, fill=(255, 255, 255, 228))
        card_cache['c'] = im
    return card_cache['c']


WCARD = (40, 15, 1140, 715)   # 가로판 왼쪽 도표 자리 (x0, y0, x1, y1) — 자막 띠 위 공간


def wide_card():
    # 가로판 도표 카드: 세로판 위 판과 같은 하늘색→흰색, 둥근 모서리
    if 'wc' not in card_cache:
        x0, y0, x1, y1 = WCARD
        cw, ch = x1 - x0, y1 - y0
        im = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        px = im.load()
        top, bot = (226, 242, 250), (250, 252, 254)
        for y in range(ch):
            k = y / ch
            col = tuple(int(top[c] + (bot[c] - top[c]) * k) for c in range(3)) + (255,)
            for x in range(cw):
                px[x, y] = col
        mask = Image.new('L', (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=44, fill=255)
        im.putalpha(mask)
        card_cache['wc'] = im
    return card_cache['wc']


def frame_wide(i, t):
    # 가로판 한 장: 바탕은 그림 바탕색, 오른쪽에 인물 그림(천천히 당겨 보임), 왼쪽 카드에 도표, 왼쪽 아래에 자막
    sc = data[i]
    base = bases[i]
    z = 1.0 + 0.045 * (t / sc['sec'])
    # 인물 크기는 처음 가로 견본(그림 전체를 화면 높이에 맞춘 비율)대로, 위쪽 빈 바탕은 잘라 내고 자막 띠 위에 세움(11/6 비광도기님)
    #   머리 꼭대기 120칸 위 ~ 그림 아래끝을 보여 주되, 띠 위 공간보다 크면 그만큼만 줄임
    top = heads[i][0]
    y_top = max(0, (top if top is not None else 300) - 120)
    roi_h = H - y_top
    s_ = min(OH / H, BAR_Y / roi_h)
    win_h = roi_h / z
    win_top = y_top + (roi_h - win_h) * 0.35
    ww = W / z
    cx = W / 2
    pic = base.crop((int(cx - ww / 2), int(win_top), int(cx + ww / 2), int(win_top + win_h)))
    pic = pic.resize((round(W * s_), round(roi_h * s_)), Image.BILINEAR)
    bgcol = base.getpixel((3, 3))
    can = Image.new('RGBA', (OW, OH), bgcol + (255,))
    # 그림 가장자리를 바탕색으로 서서히 녹여 네모 경계가 안 보이게 (도표 바탕을 없앤 뒤 드러남, 11/6)
    import numpy as np
    pw_, ph_ = pic.size   # 확대 중에는 그림 폭이 매 장 달라져 가림막을 저장해 두지 않고 매번 만듦(가벼움)
    fx = np.clip(np.minimum(np.arange(pw_), pw_ - 1 - np.arange(pw_)) / 90.0, 0, 1)
    fy = np.clip(np.arange(ph_) / 60.0, 0, 1)
    can.paste(pic, (1530 - pic.width // 2, BAR_Y - pic.height), Image.fromarray((np.outer(fy, fx) * 255).astype('uint8'), 'L'))
    if 'bar' not in card_cache:
        # 자막 띠 + 그 아래는 그림 바탕보다 한 톤 짙은 바닥색(11/6 비광도기님 B안 — 재생 막대가 없을 때 아래가 비어 보이지 않게)
        bar, bd = layer(OW, OH - BAR_Y)
        r_, g_, b_ = bgcol
        bd.rectangle((0, BAR_H, OW, OH), fill=(max(0, r_ - 22), max(0, g_ - 26), max(0, b_ - 34), 255))
        bd.rectangle((0, 0, OW, BAR_H), fill=(20, 30, 45, 235))
        card_cache['bar'] = bar
    put(can, card_cache['bar'], 0, BAR_Y, 1)
    # 도표 카드 바탕은 깔지 않음(11/6 비광도기님 "도표 바탕색은 없애자") — 도표가 그림 바탕 위에 바로 놓임
    lay_c = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if sc.get('chart'):
        draw_chart(lay_c, t, chart_for(i, sc))
    else:
        CHARTS[i](lay_c, t * sc.get('sec_old', sc['sec']) / sc['sec'])
    cx0, cy0, cx1, cy1 = WCARD
    ch_img = lay_c.crop((0, 0, W, cy1 - cy0 - 30))
    k = (cx1 - cx0) / W
    ch_img = ch_img.resize((int(W * k), int(ch_img.height * k)), Image.BILINEAR)
    can.alpha_composite(ch_img, (cx0, cy0 + 30))
    for d0, d1, lay in subs[i]:
        if d0 <= t < d1 + 0.05:
            put(can, lay, 0, BAR_Y, min(1, (t - d0) / 0.2 + 0.0001))
    return can.convert('RGB')


def frame(i, t):
    if WIDE:
        return frame_wide(i, t)
    sc = data[i]
    base = bases[i]
    z = 1.0 + 0.045 * (t / sc['sec'])
    cw, ch = W / z, H / z
    x0 = (W / 2) * (1 - 1 / z)
    y0 = anchors[i] * (1 - 1 / z)
    bg = base.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR).convert('RGBA')
    put(bg, panel(), 0, 0, 1)
    lay_c = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if sc.get('chart'):
        draw_chart(lay_c, t, chart_for(i, sc))
    else:
        CHARTS[i](lay_c, t * sc.get('sec_old', sc['sec']) / sc['sec'])   # 장면이 길어지면 차트도 같은 비율로 늦춤
    bg.alpha_composite(lay_c, (0, 30))
    for d0, d1, lay in subs[i]:
        if d0 <= t < d1 + 0.05:
            put(bg, lay, 50, 1390 - lay.height, min(1, (t - d0) / 0.2 + 0.0001))
    return bg.convert('RGB')


starts, tt = [], 0.0
for sc in data:
    starts.append(tt)
    tt += sc['sec']
TOTAL = tt
print('머리 꼭대기(원래 → 내린 칸):', [(k + 1, h0, sh) for k, (h0, sh) in enumerate(heads)], flush=True)
if os.environ.get('STILLS'):
    tw, th = (640, 360) if WIDE else (360, 640)
    sheet = Image.new('RGB', (tw * 5, th * 2), 'white')
    for i, sc in enumerate(data):
        fr = frame(i, sc['sec'] - XF - 0.05).resize((tw, th))
        sheet.paste(fr, ((i % 5) * tw, (i // 5) * th))
    sheet.save(OUT, quality=88)
    sys.exit(0)
if os.environ.get('SUBS'):
    for i in range(len(data)):
        for d0, d1, lay in subs[i]:
            print(f'{starts[i] + d0:.2f}\t{starts[i] + d1:.2f}\t{i + 1}')
    print(f'자막 경계: 구절 경계(정확) {V_EXACT[0]}곳 · 구절 안(음성인식) {V_EXACT[1]}곳')
    sys.exit(0)
if os.environ.get('MOCK'):
    sc_i, tt_ = [int(x) if k == 0 else float(x) for k, x in enumerate(os.environ['MOCK'].split(':'))]
    frame(sc_i, tt_).save(OUT)
    sys.exit(0)
if os.environ.get('ONE'):
    k, tt_ = os.environ['ONE'].split(':')
    frame(int(k), float(tt_)).save(OUT)
    sys.exit(0)
N = int(TOTAL * FPS)
VOUT = OUT + '.video.mp4' if voice else OUT
ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}', '-r', str(FPS), '-i', '-',
                       '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', VOUT], stdin=subprocess.PIPE)
for n in range(N):
    T = n / FPS
    i = max(k for k in range(len(starts)) if starts[k] <= T)
    t = T - starts[i]
    fr = frame(i, t)
    end = data[i]['sec']
    if i < len(data) - 1 and t > end - XF:
        nxt = frame(i + 1, 0.0)
        fr = Image.blend(fr, nxt, (t - (end - XF)) / XF)
    ff.stdin.write(fr.tobytes())
    if n % (FPS * 10) == 0:
        print(f'{n}/{N}', flush=True)
ff.stdin.close()
ff.wait()
if voice:
    wav = OUT + '.voice.wav'
    build_audio(starts, N / FPS, wav)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', VOUT, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', OUT], check=True)
    os.remove(VOUT)
    os.remove(wav)
print('done', TOTAL, 's')
if voice:
    print(f'자막 경계: 구절 경계(정확) {V_EXACT[0]}곳 · 구절 안(음성인식) {V_EXACT[1]}곳', flush=True)
