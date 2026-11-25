"""
렌주룰 오목 - 사람 vs AI (pygame)

조작
  마우스 왼쪽 클릭 : 돌 두기
  U               : 무르기 (내 수 + AI 수)
  N               : 수순 번호 표시 켜기/끄기
  ESC             : 종료
"""

import asyncio
import os
import sys
import threading
import time

import pygame

# 브라우저(pygbag/WebAssembly)에서 실행 중인가. 웹에서는 스레드를 쓸 수 없다.
WEB = sys.platform == "emscripten"
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "NanumGothic-Regular.ttf")

from renju import (Board, BLACK, WHITE, EMPTY, SIZE, CENTER, BOARD_CELLS,
                   idx, to_xy, opponent)
from ai import choose_move

# ------------------------------------------------------------------ 화면 설정
CELL = 42
MARGIN = 46
BOARD_PX = MARGIN * 2 + CELL * (SIZE - 1)
PANEL_W = 300
WIN_W, WIN_H = BOARD_PX + PANEL_W, BOARD_PX
FPS = 60

COL_BG = (36, 40, 48)
COL_BOARD = (222, 184, 112)
COL_BOARD_EDGE = (176, 134, 70)
COL_LINE = (70, 48, 22)
COL_TEXT = (235, 235, 240)
COL_SUB = (160, 166, 180)
COL_ACCENT = (255, 196, 80)
COL_RED = (220, 50, 50)
COL_BTN = (60, 66, 80)
COL_BTN_HOVER = (78, 86, 104)
COL_BTN_ON = (190, 140, 60)

COLS = "ABCDEFGHIJKLMNO"
STAR_POINTS = [(3, 3), (11, 3), (7, 7), (3, 11), (11, 11)]
LEVEL_NAMES = [("easy", "쉬움"), ("normal", "보통"), ("hard", "어려움")]


def load_font(size, bold=False):
    if not WEB:
        for name in ("malgungothic", "applegothic", "nanumgothic", "notosanscjkkr", "gulim"):
            path = pygame.font.match_font(name, bold=bold)
            if path:
                return pygame.font.Font(path, size)
    if os.path.exists(FONT_PATH):            # 함께 배포하는 나눔고딕 (웹은 항상 이것)
        f = pygame.font.Font(FONT_PATH, size)
        f.set_bold(bold)
        return f
    return pygame.font.SysFont(None, size, bold=bold)


def to_px(x, y):
    return MARGIN + x * CELL, MARGIN + y * CELL


def coord_name(p):
    x, y = to_xy(p)
    return f"{COLS[x]}{SIZE - y}"


class Button:
    def __init__(self, rect, text, action):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.selected = False

    def draw(self, surf, font, mouse):
        if self.selected:
            col = COL_BTN_ON
        elif self.rect.collidepoint(mouse):
            col = COL_BTN_HOVER
        else:
            col = COL_BTN
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        label = font.render(self.text, True, COL_TEXT)
        surf.blit(label, label.get_rect(center=self.rect.center))


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("렌주룰 오목 - 사람 vs AI")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.f_title = load_font(30, bold=True)
        self.f_big = load_font(22, bold=True)
        self.f_mid = load_font(17)
        self.f_small = load_font(14)
        self.f_num = load_font(13, bold=True)
        self.f_banner = load_font(44, bold=True)

        self.level = "normal"
        self.show_numbers = False
        self.lock = threading.Lock()
        self.generation = 0
        self._build_buttons()
        self.new_game(BLACK)

    # ------------------------------------------------------------ UI 구성
    def _build_buttons(self):
        x0 = BOARD_PX + 20
        w = PANEL_W - 40
        self.buttons = [
            Button((x0, 250, w, 40), "흑(선공)으로 새 게임", lambda: self.new_game(BLACK)),
            Button((x0, 298, w, 40), "백(후공)으로 새 게임", lambda: self.new_game(WHITE)),
            Button((x0, 346, (w - 8) // 2, 40), "무르기 (U)", self.undo),
            Button((x0 + (w + 8) // 2, 346, (w - 8) // 2, 40), "수순 (N)", self.toggle_numbers),
        ]
        self.level_buttons = []
        bw = (w - 16) // 3
        for i, (key, name) in enumerate(LEVEL_NAMES):
            btn = Button((x0 + i * (bw + 8), 420, bw, 36), name,
                         lambda k=key: self.set_level(k))
            self.level_buttons.append((key, btn))

    def set_level(self, key):
        self.level = key

    def toggle_numbers(self):
        self.show_numbers = not self.show_numbers

    # ------------------------------------------------------------ 게임 진행
    def new_game(self, human_color):
        self.generation += 1
        self.board = Board()
        self.human = human_color
        self.ai_color = opponent(human_color)
        self.winner = None          # BLACK / WHITE / 0(무승부) / None
        self.win_line = []
        self.message = ""
        self.message_time = 0
        self.thinking = False
        self.ai_result = None
        self.forbidden_cache = None
        if human_color == BLACK:
            self.flash("첫 수는 천원(중앙)에 두세요.")

    def flash(self, text):
        self.message = text
        self.message_time = time.time()

    def play(self, p, color):
        self.board.place(p, color)
        self.forbidden_cache = None
        line = self.board.winning_line(p, color)
        if line:
            self.winner = color
            self.win_line = line
        elif self.board.is_full():
            self.winner = 0

    def undo(self):
        if self.thinking:
            self.flash("AI가 생각 중일 때는 무를 수 없습니다.")
            return
        if not any(c == self.human for _, c in self.board.moves):
            return
        while self.board.moves:
            _, c = self.board.undo()
            if c == self.human:
                break
        self.winner = None
        self.win_line = []
        self.forbidden_cache = None
        self.message = ""

    def forbidden_points(self):
        """사람이 흑일 때 현재 흑의 금수 자리 {인덱스: 사유}"""
        if self.forbidden_cache is None:
            res = {}
            b = self.board
            if self.winner is None and b.turn() == BLACK and self.human == BLACK:
                near = set()
                for p, c in b.moves:
                    if c != BLACK:
                        continue
                    x0, y0 = to_xy(p)
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            x, y = x0 + dx, y0 + dy
                            if 0 <= x < SIZE and 0 <= y < SIZE:
                                near.add(idx(x, y))
                for q in near:
                    if b.cells[q] == EMPTY:
                        r = b.forbidden_reason(q)
                        if r:
                            res[q] = r
            self.forbidden_cache = res
        return self.forbidden_cache

    def start_ai(self):
        self.thinking = True
        self.think_start = time.time()
        gen = self.generation
        board = self.board.copy()
        color = self.ai_color
        level = self.level

        def worker():
            p = choose_move(board, color, level)
            with self.lock:
                if gen == self.generation:
                    self.ai_result = p if p is not None else -1

        if WEB:
            self.sync_job = worker               # 다음 화면을 그린 뒤 메인 루프에서 실행
        else:
            threading.Thread(target=worker, daemon=True).start()

    def update_ai(self):
        if self.winner is not None:
            return
        if self.board.turn() == self.ai_color and not self.thinking:
            self.start_ai()
            return
        with self.lock:
            p, self.ai_result = self.ai_result, None
        if p is not None:
            self.thinking = False
            if p == -1:                        # 둘 곳이 없음 (흑이 금수만 남은 경우 등)
                self.winner = self.human
                self.flash("AI가 둘 수 있는 자리가 없습니다.")
                return
            self.play(p, self.ai_color)

    def mouse_to_cell(self, pos):
        mx, my = pos
        x = round((mx - MARGIN) / CELL)
        y = round((my - MARGIN) / CELL)
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            return None
        px, py = to_px(x, y)
        if (mx - px) ** 2 + (my - py) ** 2 > (CELL * 0.48) ** 2:
            return None
        return idx(x, y)

    def on_click(self, pos):
        for b in self.buttons:
            if b.rect.collidepoint(pos):
                b.action()
                return
        for _, b in self.level_buttons:
            if b.rect.collidepoint(pos):
                b.action()
                return

        if self.winner is not None or self.thinking:
            return
        if self.board.turn() != self.human:
            return
        p = self.mouse_to_cell(pos)
        if p is None or self.board.cells[p] != EMPTY:
            return
        if not self.board.moves and p != CENTER:
            self.flash("렌주룰: 흑의 첫 수는 천원(중앙)에만 둘 수 있습니다.")
            return
        if self.human == BLACK:
            reason = self.board.forbidden_reason(p)
            if reason:
                self.flash(f"금수 자리입니다! ({reason})")
                return
        self.message = ""
        self.play(p, self.human)

    # ------------------------------------------------------------ 그리기
    def draw_board(self, mouse):
        s = self.screen
        rect = pygame.Rect(8, 8, BOARD_PX - 16, BOARD_PX - 16)
        pygame.draw.rect(s, COL_BOARD, rect, border_radius=6)
        pygame.draw.rect(s, COL_BOARD_EDGE, rect, 3, border_radius=6)

        for i in range(SIZE):
            x0, y0 = to_px(0, i)
            x1, y1 = to_px(SIZE - 1, i)
            pygame.draw.line(s, COL_LINE, (x0, y0), (x1, y1), 2 if i in (0, SIZE - 1) else 1)
            x0, y0 = to_px(i, 0)
            x1, y1 = to_px(i, SIZE - 1)
            pygame.draw.line(s, COL_LINE, (x0, y0), (x1, y1), 2 if i in (0, SIZE - 1) else 1)
        for x, y in STAR_POINTS:
            pygame.draw.circle(s, COL_LINE, to_px(x, y), 4)

        for i in range(SIZE):
            t = self.f_small.render(COLS[i], True, COL_LINE)
            cx, _ = to_px(i, 0)
            s.blit(t, t.get_rect(center=(cx, MARGIN - 26)))
            s.blit(t, t.get_rect(center=(cx, BOARD_PX - MARGIN + 26)))
            t = self.f_small.render(str(SIZE - i), True, COL_LINE)
            _, cy = to_px(0, i)
            s.blit(t, t.get_rect(center=(MARGIN - 28, cy)))
            s.blit(t, t.get_rect(center=(BOARD_PX - MARGIN + 28, cy)))

        # 금수 표시
        forb = self.forbidden_points() if not self.thinking else {}
        for q in forb:
            cx, cy = to_px(*to_xy(q))
            r = 7
            pygame.draw.line(s, COL_RED, (cx - r, cy - r), (cx + r, cy + r), 3)
            pygame.draw.line(s, COL_RED, (cx - r, cy + r), (cx + r, cy - r), 3)

        # 돌
        last = self.board.moves[-1][0] if self.board.moves else None
        for n, (p, c) in enumerate(self.board.moves, 1):
            self.draw_stone(to_px(*to_xy(p)), c)
            if self.show_numbers:
                col = (240, 240, 240) if c == BLACK else (20, 20, 20)
                if p == last:
                    col = COL_RED
                t = self.f_num.render(str(n), True, col)
                s.blit(t, t.get_rect(center=to_px(*to_xy(p))))
        if last is not None and not self.show_numbers:
            pygame.draw.circle(s, COL_RED, to_px(*to_xy(last)), 5)

        # 승리 줄
        if self.win_line:
            a = to_px(*to_xy(self.win_line[0]))
            b = to_px(*to_xy(self.win_line[-1]))
            pygame.draw.line(s, COL_RED, a, b, 5)

        # 마우스 미리보기
        if (self.winner is None and not self.thinking
                and self.board.turn() == self.human and mouse[0] < BOARD_PX):
            p = self.mouse_to_cell(mouse)
            if p is not None and self.board.cells[p] == EMPTY and p not in forb:
                self.draw_stone(to_px(*to_xy(p)), self.human, alpha=110)

    def draw_stone(self, pos, color, alpha=255):
        r = CELL // 2 - 2
        surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        c = (r + 2, r + 2)
        if alpha == 255:
            pygame.draw.circle(surf, (0, 0, 0, 70), (c[0] + 2, c[1] + 2), r)
        if color == BLACK:
            pygame.draw.circle(surf, (22, 22, 24, alpha), c, r)
            pygame.draw.circle(surf, (85, 85, 92, alpha), (c[0] - r // 3, c[1] - r // 3), r // 4)
        else:
            pygame.draw.circle(surf, (244, 244, 240, alpha), c, r)
            pygame.draw.circle(surf, (150, 150, 150, alpha), c, r, 1)
            pygame.draw.circle(surf, (255, 255, 255, alpha), (c[0] - r // 3, c[1] - r // 3), r // 4)
        self.screen.blit(surf, (pos[0] - c[0], pos[1] - c[1]))

    def draw_panel(self, mouse):
        s = self.screen
        x0 = BOARD_PX + 20
        t = self.f_title.render("렌주룰 오목", True, COL_ACCENT)
        s.blit(t, (x0, 22))
        you = "흑 (선공)" if self.human == BLACK else "백 (후공)"
        ai = "백" if self.human == BLACK else "흑"
        s.blit(self.f_mid.render(f"당신: {you}", True, COL_TEXT), (x0, 72))
        s.blit(self.f_mid.render(f"AI: {ai}", True, COL_TEXT), (x0, 96))

        # 상태
        if self.winner is not None:
            if self.winner == 0:
                status, col = "무승부", COL_TEXT
            elif self.winner == self.human:
                status, col = "당신의 승리!", COL_ACCENT
            else:
                status, col = "AI의 승리...", COL_RED
        elif self.thinking:
            dots = "." * (int((time.time() - self.think_start) * 3) % 4)
            status, col = f"AI 생각 중{dots}", COL_SUB
        else:
            status, col = "당신의 차례", COL_TEXT
        s.blit(self.f_big.render(status, True, col), (x0, 132))

        info = f"{len(self.board.moves)}수"
        if self.board.moves:
            p, c = self.board.moves[-1]
            info += f"   마지막: {'흑' if c == BLACK else '백'} {coord_name(p)}"
        s.blit(self.f_small.render(info, True, COL_SUB), (x0, 166))

        if self.message and time.time() - self.message_time < 4:
            s.blit(self.f_small.render(self.message, True, COL_ACCENT), (x0, 196))

        for b in self.buttons:
            b.selected = (b.text.startswith("수순") and self.show_numbers)
            b.draw(s, self.f_mid, mouse)
        s.blit(self.f_small.render("AI 난이도", True, COL_SUB), (x0, 398))
        for key, b in self.level_buttons:
            b.selected = (key == self.level)
            b.draw(s, self.f_mid, mouse)

        rules = [
            "렌주룰",
            "· 흑이 먼저, 첫 수는 천원(중앙)",
            "· 흑 금수: 삼삼 · 사사 · 장목(6목+)",
            "· 흑은 정확히 5목일 때만 승리",
            "· 5목과 금수가 겹치면 5목 우선",
            "· 백은 5목 이상 승리, 금수 없음",
            "· 빨간 X = 현재 흑의 금수 자리",
        ]
        y = 480
        for i, line in enumerate(rules):
            f = self.f_mid if i == 0 else self.f_small
            s.blit(f.render(line, True, COL_TEXT if i == 0 else COL_SUB), (x0, y))
            y += 26 if i == 0 else 22

    def draw_banner(self):
        if self.winner is None:
            return
        if self.winner == 0:
            text = "무승부"
        else:
            text = ("흑" if self.winner == BLACK else "백") + " 승리!"
        t = self.f_banner.render(text, True, (255, 255, 255))
        box = t.get_rect(center=(BOARD_PX // 2, BOARD_PX // 2)).inflate(60, 30)
        overlay = pygame.Surface(box.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, box.topleft)
        self.screen.blit(t, t.get_rect(center=box.center))

    # ------------------------------------------------------------ 메인 루프
    async def run(self):
        self.sync_job = None
        while True:
            mouse = pygame.mouse.get_pos()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit()
                    return
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.on_click(e.pos)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE and not WEB:
                        pygame.quit()
                        return
                    elif e.key == pygame.K_u:
                        self.undo()
                    elif e.key == pygame.K_n:
                        self.toggle_numbers()

            self.update_ai()

            self.screen.fill(COL_BG)
            self.draw_board(mouse)
            self.draw_panel(mouse)
            self.draw_banner()
            pygame.display.flip()
            self.clock.tick(FPS)
            await asyncio.sleep(0)               # 브라우저에 제어를 돌려줌 (pygbag 필수)

            if self.sync_job is not None:        # 웹: '생각 중' 화면을 먼저 보여 준 뒤 계산
                job, self.sync_job = self.sync_job, None
                await asyncio.sleep(0)
                job()


if __name__ == "__main__":
    asyncio.run(Game().run())
