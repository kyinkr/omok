"""
렌주룰(Renju) 오목 규칙 모듈 - 15x15 판

규칙 요약
  - 흑이 먼저 두며, 첫 수는 천원(중앙)에 둔다.
  - 흑은 '정확히 5목'일 때만 승리한다.
  - 흑의 금수: 삼삼(3-3), 사사(4-4), 장목(6목 이상)
    (단, 5목이 동시에 완성되면 금수보다 5목이 우선 -> 흑 승리)
  - 백은 5목 이상이면 승리하며 금수가 없다.

보드는 가장자리에 벽(WALL)을 둘러싼 1차원 배열로 표현한다.
이렇게 하면 경계 검사를 따로 하지 않아도 되어 AI 탐색이 빨라진다.
"""

SIZE = 15
PAD = 5                      # 판 바깥 벽 두께 (AI 패턴 창 크기 ±5 에 맞춤)
W = SIZE + 2 * PAD           # 패딩 포함 한 줄의 폭
EMPTY, BLACK, WHITE, WALL = 0, 1, 2, 3

# 네 방향: 가로, 세로, 대각선(↘), 역대각선(↙)
DIRS = (1, W, W + 1, W - 1)

# 금수 판정에서 '삼'을 확인할 때의 재귀 깊이 한계
_MAX_THREE_DEPTH = 3

FORBID_33 = "삼삼"
FORBID_44 = "사사"
FORBID_OVERLINE = "장목"


def idx(x, y):
    """(x, y) 좌표 -> 1차원 인덱스"""
    return (y + PAD) * W + (x + PAD)


def to_xy(p):
    """1차원 인덱스 -> (x, y) 좌표"""
    return p % W - PAD, p // W - PAD


BOARD_CELLS = [idx(x, y) for y in range(SIZE) for x in range(SIZE)]
CENTER = idx(SIZE // 2, SIZE // 2)


def opponent(color):
    return BLACK if color == WHITE else WHITE


class Board:
    def __init__(self):
        self.cells = [WALL] * (W * W)
        for p in BOARD_CELLS:
            self.cells[p] = EMPTY
        self.moves = []          # [(p, color), ...]

    def copy(self):
        b = Board.__new__(Board)
        b.cells = self.cells[:]
        b.moves = self.moves[:]
        return b

    # ------------------------------------------------------------------ 기본
    def get(self, x, y):
        return self.cells[idx(x, y)]

    def turn(self):
        return BLACK if len(self.moves) % 2 == 0 else WHITE

    def is_full(self):
        return len(self.moves) >= SIZE * SIZE

    def place(self, p, color):
        self.cells[p] = color
        self.moves.append((p, color))

    def undo(self):
        p, c = self.moves.pop()
        self.cells[p] = EMPTY
        return p, c

    # ------------------------------------------------- 연속된 돌 (내부 도구)
    def _run(self, p, d, color):
        """p 를 지나는 d 방향 연속 color 돌의 양 끝 인덱스 (p 에 돌이 있다고 가정)"""
        c = self.cells
        lo = p
        while c[lo - d] == color:
            lo -= d
        hi = p
        while c[hi + d] == color:
            hi += d
        return lo, hi

    def _run_len(self, p, d, color):
        lo, hi = self._run(p, d, color)
        return (hi - lo) // d + 1

    def _makes_five(self, p, color):
        """p 에 놓인 돌이 5목(흑은 정확히 5, 백은 5 이상)을 만들었는가"""
        for d in DIRS:
            n = self._run_len(p, d, color)
            if n == 5 or (color == WHITE and n > 5):
                return True
        return False

    def _five_offsets(self, p, d, color):
        """d 방향에서 한 수 더 두면 p 를 포함한 5목이 되는 빈 자리들의 오프셋"""
        c = self.cells
        res = []
        for k in (-4, -3, -2, -1, 1, 2, 3, 4):
            q = p + k * d
            if c[q] != EMPTY:
                continue
            c[q] = color
            lo, hi = self._run(q, d, color)
            c[q] = EMPTY
            if lo <= p <= hi:
                n = (hi - lo) // d + 1
                if n == 5 or (color == WHITE and n > 5):
                    res.append(k)
        return res

    def _fours_in_dir(self, p, d, color):
        """d 방향에 있는 '4'의 개수 (열린 4는 1개, 한 줄 안의 사사는 2개)"""
        ks = self._five_offsets(p, d, color)
        if not ks:
            return 0
        if len(ks) == 2 and abs(ks[0] - ks[1]) == 5:
            return 1          # .XXXX.  -> 열린 4 (하나의 4)
        return 2 if len(ks) >= 2 else 1

    def _open_four_dir(self, p, d):
        """p 를 포함한 흑의 '열린 4'(양쪽 모두 정확히 5목이 되는 4)인가"""
        c = self.cells
        lo, hi = self._run(p, d, BLACK)
        if (hi - lo) // d + 1 != 4:
            return False
        return (c[lo - d] == EMPTY and c[hi + d] == EMPTY
                and c[lo - 2 * d] != BLACK and c[hi + 2 * d] != BLACK)

    def _three_dir(self, p, d, depth):
        """d 방향이 '삼'인가: 금수가 아닌 한 수로 열린 4를 만들 수 있으면 삼"""
        c = self.cells
        for k in (-3, -2, -1, 1, 2, 3):
            q = p + k * d
            if c[q] != EMPTY:
                continue
            c[q] = BLACK
            ok = self._open_four_dir(p, d) and self._forbidden_placed(q, depth + 1) is None
            c[q] = EMPTY
            if ok:
                return True
        return False

    def _forbidden_placed(self, p, depth=0):
        """흑돌이 p 에 놓였다고 가정하고 금수 사유를 반환 (금수가 아니면 None)"""
        if self._makes_five(p, BLACK):
            return None                      # 5목이 우선
        for d in DIRS:
            if self._run_len(p, d, BLACK) >= 6:
                return FORBID_OVERLINE
        fours = [self._fours_in_dir(p, d, BLACK) for d in DIRS]
        if sum(fours) >= 2:
            return FORBID_44
        if depth >= _MAX_THREE_DEPTH:
            return None
        threes = 0
        for i, d in enumerate(DIRS):
            if fours[i] == 0 and self._three_dir(p, d, depth):
                threes += 1
                if threes >= 2:
                    return FORBID_33
        return None

    # ------------------------------------------------------------ 공개 함수
    def forbidden_reason(self, p):
        """빈 자리 p 에 흑이 둘 때의 금수 사유 ('삼삼'/'사사'/'장목') 또는 None"""
        if self.cells[p] != EMPTY:
            return None
        self.cells[p] = BLACK
        try:
            return self._forbidden_placed(p, 0)
        finally:
            self.cells[p] = EMPTY

    def is_forbidden(self, p):
        return self.forbidden_reason(p) is not None

    def is_legal(self, p, color):
        if self.cells[p] != EMPTY:
            return False
        if color == BLACK and self.is_forbidden(p):
            return False
        return True

    def five_points(self, p, color):
        """p 의 돌(놓여 있음)과 함께 한 수로 5목이 되는 빈 자리 집합"""
        pts = set()
        for d in DIRS:
            for k in self._five_offsets(p, d, color):
                pts.add(p + k * d)
        return pts

    def winning_line(self, p, color):
        """p 에 둔 수로 승리했다면 5목 돌들의 인덱스 목록, 아니면 None"""
        for d in DIRS:
            lo, hi = self._run(p, d, color)
            n = (hi - lo) // d + 1
            if n == 5 or (color == WHITE and n > 5):
                return list(range(lo, hi + 1, d))
        return None
