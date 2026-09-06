# gui_server.py  —  PyGame GUI for Alice (Server)

import pygame
import threading
import socket
import os
import sys
import random
import numpy as np
import datetime
import math
import tkinter as tk
from tkinter import filedialog

sys.path.insert(0, os.path.dirname(__file__))

from e91.quantum_engine import QuantumEngine
from e91.key_generator  import KeyGenerator
from e91.encryptor      import QuantumEncryptor
from utils.logger       import QuantumLogger
from utils.image_transfer import send_image, receive_image, SUPPORTED_TYPES
from utils.protocol import (
    send_message, receive_message, hash_key,
    MSG_BASIS_COMPARE, MSG_CHSH_RESULT, MSG_KEY_HASH,
    MSG_READY, MSG_CHAT, MSG_ABORT, MSG_ERROR_RATE,
    MSG_IMAGE_HEADER, MSG_IMAGE_CHUNK, MSG_IMAGE_DONE, MSG_IMAGE_ACK
)

# ══════════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ══════════════════════════════════════════════════════════════════════════════
C_BG          = (  8,  10,  18)
C_PANEL       = ( 15,  18,  32)
C_PANEL2      = ( 20,  24,  44)
C_BORDER      = ( 40,  50,  90)
C_BORDER_LIT  = ( 80, 120, 220)
C_ACCENT      = ( 80, 140, 255)
C_ACCENT2     = (140,  80, 255)
C_ACCENT3     = ( 80, 220, 180)
C_TEXT        = (210, 220, 240)
C_TEXT_DIM    = (100, 115, 150)
C_TEXT_BRIGHT = (240, 245, 255)
C_SENT        = ( 80, 160, 255)
C_RECV        = ( 60,  60,  90)
C_SUCCESS     = ( 60, 200, 120)
C_WARNING     = (255, 180,  50)
C_ERROR       = (220,  70,  70)
C_QUANTUM     = (180,  80, 255)

# ══════════════════════════════════════════════════════════════════════════════
#  PARTICLE SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class Particle:
    def __init__(self, w, h):
        self.reset(w, h)

    def reset(self, w, h):
        self.x        = np.random.randint(0, w)
        self.y        = np.random.randint(0, h)
        self.vx       = np.random.uniform(-0.3, 0.3)
        self.vy       = np.random.uniform(-0.5, -0.1)
        self.r        = np.random.uniform(0.5, 2.0)
        self.life     = np.random.uniform(0.3, 1.0)
        self.max_life = self.life
        self.color    = random.choice([C_ACCENT, C_ACCENT2, C_ACCENT3, C_QUANTUM])

    def update(self, w, h, dt):
        self.x    += self.vx * dt * 60
        self.y    += self.vy * dt * 60
        self.life -= dt * 0.08
        if self.life <= 0 or self.y < 0:
            self.reset(w, h)
            self.y = h

    def draw(self, surf):
        alpha = max(0, self.life / self.max_life)
        r, g, b = self.color
        c = (int(r * alpha), int(g * alpha), int(b * alpha))
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), max(1, int(self.r)))


class ParticleSystem:
    def __init__(self, w, h, count=80):
        self.particles = [Particle(w, h) for _ in range(count)]
        self.w, self.h = w, h

    def update(self, dt):
        for p in self.particles:
            p.update(self.w, self.h, dt)

    def draw(self, surf):
        for p in self.particles:
            p.draw(surf)


# ══════════════════════════════════════════════════════════════════════════════
#  BUTTON
# ══════════════════════════════════════════════════════════════════════════════

class Button:
    def __init__(self, rect, text, color=None, font=None,
                 text_color=None, border_radius=10):
        self.rect          = pygame.Rect(rect)
        self.text          = text
        self.color         = color or C_ACCENT
        self.text_color    = text_color or C_TEXT_BRIGHT
        self.font          = font
        self.border_radius = border_radius
        self.hover         = False
        self.press_anim    = 0.0

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.press_anim = 1.0
                return True
        return False

    def update(self, dt):
        if self.press_anim > 0:
            self.press_anim = max(0, self.press_anim - dt * 4)

    def draw(self, surf):
        if self.hover or self.press_anim > 0:
            glow = pygame.Surface(
                (self.rect.w + 20, self.rect.h + 20), pygame.SRCALPHA
            )
            t = max(self.hover * 0.4, self.press_anim)
            r, g, b = self.color
            pygame.draw.rect(
                glow, (r, g, b, int(60 * t)),
                (0, 0, self.rect.w + 20, self.rect.h + 20),
                border_radius=self.border_radius + 4
            )
            surf.blit(glow, (self.rect.x - 10, self.rect.y - 10))

        col = self.color
        if self.hover:
            col = tuple(min(255, c + 30) for c in col)
        if self.press_anim > 0:
            col = tuple(min(255, c + 60) for c in col)

        pygame.draw.rect(surf, col, self.rect, border_radius=self.border_radius)
        border_col = C_BORDER_LIT if self.hover else C_BORDER
        pygame.draw.rect(surf, border_col, self.rect, 1,
                         border_radius=self.border_radius)

        if self.font:
            lbl = self.font.render(self.text, True, self.text_color)
            surf.blit(lbl, lbl.get_rect(center=self.rect.center))


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT BUBBLE
# ══════════════════════════════════════════════════════════════════════════════

class ChatBubble:
    def __init__(self, text, sender, is_sent, font, timestamp,
                 bubble_type='text', max_width=520):
        self.text        = text
        self.sender      = sender
        self.is_sent     = is_sent
        self.font        = font
        self.timestamp   = timestamp
        self.bubble_type = bubble_type
        self.max_width   = max_width
        self.alpha       = 0.0
        self._wrap_cache = None
        self.height      = 0
        self._build()

    def _build(self):
        self._wrap_cache = self._wrap_text(self.text, self.max_width - 32)
        line_h           = self.font.get_height() + 3
        n_lines          = max(1, len(self._wrap_cache))
        self.height      = 22 + n_lines * line_h + 20

    def _wrap_text(self, text, max_w):
        words  = text.split(' ')
        lines  = []
        cur    = ''
        for word in words:
            test = (cur + ' ' + word).strip()
            if self.font.size(test)[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or ['']

    def draw(self, surf, x, y):
        alpha = min(1.0, self.alpha)
        if alpha <= 0:
            return y + self.height

        if self.bubble_type == 'system':
            bg, bord = (25, 30, 55), C_ACCENT3
        elif self.is_sent:
            bg, bord = (30, 55, 100), C_SENT
        else:
            bg, bord = (28, 30, 58), C_ACCENT2

        bubble_surf = pygame.Surface((self.max_width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(
            bubble_surf, (*bg, int(220 * alpha)),
            (0, 0, self.max_width, self.height), border_radius=14
        )
        pygame.draw.rect(
            bubble_surf, (*bord, int(180 * alpha)),
            (0, 0, self.max_width, self.height), 1, border_radius=14
        )

        if self.bubble_type == 'system':
            slbl = self.font.render(f"  ⚛  {self.sender}", True,
                                    (*C_ACCENT3, int(255 * alpha)))
        elif self.is_sent:
            slbl = self.font.render(f"  You  ·  {self.timestamp}", True,
                                    (*C_SENT, int(200 * alpha)))
        else:
            slbl = self.font.render(f"  {self.sender}  ·  {self.timestamp}", True,
                                    (*C_ACCENT2, int(200 * alpha)))
        bubble_surf.blit(slbl, (10, 6))

        line_h = self.font.get_height() + 3
        for i, line in enumerate(self._wrap_cache):
            lbl = self.font.render(line, True, (*C_TEXT, int(255 * alpha)))
            bubble_surf.blit(lbl, (16, 26 + i * line_h))

        surf.blit(bubble_surf, (x, y))
        return y + self.height + 8


# ══════════════════════════════════════════════════════════════════════════════
#  PROGRESS BAR
# ══════════════════════════════════════════════════════════════════════════════

class ProgressBar:
    def __init__(self, rect, color=C_ACCENT3):
        self.rect    = pygame.Rect(rect)
        self.color   = color
        self.value   = 0.0
        self.target  = 0.0
        self.visible = False
        self._anim   = 0.0

    def set(self, pct):
        self.target  = pct / 100
        self.visible = True

    def hide(self):
        self.visible = False
        self.value   = 0.0
        self.target  = 0.0

    def update(self, dt):
        self._anim += dt * 2
        if self.value < self.target:
            self.value = min(self.target, self.value + dt * 1.5)

    def draw(self, surf):
        if not self.visible:
            return
        pygame.draw.rect(surf, C_PANEL2, self.rect, border_radius=6)
        pygame.draw.rect(surf, C_BORDER,  self.rect, 1, border_radius=6)
        fill_w = int(self.rect.w * self.value)
        if fill_w > 0:
            fill = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.h)
            pygame.draw.rect(surf, self.color, fill, border_radius=6)
            sx = self.rect.x + int((math.sin(self._anim) * 0.5 + 0.5) * fill_w)
            for i in range(3):
                shimmer_x = sx - i * 8
                if self.rect.x < shimmer_x < self.rect.x + fill_w:
                    pygame.draw.rect(
                        surf, (255, 255, 255),
                        (shimmer_x, self.rect.y, 3, self.rect.h),
                        border_radius=2
                    )


# ══════════════════════════════════════════════════════════════════════════════
#  QUANTUM VISUALISER
# ══════════════════════════════════════════════════════════════════════════════

class QuantumVisualiser:
    def __init__(self, cx, cy, radius=60):
        self.cx     = cx
        self.cy     = cy
        self.radius = radius
        self.angle  = 0.0
        self.active = False
        self.phase  = 0.0

    def update(self, dt):
        if self.active:
            self.angle += dt * 1.2
            self.phase  += dt * 3

    def draw(self, surf):
        if not self.active:
            return
        cx, cy, r = self.cx, self.cy, self.radius
        pygame.draw.circle(surf, C_BORDER, (cx, cy), r, 1)

        for i, col in enumerate([C_ACCENT, C_ACCENT2]):
            ang = self.angle + i * math.pi
            x   = int(cx + math.cos(ang) * r)
            y   = int(cy + math.sin(ang) * r)
            gs  = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(gs, (*col, 80), (15, 15), 12)
            surf.blit(gs, (x - 15, y - 15))
            pygame.draw.circle(surf, col, (x, y), 5)

        x1 = int(cx + math.cos(self.angle) * r)
        y1 = int(cy + math.sin(self.angle) * r)
        x2 = int(cx + math.cos(self.angle + math.pi) * r)
        y2 = int(cy + math.sin(self.angle + math.pi) * r)
        pygame.draw.line(surf, (*C_ACCENT3, 120), (x1, y1), (x2, y2), 1)

        pulse = (math.sin(self.phase) * 0.5 + 0.5)
        gs2   = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(gs2, (*C_QUANTUM, int(100 * pulse)),
                           (14, 14), int(8 + 4 * pulse))
        surf.blit(gs2, (cx - 14, cy - 14))
        pygame.draw.circle(surf, C_QUANTUM, (cx, cy), 4)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class QuantumChatApp:
    W, H      = 1280, 780
    HEADER_H  = 70
    FOOTER_H  = 68
    LEFT_W    = 310
    LOG_H     = 110

    def __init__(self, role='server'):
        self.role       = role
        self.my_name    = ''
        self.peer_name  = ''
        self.running    = True

        self.state      = 'NAME_INPUT'
        self.status_msg = 'Enter your name to begin'
        self.status_col = C_ACCENT

        self.encryptor   = None
        self.logger      = None
        self.conn_sock   = None
        self.server_sock = None

        self.bubbles      = []
        self.chat_scroll  = 0
        self.chat_total_h = 0

        self.log_lines = []
        self.MAX_LOG   = 18

        self.input_text   = ''
        self.input_active = False
        self.cursor_blink = 0.0
        self.show_cursor  = True

        self.progress = None

        self.chsh_s      = 0.0
        self.chsh_secure = False
        self.key_hex     = ''
        self.n_key_bits  = 0

        self.t         = 0.0
        self.qvis      = None
        self.particles = None

        self._lock          = threading.Lock()
        self._pending_calls = []

    # ──────────────────────────────────────────────────────────────────────────
    #  BOOTSTRAP
    # ──────────────────────────────────────────────────────────────────────────

    def run(self):
        pygame.init()
        pygame.display.set_caption("⚛  Quantum Encrypted Chat  —  SERVER")

        try:
            ico = pygame.Surface((32, 32))
            ico.fill(C_BG)
            pygame.draw.circle(ico, C_QUANTUM, (16, 16), 10, 2)
            pygame.display.set_icon(ico)
        except Exception:
            pass

        self.screen = pygame.display.set_mode((self.W, self.H))
        self.clock  = pygame.time.Clock()

        def font(size, bold=False):
            try:
                name = 'DejaVuSans-Bold' if bold else 'DejaVuSans'
                return pygame.font.SysFont(name, size)
            except Exception:
                return pygame.font.SysFont('Arial', size, bold=bold)

        self.f_title = font(26, bold=True)
        self.f_sub   = font(16, bold=True)
        self.f_body  = font(15)
        self.f_small = font(13)
        self.f_tiny  = font(11)
        self.f_input = font(16)
        self.f_mono  = pygame.font.SysFont('Courier New', 13)

        chat_x = self.LEFT_W + 12
        chat_w = self.W - chat_x - 10

        self.progress = ProgressBar(
            (chat_x, self.H - self.FOOTER_H - self.LOG_H - 24, chat_w, 14),
            color=C_ACCENT3
        )

        self.qvis      = QuantumVisualiser(self.LEFT_W // 2,
                                           self.HEADER_H + 130, radius=58)
        self.particles = ParticleSystem(self.W, self.H, count=60)

        self.btn_send = Button(
            rect          = (self.W - 100, self.H - self.FOOTER_H + 10, 90, 44),
            text          = 'SEND',
            color         = C_ACCENT,
            font          = self.f_sub,
            text_color    = C_TEXT_BRIGHT,
            border_radius = 10
        )
        self.btn_send_img = Button(
            rect          = (14, self.H - self.FOOTER_H - 60, self.LEFT_W - 28, 38),
            text          = '📁  Send Image',
            color         = C_ACCENT2,
            font          = self.f_body,
            text_color    = C_TEXT_BRIGHT,
            border_radius = 8
        )
        self.btn_name_ok = Button(
            rect          = (self.W // 2 - 80, self.H // 2 + 20, 160, 44),
            text          = 'Connect',
            color         = C_ACCENT,
            font          = self.f_sub,
            text_color    = C_TEXT_BRIGHT,
            border_radius = 10
        )

        self.main_loop()

    # ──────────────────────────────────────────────────────────────────────────
    #  MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def main_loop(self):
        while self.running:
            dt = self.clock.tick(60) / 1000

            with self._lock:
                calls = self._pending_calls[:]
                self._pending_calls.clear()
            for fn in calls:
                fn()

            self._handle_events()
            self._update(dt)
            self._draw()
            pygame.display.flip()

        pygame.quit()

    # ──────────────────────────────────────────────────────────────────────────
    #  EVENTS
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            # ── NAME INPUT ───────────────────────────────────────
            if self.state == 'NAME_INPUT':
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self._confirm_name()
                    elif event.key == pygame.K_BACKSPACE:
                        self.my_name = self.my_name[:-1]
                    else:
                        if len(self.my_name) < 24 and event.unicode.isprintable():
                            self.my_name += event.unicode

                if self.btn_name_ok.handle_event(event):
                    self._confirm_name()

            # ── CHAT ─────────────────────────────────────────────
            elif self.state == 'CHAT':
                if event.type == pygame.MOUSEWHEEL:
                    self.chat_scroll = max(0, self.chat_scroll - event.y * 30)

                chat_input_rect = pygame.Rect(
                    self.LEFT_W + 12, self.H - self.FOOTER_H + 10,
                    self.W - self.LEFT_W - 120, 44
                )
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.input_active = chat_input_rect.collidepoint(event.pos)

                if event.type == pygame.KEYDOWN and self.input_active:
                    if event.key == pygame.K_RETURN:
                        self._send_chat_message()
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    elif event.key == pygame.K_v and (
                        pygame.key.get_mods() & pygame.KMOD_META or
                        pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        self._paste_clipboard()
                    else:
                        if len(self.input_text) < 400 and event.unicode.isprintable():
                            self.input_text += event.unicode

                # Send button
                if self.btn_send.handle_event(event):
                    self._send_chat_message()

                # Image button — opens native file picker
                if self.btn_send_img.handle_event(event):
                    self._pick_image_file()

            # Button animations always update
            self.btn_send.handle_event(event)
            self.btn_name_ok.handle_event(event)
            if self.state == 'CHAT':
                self.btn_send_img.handle_event(event)

    # ──────────────────────────────────────────────────────────────────────────
    #  UPDATE
    # ──────────────────────────────────────────────────────────────────────────

    def _update(self, dt):
        self.t += dt
        self.particles.update(dt)
        self.qvis.update(dt)
        self.progress.update(dt)
        self.btn_send.update(dt)
        self.btn_send_img.update(dt)
        self.btn_name_ok.update(dt)

        self.cursor_blink += dt
        if self.cursor_blink > 0.53:
            self.cursor_blink = 0
            self.show_cursor  = not self.show_cursor

        for b in self.bubbles:
            if b.alpha < 1.0:
                b.alpha = min(1.0, b.alpha + dt * 4)

    # ──────────────────────────────────────────────────────────────────────────
    #  DRAW MASTER
    # ──────────────────────────────────────────────────────────────────────────

    def _draw(self):
        self.screen.fill(C_BG)
        self.particles.draw(self.screen)
        self._draw_header()
        self._draw_left_panel()
        self._draw_right_panel()
        self._draw_footer()
        if self.state == 'NAME_INPUT':
            self._draw_name_overlay()

    # ──────────────────────────────────────────────────────────────────────────
    #  HEADER
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_header(self):
        hdr = pygame.Surface((self.W, self.HEADER_H), pygame.SRCALPHA)
        hdr.fill((*C_PANEL, 220))
        self.screen.blit(hdr, (0, 0))
        pygame.draw.line(self.screen, C_BORDER_LIT,
                         (0, self.HEADER_H), (self.W, self.HEADER_H), 1)

        pygame.draw.circle(self.screen, C_QUANTUM, (36, self.HEADER_H // 2), 14, 2)
        pygame.draw.circle(self.screen, C_ACCENT,  (36, self.HEADER_H // 2),  5)

        title_lbl = self.f_title.render("⚛  Quantum Chat", True, C_TEXT_BRIGHT)
        self.screen.blit(title_lbl,
                         (56, self.HEADER_H // 2 - title_lbl.get_height() // 2))

        role_lbl = self.f_small.render("  SERVER  ", True, C_BG)
        role_bg  = pygame.Rect(220, 18, role_lbl.get_width() + 10, 26)
        pygame.draw.rect(self.screen, C_ACCENT3, role_bg, border_radius=5)
        self.screen.blit(role_lbl, (role_bg.x + 5, role_bg.y + 5))

        st_lbl = self.f_body.render(self.status_msg, True, self.status_col)
        sx     = self.W - st_lbl.get_width() - 24
        sy     = self.HEADER_H // 2 - st_lbl.get_height() // 2
        pill   = pygame.Rect(sx - 10, sy - 4,
                              st_lbl.get_width() + 20, st_lbl.get_height() + 8)
        pill_surf = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        pygame.draw.rect(pill_surf, (*self.status_col, 30),
                         (0, 0, pill.w, pill.h), border_radius=12)
        pygame.draw.rect(pill_surf, (*self.status_col, 80),
                         (0, 0, pill.w, pill.h), 1, border_radius=12)
        self.screen.blit(pill_surf, (pill.x, pill.y))
        self.screen.blit(st_lbl, (sx, sy))

        if self.peer_name:
            pn = self.f_small.render(f"⬡  {self.peer_name}", True, C_TEXT_DIM)
            self.screen.blit(pn, (self.W // 2 - pn.get_width() // 2,
                                   self.HEADER_H // 2 - pn.get_height() // 2))

    # ──────────────────────────────────────────────────────────────────────────
    #  LEFT PANEL
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_left_panel(self):
        panel_rect = pygame.Rect(0, self.HEADER_H, self.LEFT_W,
                                  self.H - self.HEADER_H)
        ps = pygame.Surface((panel_rect.w, panel_rect.h), pygame.SRCALPHA)
        ps.fill((*C_PANEL, 200))
        self.screen.blit(ps, panel_rect.topleft)
        pygame.draw.line(self.screen, C_BORDER,
                         (self.LEFT_W, self.HEADER_H), (self.LEFT_W, self.H), 1)

        y = self.HEADER_H + 12

        # Section: Quantum Channel
        sec_lbl = self.f_sub.render("QUANTUM CHANNEL", True, C_ACCENT)
        self.screen.blit(sec_lbl, (14, y)); y += 22
        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8

        self.qvis.cx = self.LEFT_W // 2
        self.qvis.cy = y + 68
        self.qvis.draw(self.screen)
        y += 140

        if self.chsh_s > 0:
            s_col = C_SUCCESS if self.chsh_secure else C_ERROR
            sv    = self.f_sub.render(f"S = {self.chsh_s:.4f}", True, s_col)
            self.screen.blit(sv, (self.LEFT_W // 2 - sv.get_width() // 2, y)); y += 22
            bound = self.f_small.render(
                "Classical ≤ 2.0  |  Quantum ≤ 2√2", True, C_TEXT_DIM)
            self.screen.blit(bound,
                             (self.LEFT_W // 2 - bound.get_width() // 2, y)); y += 22
            verdict = "✅ SECURE" if self.chsh_secure else "❌ INSECURE"
            vl = self.f_body.render(verdict, True, s_col)
            self.screen.blit(vl,
                             (self.LEFT_W // 2 - vl.get_width() // 2, y)); y += 30
        else:
            ph = self.f_small.render("CHSH test pending...", True, C_TEXT_DIM)
            self.screen.blit(ph,
                             (self.LEFT_W // 2 - ph.get_width() // 2, y)); y += 30

        # Section: Key
        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8
        kl = self.f_sub.render("SESSION KEY", True, C_ACCENT)
        self.screen.blit(kl, (14, y)); y += 20

        if self.key_hex:
            blocks = [self.key_hex[i:i + 8] for i in range(0, len(self.key_hex), 8)]
            for bi, blk in enumerate(blocks[:4]):
                blbl = self.f_mono.render(blk, True, C_ACCENT3)
                self.screen.blit(blbl, (14 + bi * 72, y))
            y += 20
            bits_lbl = self.f_small.render("128-bit AES-stream key", True, C_TEXT_DIM)
            self.screen.blit(bits_lbl, (14, y)); y += 20
        else:
            nl = self.f_small.render("No key yet", True, C_TEXT_DIM)
            self.screen.blit(nl, (14, y)); y += 20

        # Section: Stats
        y += 10
        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8
        sl = self.f_sub.render("SESSION STATS", True, C_ACCENT)
        self.screen.blit(sl, (14, y)); y += 20

        if self.logger:
            stats = self.logger.session_data['chat_stats']
            rows  = [
                ("Messages Sent", str(stats['messages_sent'])),
                ("Messages Recv", str(stats['messages_received'])),
                ("Key Bits",      str(self.n_key_bits) if self.n_key_bits else "—"),
            ]
            for label, val in rows:
                ll = self.f_small.render(label, True, C_TEXT_DIM)
                vl = self.f_small.render(val,   True, C_TEXT_BRIGHT)
                self.screen.blit(ll, (14, y))
                self.screen.blit(vl, (self.LEFT_W - 14 - vl.get_width(), y))
                y += 18

        # Image send button
        if self.state == 'CHAT':
            btn_y2 = self.H - self.FOOTER_H - 60
            self.btn_send_img.rect.update(14, btn_y2, self.LEFT_W - 28, 38)
            self.btn_send_img.draw(self.screen)

    # ──────────────────────────────────────────────────────────────────────────
    #  RIGHT PANEL
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_right_panel(self):
        rx        = self.LEFT_W + 1
        ry        = self.HEADER_H
        rw        = self.W - rx
        log_start = self.H - self.FOOTER_H - self.LOG_H
        chat_h    = log_start - ry - 30
        chat_rect = pygame.Rect(rx, ry, rw, chat_h)

        cs = pygame.Surface((rw, chat_h), pygame.SRCALPHA)
        cs.fill((10, 12, 22, 200))
        self.screen.blit(cs, (rx, ry))

        total_h = sum(b.height + 8 for b in self.bubbles)
        self.screen.set_clip(chat_rect)
        margin   = 12
        bubble_w = rw - margin * 2 - 20
        y        = ry + chat_h - margin + self.chat_scroll - total_h

        for bubble in self.bubbles:
            if y + bubble.height > ry and y < ry + chat_h:
                bubble.max_width = bubble_w
                bubble._build()
                bubble.draw(self.screen, rx + margin, y)
            y += bubble.height + 8

        self.screen.set_clip(None)

        if self.progress.visible:
            self.progress.rect = pygame.Rect(rx + 12, log_start - 20, rw - 24, 12)
            self.progress.draw(self.screen)

        ls = pygame.Surface((rw, self.LOG_H), pygame.SRCALPHA)
        ls.fill((*C_PANEL, 210))
        self.screen.blit(ls, (rx, log_start))
        pygame.draw.line(self.screen, C_BORDER,
                         (rx, log_start), (self.W, log_start), 1)

        lbl_title = self.f_tiny.render("SYSTEM LOG", True, C_TEXT_DIM)
        self.screen.blit(lbl_title, (rx + 10, log_start + 4))

        visible_lines = self.log_lines[-(self.LOG_H // 14):]
        for i, (txt, col) in enumerate(visible_lines):
            ll = self.f_tiny.render(txt, True, col)
            self.screen.blit(ll, (rx + 10, log_start + 18 + i * 13))

        if self.state == 'CHAT':
            clbl = self.f_sub.render("ENCRYPTED CHANNEL", True, C_TEXT_DIM)
            self.screen.blit(clbl,
                             (rx + rw // 2 - clbl.get_width() // 2, ry + 6))

    # ──────────────────────────────────────────────────────────────────────────
    #  FOOTER
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_footer(self):
        fy = self.H - self.FOOTER_H
        fs = pygame.Surface((self.W, self.FOOTER_H), pygame.SRCALPHA)
        fs.fill((*C_PANEL, 230))
        self.screen.blit(fs, (0, fy))
        pygame.draw.line(self.screen, C_BORDER_LIT, (0, fy), (self.W, fy), 1)

        if self.state != 'CHAT':
            hint = self.f_body.render("Waiting for secure channel...", True, C_TEXT_DIM)
            self.screen.blit(hint, (self.LEFT_W + 20, fy + 20))
            return

        input_rect = pygame.Rect(self.LEFT_W + 12, fy + 10,
                                  self.W - self.LEFT_W - 120, 44)
        border_col = C_BORDER_LIT if self.input_active else C_BORDER
        pygame.draw.rect(self.screen, C_PANEL2,    input_rect, border_radius=10)
        pygame.draw.rect(self.screen, border_col,  input_rect, 1, border_radius=10)

        self.screen.set_clip(input_rect.inflate(-8, -8))
        txt_lbl  = self.f_input.render(self.input_text, True, C_TEXT)
        tx       = input_rect.x + 12
        ty       = input_rect.y + input_rect.h // 2 - txt_lbl.get_height() // 2
        max_tw   = input_rect.w - 24
        if txt_lbl.get_width() > max_tw:
            txt_lbl = txt_lbl.subsurface(
                (txt_lbl.get_width() - max_tw, 0, max_tw, txt_lbl.get_height())
            )
        self.screen.blit(txt_lbl, (tx, ty))

        if self.input_active and self.show_cursor:
            cx2 = tx + min(txt_lbl.get_width(), max_tw)
            pygame.draw.rect(self.screen, C_ACCENT,
                             (cx2, ty + 2, 2, txt_lbl.get_height() - 4))
        self.screen.set_clip(None)

        if not self.input_text:
            ph = self.f_body.render(f"  Message {self.peer_name}...", True, C_TEXT_DIM)
            self.screen.blit(ph, (tx, ty))

        self.btn_send.rect.update(self.W - 108, fy + 12, 90, 44)
        self.btn_send.draw(self.screen)

    # ──────────────────────────────────────────────────────────────────────────
    #  NAME OVERLAY
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_name_overlay(self):
        ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        self.screen.blit(ov, (0, 0))

        cx, cy        = self.W // 2, self.H // 2
        card_w, card_h = 420, 220
        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        pygame.draw.rect(card, (*C_PANEL2, 245),
                         (0, 0, card_w, card_h), border_radius=18)
        pygame.draw.rect(card, (*C_BORDER_LIT, 200),
                         (0, 0, card_w, card_h), 2, border_radius=18)
        self.screen.blit(card, (cx - card_w // 2, cy - card_h // 2))

        t1 = self.f_title.render("⚛  Quantum Chat", True, C_ACCENT)
        self.screen.blit(t1, (cx - t1.get_width() // 2, cy - 90))

        t2 = self.f_small.render(
            "SERVER (Alice)  —  E91 Protocol", True, C_TEXT_DIM)
        self.screen.blit(t2, (cx - t2.get_width() // 2, cy - 60))

        # Name input box
        nl = self.f_tiny.render("YOUR NAME", True, C_ACCENT)
        self.screen.blit(nl, (cx - 170, cy - 32))
        box = pygame.Rect(cx - 170, cy - 18, 340, 44)
        pygame.draw.rect(self.screen, C_PANEL, box, border_radius=10)
        pygame.draw.rect(self.screen, C_BORDER_LIT, box, 2, border_radius=10)

        if self.my_name:
            nl2 = self.f_input.render(self.my_name, True, C_TEXT_BRIGHT)
            self.screen.blit(nl2, (box.x + 14, box.y + 10))
            if self.show_cursor:
                pygame.draw.rect(self.screen, C_ACCENT,
                                 (box.x + 14 + nl2.get_width(), box.y + 10, 2, 24))
        else:
            ph = self.f_input.render("Enter your name...", True, C_TEXT_DIM)
            self.screen.blit(ph, (box.x + 14, box.y + 10))

        self.btn_name_ok.rect.centerx = cx
        self.btn_name_ok.rect.y       = cy + 38
        self.btn_name_ok.draw(self.screen)

    # ──────────────────────────────────────────────────────────────────────────
    #  CLIPBOARD PASTE
    # ──────────────────────────────────────────────────────────────────────────

    def _paste_clipboard(self):
        """Paste clipboard text into the chat input box."""
        try:
            pygame.scrap.init()
            clip = pygame.scrap.get(pygame.SCRAP_TEXT)
            if clip:
                text = clip.decode('utf-8', errors='ignore').rstrip('\x00')
                self.input_text += text
                return
        except Exception:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            self.input_text += text
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    #  FILE PICKER
    # ──────────────────────────────────────────────────────────────────────────

    def _pick_image_file(self):
        """Open a native OS file-picker dialog in a background thread."""
        def _dialog():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            path = filedialog.askopenfilename(
                title     = "Select Image to Send",
                filetypes = [
                    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                    ("PNG",         "*.png"),
                    ("JPEG",        "*.jpg *.jpeg"),
                    ("GIF",         "*.gif"),
                    ("BMP",         "*.bmp"),
                    ("WebP",        "*.webp"),
                    ("All files",   "*.*"),
                ]
            )
            root.destroy()
            if path:
                self._schedule(lambda p=path: self._send_image_path(p))

        threading.Thread(target=_dialog, daemon=True).start()

    def _send_image_path(self, path):
        """Send the image at the given path."""
        if not path or not os.path.exists(path):
            self._add_log("File not found", C_ERROR)
            return
        self._add_log(f"Sending: {os.path.basename(path)}", C_ACCENT2)
        self.progress.set(0)

        def _do():
            success = send_image(
                sock        = self.conn_sock,
                encryptor   = self.encryptor,
                file_path   = path,
                sender_name = self.my_name,
                logger      = self.logger,
                progress_cb = lambda p: self._schedule(
                    lambda pv=p: self.progress.set(pv))
            )
            if success:
                self._schedule(lambda: self._add_bubble(
                    f"📸 Image sent: {os.path.basename(path)}",
                    self.my_name, is_sent=True, bubble_type='image'))
                self._schedule(lambda: self._add_log(
                    f"✅ Image sent: {os.path.basename(path)}", C_SUCCESS))
                self._schedule(lambda: self.progress.hide())
            else:
                self._schedule(lambda: self._add_log("❌ Image send failed", C_ERROR))
                self._schedule(lambda: self.progress.hide())

        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    #  LOGIC HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _confirm_name(self):
        if not self.my_name.strip():
            return
        self.state      = 'WAITING'
        self.status_msg = 'Starting server...'
        self.status_col = C_WARNING
        self.logger     = QuantumLogger(role=self.my_name.lower())
        threading.Thread(target=self._network_thread, daemon=True).start()

    def _schedule(self, fn):
        with self._lock:
            self._pending_calls.append(fn)

    def _add_bubble(self, text, sender, is_sent, bubble_type='text'):
        ts = datetime.datetime.now().strftime("%H:%M")
        b  = ChatBubble(text, sender, is_sent, self.f_body, ts,
                        bubble_type=bubble_type)
        self.bubbles.append(b)
        self.chat_scroll = 0

    def _add_log(self, text, col=None):
        col = col or C_TEXT_DIM
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((f"[{ts}] {text}", col))
        if len(self.log_lines) > self.MAX_LOG:
            self.log_lines.pop(0)

    def _set_status(self, msg, col=None):
        self.status_msg = msg
        self.status_col = col or C_ACCENT

    def _send_chat_message(self):
        msg = self.input_text.strip()
        if not msg or not self.conn_sock or self.state != 'CHAT':
            return
        try:
            enc = self.encryptor.encrypt(msg)
            send_message(self.conn_sock, MSG_CHAT, {'data': list(enc)})
            self.input_text = ''
            self._add_bubble(msg, self.my_name, is_sent=True)
            self._add_log(f"Sent: {msg[:40]}", C_SENT)
            self.logger.log_chat_message('SENT', msg, enc.hex(), len(enc))
        except Exception as e:
            self._add_log(f"Send error: {e}", C_ERROR)

    # ──────────────────────────────────────────────────────────────────────────
    #  NETWORK THREAD
    # ──────────────────────────────────────────────────────────────────────────

    def _network_thread(self):
        try:
            self._schedule(lambda: self._set_status(
                "Listening on :12346", C_WARNING))
            self._schedule(lambda: self._add_log(
                "Server started on :12346", C_ACCENT))

            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(('0.0.0.0', 12346))
            self.server_sock.listen(1)

            conn, addr = self.server_sock.accept()
            self.conn_sock = conn

            self._schedule(lambda: self._set_status(
                f"Peer connected: {addr[0]}", C_SUCCESS))
            self._schedule(lambda: self._add_log(
                f"Peer connected from {addr[0]}", C_SUCCESS))
            self._schedule(lambda: setattr(self.qvis, 'active', True))

            self._schedule(lambda: self._set_status(
                "E91 Key Exchange in progress...", C_WARNING))
            self._schedule(lambda: self._add_log(
                "Starting E91 key exchange", C_QUANTUM))

            enc = self._do_key_exchange(conn)

            if enc is None:
                self._schedule(lambda: self._set_status(
                    "Key exchange FAILED", C_ERROR))
                return

            self.encryptor = enc
            self._schedule(lambda: self._set_status(
                f"🔐 Secure channel with {self.peer_name}", C_SUCCESS))
            self._schedule(lambda: self._add_bubble(
                f"🔐 Quantum-secured channel established with {self.peer_name}  |  "
                f"E91 · S={self.chsh_s:.3f}  |  128-bit key",
                "System", False, bubble_type='system'
            ))
            self._schedule(lambda: setattr(self, 'state', 'CHAT'))
            self._schedule(lambda: setattr(self, 'input_active', True))

            self._receive_loop(conn)

        except Exception as e:
            self._schedule(lambda: self._set_status(f"Error: {e}", C_ERROR))
            self._schedule(lambda: self._add_log(f"Network error: {e}", C_ERROR))

    def _do_key_exchange(self, conn):
        engine    = QuantumEngine()
        num_pairs = 300

        send_message(conn, 'NAME_EXCHANGE', {'name': self.my_name})
        msg = receive_message(conn)
        self.peer_name = msg['payload']['name']
        self._schedule(lambda pn=self.peer_name:
                       self._add_log(f"Peer name: {pn}", C_ACCENT))

        self._schedule(lambda: self._add_log(
            "Choosing random measurement bases...", C_TEXT_DIM))
        alice_bases = [int(np.random.randint(0, 3)) for _ in range(num_pairs)]
        send_message(conn, MSG_BASIS_COMPARE,
                     {'alice_bases': alice_bases, 'num_pairs': num_pairs})

        msg       = receive_message(conn)
        bob_bases = msg['payload']['bob_bases']

        self._schedule(lambda: self._add_log(
            "Simulating entangled Bell pairs...", C_QUANTUM))
        results = engine.generate_all_measurements(num_pairs, alice_bases, bob_bases)

        bob_bits_all = [r['bob_bit'] for r in results]
        send_message(conn, 'MEASUREMENT_RESULTS', {'bob_bits_all': bob_bits_all})

        self.logger.log_key_exchange('raw_measurements', {
            'num_pairs'  : num_pairs,
            'alice_bases': alice_bases,
            'bob_bases'  : bob_bases,
            'alice_bits' : [r['alice_bit'] for r in results],
            'bob_bits'   : bob_bits_all
        })

        self._schedule(lambda: self._add_log(
            "Computing CHSH inequality...", C_QUANTUM))
        chsh = engine.compute_chsh_value(results)

        s_val      = chsh['S_value']
        is_secure  = chsh['is_secure']
        self.chsh_s      = s_val
        self.chsh_secure = is_secure

        self._schedule(lambda sv=s_val, sec=is_secure: self._add_log(
            f"CHSH S = {sv:.4f}  {'✅ SECURE' if sec else '❌ INSECURE'}",
            C_SUCCESS if sec else C_ERROR
        ))
        self.logger.log_chsh_result(chsh)

        send_message(conn, MSG_CHSH_RESULT, {
            'S_value'   : s_val,
            'is_secure' : is_secure,
            'E_a0b0'    : chsh['E_a0b0'],
            'E_a0b1'    : chsh['E_a0b1'],
            'E_a1b0'    : chsh['E_a1b0'],
            'E_a1b1'    : chsh['E_a1b1'],
        })

        if not is_secure:
            self.logger.log_security_event('CHSH_FAIL', f"S={s_val:.4f}", 'CRITICAL')
            send_message(conn, MSG_ABORT, {'reason': 'CHSH failed'})
            return None

        self.logger.log_security_event('CHSH_PASS', f"S={s_val:.4f}", 'INFO')

        key_data       = engine.extract_key_bits(results)
        alice_key_bits = key_data['alice_bits']
        n_key          = key_data['key_length']
        self.n_key_bits = n_key

        self._schedule(lambda n=n_key: self._add_log(
            f"Key bits extracted: {n}", C_ACCENT3))

        if n_key < 8:
            send_message(conn, MSG_ABORT, {'reason': f'Only {n_key} key bits'})
            return None

        self.logger.log_measurements(
            results, key_data['used_indices'], key_data['chsh_indices'])
        self.logger.log_key_exchange('key_sifting', {
            'key_bits': n_key, 'alice_key_bits': alice_key_bits
        })

        kg        = KeyGenerator()
        final_key = kg.privacy_amplification(alice_key_bits, target_bytes=16)
        self.key_hex = final_key.hex()
        self._schedule(lambda k=self.key_hex: self._add_log(
            f"Key: {k[:16]}...", C_ACCENT3))

        self.logger.log_key_exchange('final_key', {
            'key_hex'    : final_key.hex(),
            'key_bits'   : 128,
            'source_bits': n_key
        })

        send_message(conn, MSG_ERROR_RATE, {
            'alice_key_bits': alice_key_bits,
            'n_key_bits'    : n_key,
            'chsh_s_value'  : s_val,
            'status'        : 'secure'
        })

        our_hash = hash_key(final_key)
        send_message(conn, MSG_KEY_HASH, {'key_hash': our_hash})
        msg      = receive_message(conn)
        bob_hash = msg['payload']['key_hash']

        if our_hash != bob_hash:
            self.logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
            self._schedule(lambda: self._add_log("❌ Key mismatch!", C_ERROR))
            send_message(conn, MSG_ABORT, {'reason': 'Key mismatch'})
            return None

        self.logger.log_security_event('KEY_MATCH', 'Keys match', 'INFO')
        self._schedule(lambda: self._add_log(
            "✅ Keys verified — channel secured", C_SUCCESS))

        send_message(conn, MSG_READY, {'status': 'ready'})
        receive_message(conn)

        return QuantumEncryptor(final_key)

    def _receive_loop(self, conn):
        while True:
            try:
                msg = receive_message(conn)

                if msg['type'] == MSG_CHAT:
                    enc_data  = bytes(msg['payload']['data'])
                    plaintext = self.encryptor.decrypt(enc_data)
                    pn        = self.peer_name
                    self._schedule(lambda t=plaintext, s=pn:
                                   self._add_bubble(t, s, is_sent=False))
                    self._schedule(lambda t=plaintext:
                                   self._add_log(f"Recv: {t[:40]}", C_ACCENT2))
                    self.logger.log_chat_message(
                        'RECEIVED', plaintext, enc_data.hex(), len(enc_data))

                elif msg['type'] == MSG_IMAGE_HEADER:
                    header = msg['payload']
                    fname  = header.get('file_name', 'image')
                    sender = header.get('sender', self.peer_name)
                    self._schedule(lambda f=fname, s=sender: self._add_log(
                        f"📥 Receiving image {f} from {s}", C_ACCENT2))
                    self._schedule(lambda: self.progress.set(0))

                    saved_path = receive_image(
                        sock      = conn,
                        encryptor = self.encryptor,
                        header    = header,
                        my_name   = self.my_name,
                        logger    = self.logger
                    )

                    if saved_path:
                        bn = os.path.basename(saved_path)
                        self._schedule(lambda b=bn: self._add_bubble(
                            f"📥 Image received: {b}",
                            self.peer_name, False, 'image'))
                        self._schedule(lambda b=bn: self._add_log(
                            f"Image saved: {b}", C_SUCCESS))
                        self._schedule(lambda: self.progress.hide())
                    else:
                        self._schedule(lambda: self._add_log(
                            "Image receive failed", C_ERROR))
                        self._schedule(lambda: self.progress.hide())

                elif msg['type'] == MSG_ABORT:
                    pn = self.peer_name
                    self._schedule(lambda n=pn: self._add_bubble(
                        f"[{n} has disconnected]", "System", False, 'system'))
                    self._schedule(lambda: self._set_status(
                        "Peer disconnected", C_ERROR))
                    if self.logger:
                        self.logger.save_session_summary()
                    break

            except Exception as e:
                self._schedule(lambda: self._set_status("Connection lost", C_ERROR))
                self._schedule(lambda: self._add_log(
                    f"Connection lost: {e}", C_ERROR))
                if self.logger:
                    self.logger.save_session_summary()
                break


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app = QuantumChatApp(role='server')
    app.run()