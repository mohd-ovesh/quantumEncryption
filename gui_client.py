# gui_client.py  —  PyGame GUI for Bob (Client)

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

from e91.quantum_engine   import QuantumEngine
from e91.key_generator    import KeyGenerator
from e91.encryptor        import QuantumEncryptor
from utils.logger         import QuantumLogger
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
        pygame.draw.circle(surf,
                           (int(r * alpha), int(g * alpha), int(b * alpha)),
                           (int(self.x), int(self.y)), max(1, int(self.r)))


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
        self.press_anim = max(0, self.press_anim - dt * 4)

    def draw(self, surf):
        if self.hover or self.press_anim > 0:
            glow = pygame.Surface(
                (self.rect.w + 20, self.rect.h + 20), pygame.SRCALPHA)
            t = max(self.hover * 0.4, self.press_anim)
            r, g, b = self.color
            pygame.draw.rect(glow, (r, g, b, int(60 * t)),
                             (0, 0, self.rect.w + 20, self.rect.h + 20),
                             border_radius=self.border_radius + 4)
            surf.blit(glow, (self.rect.x - 10, self.rect.y - 10))

        col = tuple(min(255, c + (30 if self.hover else 0) +
                        (60 if self.press_anim > 0 else 0)) for c in self.color)
        pygame.draw.rect(surf, col, self.rect, border_radius=self.border_radius)
        pygame.draw.rect(surf, C_BORDER_LIT if self.hover else C_BORDER,
                         self.rect, 1, border_radius=self.border_radius)
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
        self.height      = 22 + max(1, len(self._wrap_cache)) * line_h + 20

    def _wrap_text(self, text, max_w):
        words, lines, cur = text.split(' '), [], ''
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

        s = pygame.Surface((self.max_width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(s, (*bg, int(220 * alpha)),
                         (0, 0, self.max_width, self.height), border_radius=14)
        pygame.draw.rect(s, (*bord, int(180 * alpha)),
                         (0, 0, self.max_width, self.height), 1, border_radius=14)

        if self.bubble_type == 'system':
            lbl = self.font.render(f"  ⚛  {self.sender}", True,
                                    (*C_ACCENT3, int(255 * alpha)))
        elif self.is_sent:
            lbl = self.font.render(f"  You  ·  {self.timestamp}", True,
                                    (*C_SENT, int(200 * alpha)))
        else:
            lbl = self.font.render(f"  {self.sender}  ·  {self.timestamp}", True,
                                    (*C_ACCENT2, int(200 * alpha)))
        s.blit(lbl, (10, 6))

        line_h = self.font.get_height() + 3
        for i, line in enumerate(self._wrap_cache):
            s.blit(self.font.render(line, True, (*C_TEXT, int(255 * alpha))),
                   (16, 26 + i * line_h))
        surf.blit(s, (x, y))
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
        self.value   = self.target = 0.0

    def update(self, dt):
        self._anim += dt * 2
        self.value  = min(self.target, self.value + dt * 1.5)

    def draw(self, surf):
        if not self.visible:
            return
        pygame.draw.rect(surf, C_PANEL2, self.rect, border_radius=6)
        pygame.draw.rect(surf, C_BORDER,  self.rect, 1, border_radius=6)
        fw = int(self.rect.w * self.value)
        if fw > 0:
            pygame.draw.rect(surf, self.color,
                             (self.rect.x, self.rect.y, fw, self.rect.h),
                             border_radius=6)
            sx = self.rect.x + int((math.sin(self._anim) * 0.5 + 0.5) * fw)
            for i in range(3):
                sxi = sx - i * 8
                if self.rect.x < sxi < self.rect.x + fw:
                    pygame.draw.rect(surf, (255, 255, 255),
                                     (sxi, self.rect.y, 3, self.rect.h),
                                     border_radius=2)


# ══════════════════════════════════════════════════════════════════════════════
#  QUANTUM VISUALISER
# ══════════════════════════════════════════════════════════════════════════════

class QuantumVisualiser:
    def __init__(self, cx, cy, radius=60):
        self.cx, self.cy = cx, cy
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
        pulse = math.sin(self.phase) * 0.5 + 0.5
        gs2   = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(gs2, (*C_QUANTUM, int(100 * pulse)),
                           (14, 14), int(8 + 4 * pulse))
        surf.blit(gs2, (cx - 14, cy - 14))
        pygame.draw.circle(surf, C_QUANTUM, (cx, cy), 4)


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENT APP
# ══════════════════════════════════════════════════════════════════════════════

class QuantumChatClientApp:
    W, H               = 1280, 780
    HEADER_H           = 70
    FOOTER_H           = 68
    LEFT_W             = 310
    LOG_H              = 110
    DEFAULT_SERVER_IP  = '192.168.29.162'

    def __init__(self):
        self.role       = 'client'
        self.my_name    = ''
        self.peer_name  = ''
        self.server_ip  = self.DEFAULT_SERVER_IP
        self.running    = True

        self.state      = 'NAME_INPUT'
        self.status_msg = 'Enter your name to begin'
        self.status_col = C_ACCENT

        self.encryptor  = None
        self.logger     = None
        self.sock       = None

        self.bubbles     = []
        self.chat_scroll = 0
        self.log_lines   = []
        self.MAX_LOG     = 18

        self.input_text   = ''
        self.input_active = False
        self.cursor_blink = 0.0
        self.show_cursor  = True

        # 0 = name field focused, 1 = ip field focused
        self.name_field_focus = 0

        self.progress    = None
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
        pygame.display.set_caption("⚛  Quantum Encrypted Chat  —  CLIENT")

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
        self.btn_connect = Button(
            rect          = (self.W // 2 - 80, self.H // 2 + 82, 160, 44),
            text          = 'Connect',
            color         = C_ACCENT,
            font          = self.f_sub,
            text_color    = C_TEXT_BRIGHT,
            border_radius = 10
        )

        self._main_loop()

    # ──────────────────────────────────────────────────────────────────────────
    #  MAIN LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def _main_loop(self):
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
                    if event.key == pygame.K_TAB:
                        self.name_field_focus = 1 - self.name_field_focus
                    elif event.key == pygame.K_RETURN:
                        self._confirm_connect()
                    elif event.key == pygame.K_BACKSPACE:
                        if self.name_field_focus == 0:
                            self.my_name = self.my_name[:-1]
                        else:
                            self.server_ip = self.server_ip[:-1]
                    elif event.key == pygame.K_v and (
                        pygame.key.get_mods() & pygame.KMOD_META or
                        pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        # Paste into whichever field is focused
                        pasted = self._get_clipboard()
                        if pasted:
                            if self.name_field_focus == 0:
                                self.my_name += pasted
                            else:
                                self.server_ip += pasted
                    else:
                        ch = event.unicode
                        if ch.isprintable():
                            if self.name_field_focus == 0 and len(self.my_name) < 24:
                                self.my_name += ch
                            elif self.name_field_focus == 1 and len(self.server_ip) < 40:
                                self.server_ip += ch

                if self.btn_connect.handle_event(event):
                    self._confirm_connect()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    cx = self.W // 2
                    cy = self.H // 2
                    name_box = pygame.Rect(cx - 170, cy - 46, 340, 42)
                    ip_box   = pygame.Rect(cx - 170, cy + 10, 340, 42)
                    if name_box.collidepoint(event.pos):
                        self.name_field_focus = 0
                    elif ip_box.collidepoint(event.pos):
                        self.name_field_focus = 1

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
                        pasted = self._get_clipboard()
                        if pasted:
                            self.input_text += pasted
                    else:
                        if len(self.input_text) < 400 and event.unicode.isprintable():
                            self.input_text += event.unicode

                if self.btn_send.handle_event(event):
                    self._send_chat_message()

                if self.btn_send_img.handle_event(event):
                    self._pick_image_file()

            self.btn_send.handle_event(event)
            self.btn_connect.handle_event(event)
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
        self.btn_connect.update(dt)
        self.cursor_blink += dt
        if self.cursor_blink > 0.53:
            self.cursor_blink = 0
            self.show_cursor  = not self.show_cursor
        for b in self.bubbles:
            if b.alpha < 1.0:
                b.alpha = min(1.0, b.alpha + dt * 4)

    # ──────────────────────────────────────────────────────────────────────────
    #  DRAW
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

    # ── Header ────────────────────────────────────────────────────

    def _draw_header(self):
        hdr = pygame.Surface((self.W, self.HEADER_H), pygame.SRCALPHA)
        hdr.fill((*C_PANEL, 220))
        self.screen.blit(hdr, (0, 0))
        pygame.draw.line(self.screen, C_BORDER_LIT,
                         (0, self.HEADER_H), (self.W, self.HEADER_H), 1)

        pygame.draw.circle(self.screen, C_QUANTUM, (36, self.HEADER_H // 2), 14, 2)
        pygame.draw.circle(self.screen, C_ACCENT2,  (36, self.HEADER_H // 2),  5)

        title = self.f_title.render("⚛  Quantum Chat", True, C_TEXT_BRIGHT)
        self.screen.blit(title, (56, self.HEADER_H // 2 - title.get_height() // 2))

        role_lbl = self.f_small.render("  CLIENT  ", True, C_BG)
        role_bg  = pygame.Rect(220, 18, role_lbl.get_width() + 10, 26)
        pygame.draw.rect(self.screen, C_ACCENT2, role_bg, border_radius=5)
        self.screen.blit(role_lbl, (role_bg.x + 5, role_bg.y + 5))

        st_lbl = self.f_body.render(self.status_msg, True, self.status_col)
        sx     = self.W - st_lbl.get_width() - 24
        sy     = self.HEADER_H // 2 - st_lbl.get_height() // 2
        pill   = pygame.Rect(sx - 10, sy - 4,
                              st_lbl.get_width() + 20, st_lbl.get_height() + 8)
        ps     = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        pygame.draw.rect(ps, (*self.status_col, 30),
                         (0, 0, pill.w, pill.h), border_radius=12)
        pygame.draw.rect(ps, (*self.status_col, 80),
                         (0, 0, pill.w, pill.h), 1, border_radius=12)
        self.screen.blit(ps, (pill.x, pill.y))
        self.screen.blit(st_lbl, (sx, sy))

        if self.peer_name:
            pn = self.f_small.render(f"⬡  {self.peer_name}", True, C_TEXT_DIM)
            self.screen.blit(pn, (self.W // 2 - pn.get_width() // 2,
                                   self.HEADER_H // 2 - pn.get_height() // 2))

        if self.server_ip and self.state != 'NAME_INPUT':
            ip_lbl = self.f_tiny.render(
                f"⇢ {self.server_ip}:12346", True, C_TEXT_DIM)
            self.screen.blit(ip_lbl,
                             (320, self.HEADER_H // 2 - ip_lbl.get_height() // 2))

    # ── Left panel ────────────────────────────────────────────────

    def _draw_left_panel(self):
        panel_rect = pygame.Rect(0, self.HEADER_H, self.LEFT_W,
                                  self.H - self.HEADER_H)
        ps = pygame.Surface((panel_rect.w, panel_rect.h), pygame.SRCALPHA)
        ps.fill((*C_PANEL, 200))
        self.screen.blit(ps, panel_rect.topleft)
        pygame.draw.line(self.screen, C_BORDER,
                         (self.LEFT_W, self.HEADER_H), (self.LEFT_W, self.H), 1)

        y = self.HEADER_H + 12
        sec = self.f_sub.render("QUANTUM CHANNEL", True, C_ACCENT2)
        self.screen.blit(sec, (14, y)); y += 22
        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8

        self.qvis.cx = self.LEFT_W // 2
        self.qvis.cy = y + 68
        self.qvis.draw(self.screen)
        y += 140

        if self.chsh_s > 0:
            s_col = C_SUCCESS if self.chsh_secure else C_ERROR
            sv    = self.f_sub.render(f"S = {self.chsh_s:.4f}", True, s_col)
            self.screen.blit(sv,
                             (self.LEFT_W // 2 - sv.get_width() // 2, y)); y += 22
            bound = self.f_small.render(
                "Classical ≤ 2.0  |  Quantum ≤ 2√2", True, C_TEXT_DIM)
            self.screen.blit(bound,
                             (self.LEFT_W // 2 - bound.get_width() // 2, y)); y += 22
            verd = self.f_body.render(
                "✅ SECURE" if self.chsh_secure else "❌ INSECURE",
                True, s_col)
            self.screen.blit(verd,
                             (self.LEFT_W // 2 - verd.get_width() // 2, y)); y += 30
        else:
            ph = self.f_small.render("CHSH test pending...", True, C_TEXT_DIM)
            self.screen.blit(ph,
                             (self.LEFT_W // 2 - ph.get_width() // 2, y)); y += 30

        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8
        kl = self.f_sub.render("SESSION KEY", True, C_ACCENT2)
        self.screen.blit(kl, (14, y)); y += 20

        if self.key_hex:
            blocks = [self.key_hex[i:i + 8] for i in range(0, len(self.key_hex), 8)]
            for bi, blk in enumerate(blocks[:4]):
                blbl = self.f_mono.render(blk, True, C_ACCENT3)
                self.screen.blit(blbl, (14 + bi * 72, y))
            y += 20
            self.screen.blit(
                self.f_small.render("128-bit stream key", True, C_TEXT_DIM),
                (14, y)); y += 20
        else:
            self.screen.blit(
                self.f_small.render("No key yet", True, C_TEXT_DIM),
                (14, y)); y += 20

        y += 10
        pygame.draw.line(self.screen, C_BORDER,
                         (14, y), (self.LEFT_W - 14, y)); y += 8
        self.screen.blit(
            self.f_sub.render("SESSION STATS", True, C_ACCENT2), (14, y)); y += 20

        if self.logger:
            stats = self.logger.session_data['chat_stats']
            for label, val in [
                ("Messages Sent", str(stats['messages_sent'])),
                ("Messages Recv", str(stats['messages_received'])),
                ("Key Bits",      str(self.n_key_bits) if self.n_key_bits else "—"),
            ]:
                ll = self.f_small.render(label, True, C_TEXT_DIM)
                vl = self.f_small.render(val,   True, C_TEXT_BRIGHT)
                self.screen.blit(ll, (14, y))
                self.screen.blit(vl, (self.LEFT_W - 14 - vl.get_width(), y))
                y += 18

        if self.state == 'CHAT':
            btn_y2 = self.H - self.FOOTER_H - 60
            self.btn_send_img.rect.update(14, btn_y2, self.LEFT_W - 28, 38)
            self.btn_send_img.draw(self.screen)

    # ── Right panel ───────────────────────────────────────────────

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
        self.screen.blit(
            self.f_tiny.render("SYSTEM LOG", True, C_TEXT_DIM),
            (rx + 10, log_start + 4))

        visible = self.log_lines[-(self.LOG_H // 14):]
        for i, (txt, col) in enumerate(visible):
            self.screen.blit(self.f_tiny.render(txt, True, col),
                             (rx + 10, log_start + 18 + i * 13))

        if self.state == 'CHAT':
            clbl = self.f_sub.render("ENCRYPTED CHANNEL", True, C_TEXT_DIM)
            self.screen.blit(clbl,
                             (rx + rw // 2 - clbl.get_width() // 2, ry + 6))

    # ── Footer ────────────────────────────────────────────────────

    def _draw_footer(self):
        fy = self.H - self.FOOTER_H
        fs = pygame.Surface((self.W, self.FOOTER_H), pygame.SRCALPHA)
        fs.fill((*C_PANEL, 230))
        self.screen.blit(fs, (0, fy))
        pygame.draw.line(self.screen, C_BORDER_LIT, (0, fy), (self.W, fy), 1)

        if self.state != 'CHAT':
            hint = self.f_body.render(
                "Waiting for secure channel...", True, C_TEXT_DIM)
            self.screen.blit(hint, (self.LEFT_W + 20, fy + 20))
            return

        input_rect = pygame.Rect(self.LEFT_W + 12, fy + 10,
                                  self.W - self.LEFT_W - 120, 44)
        pygame.draw.rect(self.screen, C_PANEL2, input_rect, border_radius=10)
        pygame.draw.rect(self.screen,
                         C_BORDER_LIT if self.input_active else C_BORDER,
                         input_rect, 1, border_radius=10)

        self.screen.set_clip(input_rect.inflate(-8, -8))
        txt_lbl = self.f_input.render(self.input_text, True, C_TEXT)
        tx      = input_rect.x + 12
        ty      = input_rect.y + input_rect.h // 2 - txt_lbl.get_height() // 2
        max_tw  = input_rect.w - 24
        if txt_lbl.get_width() > max_tw:
            txt_lbl = txt_lbl.subsurface(
                (txt_lbl.get_width() - max_tw, 0, max_tw, txt_lbl.get_height()))
        self.screen.blit(txt_lbl, (tx, ty))
        if self.input_active and self.show_cursor:
            pygame.draw.rect(self.screen, C_ACCENT2,
                             (tx + min(txt_lbl.get_width(), max_tw),
                              ty + 2, 2, txt_lbl.get_height() - 4))
        self.screen.set_clip(None)

        if not self.input_text:
            self.screen.blit(
                self.f_body.render(
                    f"  Message {self.peer_name}...", True, C_TEXT_DIM),
                (tx, ty))

        self.btn_send.rect.update(self.W - 108, fy + 12, 90, 44)
        self.btn_send.draw(self.screen)

    # ── Name overlay ──────────────────────────────────────────────

    def _draw_name_overlay(self):
        ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        self.screen.blit(ov, (0, 0))

        cx, cy        = self.W // 2, self.H // 2
        card_w, card_h = 440, 280
        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        pygame.draw.rect(card, (*C_PANEL2, 245),
                         (0, 0, card_w, card_h), border_radius=18)
        pygame.draw.rect(card, (*C_BORDER_LIT, 200),
                         (0, 0, card_w, card_h), 2, border_radius=18)
        self.screen.blit(card, (cx - card_w // 2, cy - card_h // 2))

        t1 = self.f_title.render("⚛  Quantum Chat", True, C_ACCENT2)
        self.screen.blit(t1, (cx - t1.get_width() // 2, cy - 125))

        t2 = self.f_small.render(
            "CLIENT (Bob)  —  E91 Protocol", True, C_TEXT_DIM)
        self.screen.blit(t2, (cx - t2.get_width() // 2, cy - 98))

        # Name field
        nl = self.f_tiny.render("YOUR NAME", True, C_ACCENT2)
        self.screen.blit(nl, (cx - 170, cy - 74))
        name_box = pygame.Rect(cx - 170, cy - 58, 340, 42)
        focused0  = self.name_field_focus == 0
        pygame.draw.rect(self.screen, C_PANEL, name_box, border_radius=10)
        pygame.draw.rect(self.screen,
                         C_BORDER_LIT if focused0 else C_BORDER,
                         name_box, 2, border_radius=10)
        if self.my_name:
            nl2 = self.f_input.render(self.my_name, True, C_TEXT_BRIGHT)
            self.screen.blit(nl2, (name_box.x + 12, name_box.y + 10))
            if focused0 and self.show_cursor:
                pygame.draw.rect(self.screen, C_ACCENT2,
                                 (name_box.x + 12 + nl2.get_width(),
                                  name_box.y + 10, 2, 22))
        else:
            self.screen.blit(
                self.f_input.render("Enter your name...", True, C_TEXT_DIM),
                (name_box.x + 12, name_box.y + 10))

        # IP field
        il = self.f_tiny.render("SERVER IP ADDRESS", True, C_ACCENT2)
        self.screen.blit(il, (cx - 170, cy - 4))
        ip_box   = pygame.Rect(cx - 170, cy + 12, 340, 42)
        focused1  = self.name_field_focus == 1
        pygame.draw.rect(self.screen, C_PANEL, ip_box, border_radius=10)
        pygame.draw.rect(self.screen,
                         C_BORDER_LIT if focused1 else C_BORDER,
                         ip_box, 2, border_radius=10)
        ip_disp = self.server_ip or self.DEFAULT_SERVER_IP
        ip_col  = C_TEXT_BRIGHT if self.server_ip else C_TEXT_DIM
        ip_lbl  = self.f_input.render(ip_disp, True, ip_col)
        self.screen.blit(ip_lbl, (ip_box.x + 12, ip_box.y + 10))
        if focused1 and self.show_cursor:
            pygame.draw.rect(self.screen, C_ACCENT2,
                             (ip_box.x + 12 + ip_lbl.get_width(),
                              ip_box.y + 10, 2, 22))

        hint = self.f_tiny.render(
            "Tab to switch fields  ·  Cmd/Ctrl+V to paste", True, C_TEXT_DIM)
        self.screen.blit(hint, (cx - hint.get_width() // 2, cy + 60))

        self.btn_connect.rect.centerx = cx
        self.btn_connect.rect.y       = cy + 80
        self.btn_connect.draw(self.screen)

    # ──────────────────────────────────────────────────────────────────────────
    #  CLIPBOARD
    # ──────────────────────────────────────────────────────────────────────────

    def _get_clipboard(self) -> str:
        """Return clipboard text, trying pygame.scrap then tkinter fallback."""
        try:
            pygame.scrap.init()
            clip = pygame.scrap.get(pygame.SCRAP_TEXT)
            if clip:
                return clip.decode('utf-8', errors='ignore').rstrip('\x00')
        except Exception:
            pass
        try:
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return text
        except Exception:
            return ''

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
                sock        = self.sock,
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
                self._schedule(lambda: self._add_log(
                    "❌ Image send failed", C_ERROR))
                self._schedule(lambda: self.progress.hide())

        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    #  LOGIC HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _confirm_connect(self):
        if not self.my_name.strip():
            return
        if not self.server_ip.strip():
            self.server_ip = self.DEFAULT_SERVER_IP
        self.state      = 'WAITING'
        self.status_msg = f'Connecting to {self.server_ip}...'
        self.status_col = C_WARNING
        self.logger     = QuantumLogger(role=self.my_name.lower())
        threading.Thread(target=self._network_thread, daemon=True).start()

    def _schedule(self, fn):
        with self._lock:
            self._pending_calls.append(fn)

    def _add_bubble(self, text, sender, is_sent, bubble_type='text'):
        ts = datetime.datetime.now().strftime("%H:%M")
        self.bubbles.append(ChatBubble(text, sender, is_sent, self.f_body,
                                        ts, bubble_type=bubble_type))
        self.chat_scroll = 0

    def _add_log(self, text, col=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((f"[{ts}] {text}", col or C_TEXT_DIM))
        if len(self.log_lines) > self.MAX_LOG:
            self.log_lines.pop(0)

    def _set_status(self, msg, col=None):
        self.status_msg = msg
        self.status_col = col or C_ACCENT

    def _send_chat_message(self):
        msg = self.input_text.strip()
        if not msg or not self.sock or self.state != 'CHAT':
            return
        try:
            enc = self.encryptor.encrypt(msg)
            send_message(self.sock, MSG_CHAT, {'data': list(enc)})
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
            self._schedule(lambda: self._add_log(
                f"Connecting to {self.server_ip}:12346...", C_ACCENT))

            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, 12346))

            self._schedule(lambda: self._set_status(
                "Connected — starting key exchange", C_SUCCESS))
            self._schedule(lambda: self._add_log("Connected ✅", C_SUCCESS))
            self._schedule(lambda: setattr(self.qvis, 'active', True))

            enc = self._do_key_exchange(self.sock)
            if enc is None:
                self._schedule(lambda: self._set_status(
                    "Key exchange FAILED", C_ERROR))
                return

            self.encryptor = enc
            self._schedule(lambda: self._set_status(
                f"🔐 Secure channel with {self.peer_name}", C_SUCCESS))
            self._schedule(lambda: self._add_bubble(
                f"🔐 Quantum-secured channel with {self.peer_name}  |  "
                f"E91 · S={self.chsh_s:.3f}  |  128-bit key",
                "System", False, bubble_type='system'
            ))
            self._schedule(lambda: setattr(self, 'state', 'CHAT'))
            self._schedule(lambda: setattr(self, 'input_active', True))

            self._receive_loop(self.sock)

        except Exception as e:
            self._schedule(lambda: self._set_status(f"Error: {e}", C_ERROR))
            self._schedule(lambda: self._add_log(f"Network error: {e}", C_ERROR))

    def _do_key_exchange(self, sock):
        engine = QuantumEngine()

        msg = receive_message(sock)
        self.peer_name = msg['payload']['name']
        send_message(sock, 'NAME_EXCHANGE', {'name': self.my_name})
        self._schedule(lambda pn=self.peer_name:
                       self._add_log(f"Peer name: {pn}", C_ACCENT))

        self._schedule(lambda: self._add_log(
            "Receiving Alice's bases...", C_TEXT_DIM))
        msg         = receive_message(sock)
        alice_bases = msg['payload']['alice_bases']
        num_pairs   = msg['payload']['num_pairs']

        bob_bases = [int(np.random.randint(0, 3)) for _ in range(num_pairs)]
        send_message(sock, MSG_BASIS_COMPARE, {'bob_bases': bob_bases})
        self.logger.log_key_exchange('basis_choices', {
            'alice_bases': alice_bases,
            'bob_bases'  : bob_bases,
            'num_pairs'  : num_pairs
        })

        self._schedule(lambda: self._add_log(
            "Receiving qubit results...", C_TEXT_DIM))
        msg          = receive_message(sock)
        bob_bits_all = msg['payload']['bob_bits_all']

        self._schedule(lambda: self._add_log(
            "Receiving CHSH result...", C_QUANTUM))
        msg       = receive_message(sock)
        chsh      = msg['payload']
        s_val     = chsh['S_value']
        is_secure = chsh['is_secure']
        self.chsh_s      = s_val
        self.chsh_secure = is_secure

        self._schedule(lambda sv=s_val, sec=is_secure: self._add_log(
            f"CHSH S = {sv:.4f}  {'✅ SECURE' if sec else '❌ INSECURE'}",
            C_SUCCESS if sec else C_ERROR
        ))

        self.logger.log_chsh_result({
            'S_value'      : s_val,
            'is_secure'    : is_secure,
            'E_00'         : chsh.get('E_a0b0', 0),
            'E_02'         : chsh.get('E_a0b1', 0),
            'E_20'         : chsh.get('E_a1b0', 0),
            'E_22'         : chsh.get('E_a1b1', 0),
            'quantum_bound': 2 * np.sqrt(2)
        })

        if not is_secure:
            try:
                receive_message(sock)
            except Exception:
                pass
            return None

        combined = []
        for i in range(num_pairs):
            combined.append({
                'alice_angle_idx': alice_bases[i],
                'bob_angle_idx':   bob_bases[i],
                'alice_bit':       0,
                'bob_bit':         bob_bits_all[i],
                'alice_angle_deg': round(
                    np.degrees(engine.alice_angles[alice_bases[i]]), 2),
                'bob_angle_deg': round(
                    np.degrees(engine.bob_angles[bob_bases[i]]), 2)
            })
        key_data = engine.extract_key_bits(combined)
        self.logger.log_measurements(
            combined, key_data['used_indices'], key_data['chsh_indices'])

        self._schedule(lambda: self._add_log(
            "Receiving key material...", C_TEXT_DIM))
        msg            = receive_message(sock)
        payload        = msg['payload']
        alice_key_bits = payload['alice_key_bits']
        n_key          = payload['n_key_bits']
        self.n_key_bits = n_key

        if len(alice_key_bits) < 8:
            return None

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

        msg           = receive_message(sock)
        peer_key_hash = msg['payload']['key_hash']
        our_hash      = hash_key(final_key)
        send_message(sock, MSG_KEY_HASH, {'key_hash': our_hash})

        if our_hash != peer_key_hash:
            self.logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
            self._schedule(lambda: self._add_log("❌ Key mismatch!", C_ERROR))
            return None

        self.logger.log_security_event('KEY_MATCH', 'Keys match', 'INFO')
        self._schedule(lambda: self._add_log(
            "✅ Keys verified — channel secured", C_SUCCESS))

        receive_message(sock)
        send_message(sock, MSG_READY, {'status': 'ready'})

        return QuantumEncryptor(final_key)

    def _receive_loop(self, sock):
        while True:
            try:
                msg = receive_message(sock)

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
                    self._schedule(lambda f=fname: self._add_log(
                        f"📥 Receiving image: {f}", C_ACCENT2))
                    self._schedule(lambda: self.progress.set(0))

                    saved_path = receive_image(
                        sock      = sock,
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
    app = QuantumChatClientApp()
    app.run()