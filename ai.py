"""
렌주룰 오목 AI

구성
  1) 즉시 승리 / 상대 5목 방어
  2) VCF 탐색 (연속 4로 몰아서 이기는 수순)
  3) 알파-베타 탐색 + 반복 심화 (패턴 기반 평가함수)
  4) 안전 확인: 고른 수를 둔 뒤 상대에게 VCF 가 생기면 다른 수로 교체

AI 가 흑일 때는 금수 자리에 두지 않고,
상대가 흑일 때는 상대의 금수 자리를 '막을 필요 없는 곳'으로 판단한다.
"""

import random
import time
from functools import lru_cache

from renju import (BLACK, WHITE, EMPTY, SIZE, W, DIRS, CENTER, BOARD_CELLS,
                   idx, to_xy, opponent)

# ------------------------------------------------------------- 모양 분류
NONE, TWO, OPEN2, THREE, OPEN3, FOUR, OPEN4, FIVE, OVERLINE = range(9)

WIN = 10 ** 8
INF = 10 ** 9

# noise = (점수 차 허용폭, 후보 수, 실수 확률)
#   허용폭 안에 드는 상위 후보 중 무작위로 고르고, '실수 확률'로 가끔 상위 후보 아무거나 둔다.
#   (즉시 승리·5목 방어는 난이도와 상관없이 항상 한다)
LEVELS = {
    "easy":   dict(time=0.5, max_depth=2, vcf=0,  safety=False, widths=(8, 6),
                   noise=(2500, 3, 0.1)),
    # 보통: 짧은 위협(VCT 3수)까지만 공격·방어
    "normal": dict(time=1.0, max_depth=4, vcf=8, vct=3, vct_time=0.3,
                   safety=True, safe_vcf=10, safe_vct=3, safe_n=12,
                   widths=(10, 8, 6), noise=None),
    # 어려움: 긴 위협(VCT 8수) 공격, 5수 위협 방어, 위협 인식 탐색
    "hard":   dict(time=4.5, max_depth=10, vcf=16, vct=8, vct_time=0.3, search_time=0.6,
                   safety=True, safe_time=0.7, safe_each=0.2, safe_vcf=16, safe_vct=5, safe_n=10,
                   threat_search=True, widths=(16, 12, 10, 8, 6), noise=None),
}


class Timeout(Exception):
    pass


@lru_cache(maxsize=None)
def _classify(s, exact):
    """
    길이 11 문자열(가운데 s[5] 가 방금 둔 내 돌 '1', '0'=빈칸, '2'=막힘)의
    한 방향 모양을 분류한다. exact=True 이면 흑(정확히 5목) 규칙.
    """
    lo = 5
    while lo > 0 and s[lo - 1] == '1':
        lo -= 1
    hi = 5
    while hi < 10 and s[hi + 1] == '1':
        hi += 1
    n = hi - lo + 1
    if n >= 5:
        return FIVE if (n == 5 or not exact) else OVERLINE

    # 한 수 더 두면 5목이 되는 자리의 개수
    fp = 0
    if lo > 0 and s[lo - 1] == '0':
        j, ext = lo - 2, 0
        while j >= 0 and s[j] == '1':
            ext += 1
            j -= 1
        n2 = n + 1 + ext
        if n2 == 5 or (not exact and n2 > 5):
            fp += 1
    if hi < 10 and s[hi + 1] == '0':
        j, ext = hi + 2, 0
        while j <= 10 and s[j] == '1':
            ext += 1
            j += 1
        n2 = n + 1 + ext
        if n2 == 5 or (not exact and n2 > 5):
            fp += 1
    if fp >= 2:
        return OPEN4
    if fp == 1:
        return FOUR

    best = NONE
    for i in range(1, 10):
        if s[i] != '0':
            continue
        r = _classify(s[:i] + '1' + s[i + 1:], exact)
        if r == OPEN4:
            return OPEN3
        if r == FOUR:
            best = max(best, THREE)
        elif r == OPEN3:
            best = max(best, OPEN2)
        elif r == THREE:
            best = max(best, TWO)
    return best


_SHAPE_MEMO = {}


def point_value(a):
    """네 방향 모양 목록 -> 그 자리의 가치"""
    if FIVE in a:
        return 10_000_000
    c4o = a.count(OPEN4)
    c4 = a.count(FOUR)
    c3 = a.count(OPEN3)
    if c4o or c4 >= 2:
        return 1_000_000
    if c4 and c3:
        return 500_000
    if c3 >= 2:
        return 100_000
    return (c4 * 2600 + c3 * 2500 + a.count(THREE) * 300
            + a.count(OPEN2) * 250 + a.count(TWO) * 30)


def needs_forbid_check(a):
    """흑 금수 가능성이 있는 모양인가 (정밀 판정이 필요한지 빠르게 거름)"""
    if FIVE in a:
        return False
    if OVERLINE in a or OPEN4 in a:
        return True
    return sum(1 for s in a if s in (OPEN3, FOUR)) >= 2


# ------------------------------------------------- 줄 단위 평가 (정적 평가)
def _build_lines():
    lines = []
    for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
        for y in range(SIZE):
            for x in range(SIZE):
                px, py = x - dx, y - dy
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    continue
                cells = []
                cx, cy = x, y
                while 0 <= cx < SIZE and 0 <= cy < SIZE:
                    cells.append(idx(cx, cy))
                    cx += dx
                    cy += dy
                if len(cells) >= 5:
                    lines.append(cells)
    return lines


LINES = _build_lines()
LINE_OF = {p: [] for p in BOARD_CELLS}
for _lid, _cells in enumerate(LINES):
    for _p in _cells:
        LINE_OF[_p].append(_lid)

_W_FIVE, _W_OPEN4, _W_FOUR, _W_OPEN3, _W_THREE, _W_OPEN2, _W_TWO = (
    1_000_000, 100_000, 3000, 2500, 300, 200, 30)

# (패턴, 점수, 4의 개수)  '1'=내 돌, '0'=빈칸, '2'=상대/벽
_PATTERNS = [
    ('11111', _W_FIVE, 0),
    ('011110', _W_OPEN4, 2),
    ('011112', _W_FOUR, 1), ('211110', _W_FOUR, 1),
    ('10111', _W_FOUR, 1), ('11011', _W_FOUR, 1), ('11101', _W_FOUR, 1),
    ('01110', _W_OPEN3, 0), ('010110', _W_OPEN3, 0), ('011010', _W_OPEN3, 0),
    ('2011102', _W_THREE - _W_OPEN3, 0),          # 양쪽이 좁은 01110 보정
    ('211100', _W_THREE, 0), ('001112', _W_THREE, 0),
    ('210110', _W_THREE, 0), ('011012', _W_THREE, 0),
    ('211010', _W_THREE, 0), ('010112', _W_THREE, 0),
    ('10011', _W_THREE, 0), ('11001', _W_THREE, 0), ('10101', _W_THREE, 0),
    ('001100', _W_OPEN2, 0), ('01010', _W_OPEN2, 0), ('010010', _W_OPEN2, 0),
    ('211000', _W_TWO, 0), ('000112', _W_TWO, 0),
    ('210100', _W_TWO, 0), ('001012', _W_TWO, 0),
    ('210010', _W_TWO, 0), ('010012', _W_TWO, 0), ('10001', _W_TWO, 0),
]

_SWAP = str.maketrans('12', '21')
_LINE_MEMO = {}


def _side_score(s):
    v = f = 0
    for pat, w, fc in _PATTERNS:
        n = s.count(pat)
        if n:
            v += n * w
            f += n * fc
    return v, f


def _line_value(key):
    r = _LINE_MEMO.get(key)
    if r is None:
        s = ''.join('012'[v] for v in key)      # 흑 기준 문자열
        vb, fb = _side_score('2' + s + '2')
        vw, fw = _side_score('2' + s.translate(_SWAP) + '2')
        r = (vb, vw, fb, fw)
        _LINE_MEMO[key] = r
    return r


# 후보 수: 돌에서 네 방향으로 2칸 이내
_NEIGH = [k * d for d in DIRS for k in (-2, -1, 1, 2)]

_rng = random.Random(20261125)
_ZOB = [[_rng.getrandbits(64) for _ in range(W * W)] for _ in range(3)]


class Engine:
    def __init__(self, board):
        self.b = board.copy()
        self.cells = self.b.cells
        self.stones = [p for p, _ in board.moves]
        self.line_vals = [(0, 0, 0, 0)] * len(LINES)
        self.score = [0, 0, 0]
        self.fours = [0, 0, 0]
        self.hash = 0
        for p in self.stones:
            self.hash ^= _ZOB[self.cells[p]][p]
        for lid in range(len(LINES)):
            self._update_line(lid)
        self.deadline = 0.0
        self.nodes = 0
        self.vcf_fail = set()
        self.vct_fail = set()
        self.threat_mode = False
        self.last_shapes = {}
        self.shape_cache = {}
        self.leaf_vcf = 0

    # ------------------------------------------------------------ 상태 변경
    def _update_line(self, lid):
        c = self.cells
        new = _line_value(bytes([c[i] for i in LINES[lid]]))
        old = self.line_vals[lid]
        self.score[BLACK] += new[0] - old[0]
        self.score[WHITE] += new[1] - old[1]
        self.fours[BLACK] += new[2] - old[2]
        self.fours[WHITE] += new[3] - old[3]
        self.line_vals[lid] = new

    def make(self, p, color):
        self.cells[p] = color
        self.stones.append(p)
        self.hash ^= _ZOB[color][p]
        for lid in LINE_OF[p]:
            self._update_line(lid)

    def unmake(self):
        p = self.stones.pop()
        self.hash ^= _ZOB[self.cells[p]][p]
        self.cells[p] = EMPTY
        for lid in LINE_OF[p]:
            self._update_line(lid)

    # ------------------------------------------------------------ 수 생성
    def candidates(self):
        c = self.cells
        s = set()
        for p in self.stones:
            for o in _NEIGH:
                q = p + o
                if c[q] == EMPTY:
                    s.add(q)
        return s

    def shapes(self, p, color):
        """국면 해시 기준으로 캐시한 모양 판정 (make/unmake 로 바뀐 판에서만 사용)"""
        key = (self.hash, p, color)
        r = self.shape_cache.get(key)
        if r is None:
            if len(self.shape_cache) > 400_000:
                self.shape_cache.clear()
            r = self.shapes_raw(p, color)
            self.shape_cache[key] = r
        return r

    def shapes_raw(self, p, color):
        """캐시 없이 현재 칸 배열로 바로 판정 (임시로 칸을 바꿔 볼 때 사용)"""
        c = self.cells
        out = []
        for d in DIRS:
            key = (color,) + tuple(c[p - 5 * d:p + 5 * d + 1:d])
            r = _SHAPE_MEMO.get(key)
            if r is None:
                s = ''.join('1' if v == color else ('0' if v == EMPTY else '2') for v in key[1:])
                r = _classify(s[:5] + '1' + s[6:], color == BLACK)
                _SHAPE_MEMO[key] = r
            out.append(r)
        return out

    def gen_moves(self, color):
        """(정렬된 [(점수, 자리)], 즉시 승리 자리, 상대의 5목 자리 목록)"""
        opp = opponent(color)
        res = []
        win = None
        opp5 = []
        sh = {}
        self.last_shapes = sh
        for p in self.candidates():
            a = self.shapes(p, color)
            d = self.shapes(p, opp)
            sh[p] = (a, d)
            if FIVE in a:
                win = p
            if FIVE in d:
                opp5.append(p)
            if color == BLACK and needs_forbid_check(a) and self.b.is_forbidden(p):
                continue                       # 흑의 금수 자리는 둘 수 없음
            va = point_value(a)
            vd = point_value(d)
            if opp == BLACK and vd >= 100_000 and needs_forbid_check(d) and self.b.is_forbidden(p):
                vd = 0                         # 상대(흑)의 금수 자리는 막을 필요 없음
            x, y = to_xy(p)
            center = -(abs(x - 7) + abs(y - 7))
            res.append((va + vd * 0.9 + center, p))
        res.sort(reverse=True)
        return res, win, opp5

    def threat_filter(self, color, moves, sh):
        """
        (위협 인식 모드) 상대의 5목 위협이 없을 때:
          - 내가 열린 4를 만들 수 있으면 ('win', None)
          - 상대에게 열린 3(열린 4를 만들 자리)이 있으면 막는 수 + 내 4 만 남김 ('cand', [...])
            막을 방법이 없으면 ('lose', None)
          - 그 밖에는 (None, None)
        """
        opp = opponent(color)
        for _, p in moves:
            if OPEN4 in sh[p][0]:
                return 'win', None
        T = []
        for p, (a, d) in sh.items():
            if OPEN4 in d:
                if opp == BLACK and needs_forbid_check(d) and self.b.is_forbidden(p):
                    continue
                T.append(p)
        if not T:
            return None, None
        cells = self.cells
        cand = []
        for _, p in moves:
            a = sh[p][0]
            if FOUR in a:
                cand.append(p)
                continue
            cells[p] = color
            still = any(cells[t] == EMPTY and OPEN4 in self.shapes_raw(t, opp) for t in T)
            cells[p] = EMPTY
            if not still:
                cand.append(p)
        if not cand:
            return 'lose', None
        return 'cand', cand

    # ------------------------------------------------------------ 평가/탐색
    def evaluate(self, color):
        return self.score[color] - self.score[opponent(color)]

    def search(self, color, depth, alpha, beta, ply, widths):
        self.nodes += 1
        if (self.nodes & 31) == 0 and time.perf_counter() > self.deadline:
            raise Timeout
        opp = opponent(color)
        if depth <= 0:
            if self.fours[color] > 0:
                return WIN - ply
            if self.leaf_vcf and self.fours[opp] == 0:
                # (어려움) 탐색 끝에서도 연속 4로 이기는 수순이 있는지 확인
                if self.vcf(color, self.leaf_vcf, None, self.deadline) is not None:
                    return WIN - ply - 10
            return self.evaluate(color)

        moves, win, opp5 = self.gen_moves(color)
        sh = self.last_shapes
        if win is not None:
            return WIN - ply
        if opp5:
            if len(opp5) >= 2:
                return -(WIN - ply - 1)
            q = opp5[0]
            if not any(m[1] == q for m in moves):     # 막을 자리가 흑의 금수
                return -(WIN - ply - 1)
            cand = [q]
        else:
            if not moves:
                return 0
            width = widths[min(ply, len(widths) - 1)]
            cand = [m[1] for m in moves[:width]]
            if self.threat_mode:
                st, tc = self.threat_filter(color, moves, sh)
                if st == 'win':
                    return WIN - ply - 2
                if st == 'lose':
                    return -(WIN - ply - 3)
                if st == 'cand':
                    cand = tc[:width + 4]

        best = -INF
        for p in cand:
            self.make(p, color)
            try:
                v = -self.search(opp, depth - 1, -beta, -alpha, ply + 1, widths)
            finally:
                self.unmake()
            if v > best:
                best = v
            if v > alpha:
                alpha = v
            if alpha >= beta:
                break
        return best

    def root_search(self, color, depth, order, widths):
        opp = opponent(color)
        alpha = -INF
        res = []
        for p in order:
            self.make(p, color)
            try:
                v = -self.search(opp, depth - 1, -INF, -alpha, 1, widths)
            finally:
                self.unmake()
            res.append((v, p))
            if v > alpha:
                alpha = v
        return res

    # ------------------------------------------------------------ VCF
    def vcf(self, color, depth, forced, deadline):
        """연속 4로 이기는 첫 수를 반환 (없으면 None). 상대에게 4가 없다는 전제."""
        if time.perf_counter() > deadline:
            raise Timeout
        key = (self.hash, color, forced)
        if key in self.vcf_fail:
            return None
        opp = opponent(color)
        cands = [forced] if forced is not None else self.candidates()
        fours = []
        for p in cands:
            a = self.shapes(p, color)
            if FIVE in a:
                return p
            if depth > 0 and (OPEN4 in a or FOUR in a):
                fours.append((OPEN4 in a, p, a))
        fours.sort(key=lambda t: t[0], reverse=True)

        for _, p, a in fours:
            if color == BLACK and needs_forbid_check(a) and self.b.is_forbidden(p):
                continue
            win = False
            self.make(p, color)
            try:
                fps = self.b.five_points(p, color)
                if len(fps) >= 2:
                    win = True
                elif len(fps) == 1:
                    q = next(iter(fps))
                    if opp == BLACK and self.b.is_forbidden(q):
                        win = True                # 흑은 금수라서 막을 수 없음
                    else:
                        self.make(q, opp)
                        try:
                            ofps = self.b.five_points(q, opp)
                            if not ofps:
                                win = self.vcf(color, depth - 1, None, deadline) is not None
                            elif len(ofps) == 1:
                                f = next(iter(ofps))
                                win = self.vcf(color, depth - 1, f, deadline) is not None
                        finally:
                            self.unmake()
            finally:
                self.unmake()
            if win:
                return p
        self.vcf_fail.add(key)
        return None

    # ------------------------------------------------------------ VCT
    def five_points_all(self, color):
        return [p for p in self.candidates() if FIVE in self.shapes(p, color)]

    def vct(self, A, depth, deadline):
        """
        연속 위협(4 또는 열린 3)으로 이기는 첫 수를 반환 (없으면 None).
        A = 공격자. 상대(D)의 방어는 '열린 4 자리를 막는 수' + '상대의 4(역공)'를 모두 따져 본다.
        """
        if time.perf_counter() > deadline:
            raise Timeout
        key = (self.hash, A, depth)
        if key in self.vct_fail:
            return None
        D = opponent(A)
        threats = []
        dfive = []
        for p in self.candidates():
            a = self.shapes(p, A)
            if FIVE in a:
                return p
            if FIVE in self.shapes(p, D):
                dfive.append(p)
            if OPEN4 in a or FOUR in a or OPEN3 in a:
                threats.append((point_value(a), p, a))
        if depth > 0:
            if dfive:
                # 상대의 5목 자리를 먼저 막아야 하며, 그 수가 위협이 될 때만 계속
                threats = [t for t in threats if t[1] == dfive[0]] if len(dfive) == 1 else []
            threats.sort(key=lambda t: t[0], reverse=True)
            for _, p, a in threats[:12]:
                if A == BLACK and needs_forbid_check(a) and self.b.is_forbidden(p):
                    continue
                self.make(p, A)
                try:
                    ok = self._vct_defend(A, depth - 1, deadline, p)
                finally:
                    self.unmake()
                if ok:
                    return p
        self.vct_fail.add(key)
        return None

    def _vct_defend(self, A, depth, deadline, p):
        """상대(D) 차례. A 가 방금 p 에 위협을 두었을 때 D 의 모든 방어에도 A 가 이기는가"""
        D = opponent(A)
        fps = self.five_points_all(A)
        if len(fps) >= 2:
            return True
        if len(fps) == 1:
            q = fps[0]
            if D == BLACK and self.b.is_forbidden(q):
                return True                       # 흑은 금수라서 막을 수 없음
            self.make(q, D)
            try:
                return self.vct(A, depth, deadline) is not None
            finally:
                self.unmake()

        # 열린 3 위협: A 가 열린 4를 만들 수 있는 자리들
        T = []
        for t in self.candidates():
            a = self.shapes(t, A)
            if OPEN4 in a and not (A == BLACK and self.b.is_forbidden(t)):
                T.append(t)
        if not T or depth <= 0:
            return False
        if self.vcf(D, 10, None, deadline) is not None:
            return False                          # D 가 먼저 4로 몰아 이김

        # 방어 후보: p 를 지나는 줄 위의 빈칸 + T. 두고 나서 T 가 모두 사라지면 방어 성공
        cells = self.cells
        pts = set(T)
        for d in DIRS:
            for k in range(-5, 6):
                q = p + k * d
                if cells[q] == EMPTY:
                    pts.add(q)
        defs = []
        for q in pts:
            cells[q] = D
            still = any(cells[t] == EMPTY and OPEN4 in self.shapes_raw(t, A) for t in T)
            cells[q] = EMPTY
            if not still:
                defs.append(q)
        # D 의 역공(4) 도 방어 수단
        for q in self.candidates():
            if q not in defs:
                d = self.shapes(q, D)
                if FOUR in d or OPEN4 in d:
                    defs.append(q)

        for q in defs:
            dsh = self.shapes(q, D)
            if D == BLACK and needs_forbid_check(dsh) and self.b.is_forbidden(q):
                continue
            self.make(q, D)
            try:
                dfp = self.b.five_points(q, D)
                if dfp:
                    if len(dfp) >= 2:
                        return False
                    f = next(iter(dfp))
                    if A == BLACK and self.b.is_forbidden(f):
                        return False
                    self.make(f, A)
                    try:
                        ok = self._vct_defend(A, depth, deadline, p)
                    finally:
                        self.unmake()
                else:
                    ok = self.vct(A, depth, deadline) is not None
            finally:
                self.unmake()
            if not ok:
                return False
        return True

    def _safe_after(self, p, color, s_vcf, s_vct, deadline):
        """방금 p 에 둔 뒤 상대가 강제 승리 수순을 갖지 않는가.
        p 가 4라면 상대가 막는 수까지 두어 본 뒤 확인한다 (막는 수로 역공당하는 것 방지)."""
        opp = opponent(color)
        fps = self.b.five_points(p, color)
        if len(fps) >= 2:
            return True
        if len(fps) == 1:
            q = next(iter(fps))
            if opp == BLACK and self.b.is_forbidden(q):
                return True
            self.make(q, opp)
            try:
                if self.b.five_points(q, opp):
                    return False                 # 막으면서 4를 만들면 위험
                return not self.opp_threat(opp, s_vcf, s_vct, deadline)
            finally:
                self.unmake()
        if self.five_points_all(color):
            return True                          # 다른 곳에 이미 4가 있음: 상대가 먼저 막아야 함
        return not self.opp_threat(opp, s_vcf, s_vct, deadline)

    def opp_threat(self, opp, vcf_depth, vct_depth, deadline):
        """opp(다음 차례)가 강제로 이기는 수순(VCF/VCT)을 가지고 있는가"""
        self.vcf_fail.clear()
        if self.vcf(opp, vcf_depth, None, deadline) is not None:
            return True
        if vct_depth:
            self.vct_fail.clear()
            if self.vct(opp, vct_depth, deadline) is not None:
                return True
        return False

    # ------------------------------------------------------------ 수 선택
    def choose(self, color, cfg):
        start = time.perf_counter()
        T = cfg["time"]
        opp = opponent(color)

        if not self.stones:
            return CENTER                       # 흑 첫 수는 천원
        if len(self.stones) == 1:
            p0 = self.stones[0]
            opts = [p0 + d * s for d in DIRS for s in (1, -1)
                    if self.cells[p0 + d * s] == EMPTY]
            if opts:
                return random.choice(opts)

        moves, win, opp5 = self.gen_moves(color)
        root_sh = self.last_shapes
        if win is not None:
            return win
        if opp5:
            legal = [p for _, p in moves if p in opp5]
            if legal:
                return legal[0]
            return moves[0][1] if moves else None
        if not moves:
            return None
        self.threat_mode = bool(cfg.get("threat_search"))
        self.leaf_vcf = cfg.get("leaf_vcf", 0)
        root_cand = None
        if self.threat_mode:
            st, tc = self.threat_filter(color, moves, root_sh)
            if st == 'win':
                return next(p for _, p in moves if OPEN4 in root_sh[p][0])
            if st == 'cand':
                root_cand = tc

        # 1) VCF: 연속 4로 이길 수 있는가
        if cfg["vcf"]:
            try:
                p = self.vcf(color, cfg["vcf"], None, start + T * 0.3)
                if p is not None:
                    return p
            except Timeout:
                pass
        # 1-2) VCT: 4와 열린 3을 섞은 연속 위협으로 이길 수 있는가
        if cfg.get("vct"):
            try:
                p = self.vct(color, cfg["vct"], start + T * cfg.get("vct_time", 0.3))
                if p is not None:
                    return p
            except Timeout:
                pass

        # 2) 알파-베타 반복 심화
        widths = cfg["widths"]
        order = [p for _, p in moves[:widths[0]]]
        if root_cand:
            order = root_cand[:widths[0] + 4]
        results = [(0, p) for p in order]
        self.deadline = start + T * (cfg.get("search_time", 0.75) if cfg["safety"] else 1.0)
        for depth in range(1, cfg["max_depth"] + 1):
            try:
                res = self.root_search(color, depth, order, widths)
            except Timeout:
                break
            res.sort(key=lambda t: -t[0])
            results = res
            order = [p for _, p in res]
            if abs(res[0][0]) >= WIN - 1000:
                break

        noise = cfg.get("noise")
        if noise and len(results) > 1 and results[0][0] < WIN - 1000:
            margin, top_n, blunder = noise
            if random.random() < blunder:
                return random.choice(results[:top_n])[1]
            top = [p for v, p in results[:top_n] if v >= results[0][0] - margin]
            return random.choice(top)

        # 3) 안전 확인: 둔 뒤 상대에게 강제 승리 수순(VCF/VCT)이 생기지 않는 수
        if cfg["safety"] and results[0][0] < WIN - 1000:
            now = time.perf_counter()
            deadline_all = now + T * cfg.get("safe_time", 0.5)
            s_vcf = cfg.get("safe_vcf", cfg["vcf"])
            s_vct = cfg.get("safe_vct", 0)
            check = [p for v, p in results[:cfg.get("safe_n", 6)] if v > -(WIN - 1000)]

            # 상대가 지금 '내가 손을 빼면' 이기는 수순의 첫 자리 = 급소. 우선 확인한다.
            try:
                w = self.vcf(opp, s_vcf, None, min(deadline_all, now + T * 0.1))
                if w is None and s_vct:
                    self.vct_fail.clear()
                    w = self.vct(opp, s_vct, min(deadline_all, now + T * 0.1))
            except Timeout:
                w = None
            if w is not None and any(p == w for _, p in moves):
                check = check[:1] + [w] + [p for p in check[1:] if p != w]

            def check_one(p, budget):
                self.make(p, color)
                try:
                    return self._safe_after(p, color, s_vcf, s_vct,
                                            min(deadline_all, time.perf_counter() + budget))
                except Timeout:
                    return None                  # 시간 안에 판정 못 함
                finally:
                    self.unmake()

            unknown = []
            for p in check:                      # 1차: 짧게 확인
                if time.perf_counter() > deadline_all:
                    break
                safe = check_one(p, T * cfg.get("safe_each", 0.12))
                if safe:
                    return p
                if safe is None:
                    unknown.append(p)
            for p in unknown:                    # 2차: 판정 못 한 수를 남은 시간으로 다시 확인
                if time.perf_counter() > deadline_all:
                    break
                if check_one(p, T):
                    return p
            if unknown:
                return unknown[0]                # 위험이 확인된 수보다는 판정 못 한 수
        return results[0][1]


def choose_move(board, color, level="normal"):
    """board(renju.Board) 에서 color 가 둘 자리(1차원 인덱스)를 반환"""
    cfg = LEVELS.get(level, LEVELS["normal"])
    return Engine(board).choose(color, cfg)
