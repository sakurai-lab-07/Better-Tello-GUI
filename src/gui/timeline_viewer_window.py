"""
Horizontal timeline viewer — simplified, consistent implementation.

Features:
 - Left column: drone names; Right: time axis left->right
 - COMMAND/WAIT drawn as rectangles, `text` from parser shown
 - Zoom in/out, scrollbars, and drag-to-pan
 - Click event shows a small tooltip with details
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Dict
import re
import os
import wave
import audioop
import math as _math

from config import (
    COLOR_BACKGROUND,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_HIGHLIGHT,
    FONT_NORMAL,
    FONT_HEADER,
)


def _font_family_and_size(font_val):
    try:
        return font_val[0], int(font_val[1])
    except Exception:
        return ("TkDefaultFont", 10)


class TimelineViewerWindow:
    def __init__(
        self,
        parent,
        music_list: List[str],
        schedule: List[Dict],
        total_time: float,
        interval_seconds: float = 0.0,
    ):
        self.parent = parent
        self.music_list = music_list or []
        self.schedule = schedule or []
        self.total_time = float(total_time or 0.0)

        # layout
        self.left_width = 160
        self.track_height = 64
        # music waveform track height (optional)
        self.music_track_height = 96
        self.header_h = 48
        self.padding = 12
        self.px_per_s = 60

        # fonts
        self.FONT_FAMILY, self.FONT_SIZE = _font_family_and_size(FONT_NORMAL)

        self._gather_tracks()

        # window
        self.window = tk.Toplevel(parent)
        self.window.title("タイムライン")
        self.window.geometry("1200x700")
        self.window.minsize(800, 480)
        self.window.configure(bg=COLOR_BACKGROUND)
        self.window.transient(parent)

        self._create_widgets()
        self._draw()

    def _gather_tracks(self):
        self.tracks = {}
        for e in self.schedule:
            t = e.get("target", "Unknown")
            if t == "ALL":
                continue
            if e.get("type") == "TAKEOFF":
                continue
            self.tracks.setdefault(t, []).append(e)
        self.track_names = sorted(self.tracks.keys())

    def _create_widgets(self):
        frame = ttk.Frame(self.window, padding=8)
        frame.pack(fill="both", expand=True)

        hdr = ttk.Frame(frame)
        hdr.pack(fill="x")
        ttk.Label(
            hdr, text="📊 タイムライン", font=FONT_HEADER, foreground=COLOR_ACCENT
        ).pack(side="left")
        ttk.Label(
            hdr,
            text=f" 総時間: {self.total_time:.2f}s",
            font=FONT_NORMAL,
            foreground="#666",
        ).pack(side="left", padx=(8, 0))
        ctrl = ttk.Frame(hdr)
        ctrl.pack(side="right")
        ttk.Button(ctrl, text="－", width=3, command=self._zoom_out).pack(side="left")
        self.zoom_label = ttk.Label(ctrl, text=f"{int(self.px_per_s/60*100)}%")
        self.zoom_label.pack(side="left", padx=6)
        ttk.Button(ctrl, text="＋", width=3, command=self._zoom_in).pack(side="left")

        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        self.h_scroll.pack(side="bottom", fill="x")
        self.v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.v_scroll.pack(side="right", fill="y")

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#fff",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
            highlightthickness=0,
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.h_scroll.config(command=self.canvas.xview)
        self.v_scroll.config(command=self.canvas.yview)

        # input state for drag
        self._drag = {"x": 0, "y": 0, "moved": False}

        # bindings
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._on_button_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_release)

        self._tip = None

    def _zoom_in(self):
        self.px_per_s = int(min(300, self.px_per_s * 1.25))
        self.zoom_label.config(text=f"{int(self.px_per_s/60*100)}%")
        self._draw()

    def _zoom_out(self):
        self.px_per_s = int(max(10, self.px_per_s / 1.25))
        self.zoom_label.config(text=f"{int(self.px_per_s/60*100)}%")
        self._draw()

    def _on_mousewheel(self, ev):
        # vertical scroll
        if ev.state & 0x0001:  # Shift pressed -> horizontal
            self.canvas.xview_scroll(int(-1 * (ev.delta / 120)), "units")
        else:
            self.canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")

    def _on_button_press(self, ev):
        self._drag["x"] = ev.x
        self._drag["y"] = ev.y
        self._drag["moved"] = False

    def _on_drag(self, ev):
        dx = ev.x - self._drag["x"]
        dy = ev.y - self._drag["y"]
        if abs(dx) + abs(dy) < 3:
            return
        self._drag["moved"] = True
        # compute fraction movement
        bbox = self.canvas.bbox("all") or (0, 0, 1, 1)
        total_w = max(1, bbox[2] - bbox[0])
        total_h = max(1, bbox[3] - bbox[1])
        view_w = self.canvas.winfo_width() or 1
        view_h = self.canvas.winfo_height() or 1
        frac_x = dx / float(max(total_w - view_w, 1))
        frac_y = dy / float(max(total_h - view_h, 1))
        curx = self.canvas.xview()
        cury = self.canvas.yview()
        self.canvas.xview_moveto(max(0.0, min(1.0, curx[0] - frac_x)))
        self.canvas.yview_moveto(max(0.0, min(1.0, cury[0] - frac_y)))
        self._drag["x"] = ev.x
        self._drag["y"] = ev.y

    def _on_button_release(self, ev):
        if not self._drag.get("moved"):
            # click -> open detail panel for the event if any
            x = self.canvas.canvasx(ev.x)
            y = self.canvas.canvasy(ev.y)
            items = self.canvas.find_overlapping(x, y, x, y)
            for it in items:
                tags = self.canvas.gettags(it)
                for tag in tags:
                    if tag.startswith("evt:"):
                        idx = int(tag.split(":", 1)[1])
                        evobj = self._flat_events[idx]
                        self._show_detail_panel(evobj)
                        return
            self._hide_tooltip()
        else:
            # end of pan
            self._hide_tooltip()

    def _show_detail_panel(self, evobj: dict):
        """Show a modal-like detail window for an event with copy/close actions."""
        try:
            w = tk.Toplevel(self.window)
            w.title("イベント詳細")
            w.transient(self.window)
            w.grab_set()
            frm = ttk.Frame(w, padding=12)
            frm.pack(fill="both", expand=True)

            def _add_row(label, value):
                r = ttk.Frame(frm)
                r.pack(fill="x", pady=4)
                ttk.Label(r, text=label + ":", width=12).pack(side="left")
                ttk.Label(r, text=value, wraplength=520, anchor="w").pack(
                    side="left", fill="x", expand=True
                )

            _add_row("タイプ", str(evobj.get("type")))
            _add_row("ターゲット", str(evobj.get("target")))
            _add_row("時間", f"{float(evobj.get('time',0.0)):.2f}s")
            # duration if present
            if evobj.get("duration") is not None:
                _add_row("長さ", str(evobj.get("duration")))
            # full text/command
            full = evobj.get("text") or evobj.get("command") or ""
            _add_row("内容", full)

            btns = ttk.Frame(frm)
            btns.pack(fill="x", pady=(8, 0))

            def _copy():
                try:
                    self.window.clipboard_clear()
                    self.window.clipboard_append(full)
                except Exception:
                    pass

            ttk.Button(btns, text="コピー", command=_copy).pack(side="right", padx=6)
            ttk.Button(btns, text="閉じる", command=w.destroy).pack(side="right")
        except Exception:
            pass

    def _show_tooltip(self, rx, ry, evobj):
        self._hide_tooltip()
        t = tk.Toplevel(self.window)
        t.wm_overrideredirect(True)
        t.wm_geometry(f"+{rx+10}+{ry+10}")
        text = f"{evobj.get('type')}\n{evobj.get('text') or evobj.get('command') or ''}"
        lbl = tk.Label(
            t,
            text=text,
            bg="#ffffe0",
            bd=1,
            relief="solid",
            justify="left",
            font=(self.FONT_FAMILY, max(9, self.FONT_SIZE - 1)),
            padx=6,
            pady=4,
        )
        lbl.pack()
        self._tip = t

    def _hide_tooltip(self):
        if self._tip:
            try:
                self._tip.destroy()
            except:
                pass
            self._tip = None

    def _draw(self):
        self.canvas.delete("all")
        display_time = max(self.total_time, 1.0)
        width = int(display_time * self.px_per_s) + self.padding * 2
        tracks = self.track_names
        num = max(1, len(tracks))
        height = self.header_h + num * self.track_height + self.padding * 2
        has_music = bool(self.music_list)
        if has_music:
            height += self.music_track_height + 8
        self.canvas.config(scrollregion=(0, 0, self.left_width + width, height))

        # header background and time ticks
        self.canvas.create_rectangle(
            0, 0, self.left_width + width, self.header_h, fill="#f3f6f9", outline=""
        )
        step = 1 if self.px_per_s >= 40 else (2 if self.px_per_s >= 20 else 5)
        for t in range(0, int(display_time) + 1, step):
            x = self.left_width + int(t * self.px_per_s)
            self.canvas.create_line(
                x,
                self.header_h - 6,
                x,
                self.header_h + (num * self.track_height),
                fill="#e0e0e0",
            )
            self.canvas.create_text(
                x + 2,
                6,
                text=f"{t}s",
                anchor="nw",
                font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 1)),
                fill="#555",
            )

        # draw music waveform track if present
        y0 = self.header_h + self.padding
        if self.music_list:
            try:
                self._draw_music_waveform(y0)
            except Exception:
                # ensure music drawing errors don't prevent timeline from rendering
                import traceback

                traceback.print_exc()
            y0 += self.music_track_height + 8
        self._flat_events = []
        for i, name in enumerate(tracks):
            ty = y0 + i * self.track_height
            self.canvas.create_rectangle(
                0,
                ty,
                self.left_width,
                ty + self.track_height,
                fill="#fafafa",
                outline="#eee",
            )
            self.canvas.create_text(
                8,
                ty + self.track_height / 2,
                text=f"{name}",
                anchor="w",
                font=(self.FONT_FAMILY, max(9, self.FONT_SIZE)),
                fill="#222",
            )

            events = sorted(self.tracks.get(name, []), key=lambda e: e.get("time", 0))
            for ev in events:
                st = float(ev.get("time", 0.0))
                dur = float(self._estimate_duration(ev) or 0.0)
                x0 = self.left_width + int(st * self.px_per_s)
                x1 = x0 + max(8, int(dur * self.px_per_s))
                col = COLOR_ACCENT if ev.get("type") == "COMMAND" else COLOR_WARNING
                rect = self.canvas.create_rectangle(
                    x0, ty + 10, x1, ty + self.track_height - 10, fill=col, outline=col
                )
                text = ev.get("text") or ev.get("command") or ev.get("type") or ""
                short = text if len(text) <= 36 else text[:33] + "..."
                rect_w = x1 - x0
                # draw start time small label above rectangle
                try:
                    self.canvas.create_text(
                        x0 + 2,
                        ty + 2,
                        text=f"{st:.2f}s",
                        anchor="nw",
                        font=(self.FONT_FAMILY, max(7, self.FONT_SIZE - 3)),
                        fill="#444",
                    )
                except Exception:
                    pass
                # If rectangle is too narrow to fit text, render text outside to avoid overlap
                if rect_w < 120:
                    outside_x = x1 + 6
                    right_limit = self.left_width + width
                    if outside_x + 140 > right_limit:
                        # place to left
                        text_x = x0 - 6
                        anchor = "e"
                        bg_x0 = text_x - 140
                        bg_x1 = text_x + 4
                    else:
                        text_x = outside_x
                        anchor = "w"
                        bg_x0 = text_x - 4
                        bg_x1 = text_x + 140
                    ycenter = ty + self.track_height / 2
                    bg_y0 = ycenter - 12
                    bg_y1 = ycenter + 12
                    # background for readability
                    self.canvas.create_rectangle(
                        bg_x0, bg_y0, bg_x1, bg_y1, fill="#ffffe0", outline="#ddd"
                    )
                    self.canvas.create_text(
                        text_x,
                        ycenter,
                        text=short,
                        font=(self.FONT_FAMILY, max(9, self.FONT_SIZE - 1)),
                        anchor=anchor,
                    )
                else:
                    self.canvas.create_text(
                        (x0 + x1) / 2,
                        ty + self.track_height / 2,
                        text=short,
                        font=(self.FONT_FAMILY, max(9, self.FONT_SIZE - 1)),
                    )
                idx = len(self._flat_events)
                self.canvas.addtag_withtag(f"evt:{idx}", rect)
                self._flat_events.append(ev)

        # summary text
        self.canvas.create_text(
            self.left_width + width + 8,
            8,
            anchor="nw",
            text=f"総時間: {self.total_time:.2f}s",
            font=(self.FONT_FAMILY, max(9, self.FONT_SIZE)),
        )

    def _estimate_duration(self, ev):
        typ = ev.get("type", "COMMAND")
        # Prefer explicit duration field when present
        if ev.get("duration") is not None:
            try:
                return float(ev.get("duration"))
            except Exception:
                pass
        if typ == "WAIT":
            try:
                return float(
                    ev.get("text") and self._extract_seconds(ev.get("text")) or 1.0
                )
            except Exception:
                return 1.0
        if typ in ("TAKEOFF", "LAND"):
            return 1.0
        cmd = ev.get("command") or ""
        m = re.search(r"(\d+(?:\.\d+)?)", cmd)
        if m:
            try:
                v = float(m.group(1))
                return max(0.4, v / 20.0)
            except:
                pass
        return 0.8

    def _extract_seconds(self, text: str) -> float:
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
        return 1.0

    def _draw_music_waveform(self, y_top: int):
        """Draw a simple waveform for the first music file across the timeline.

        This attempts to open the first path in `self.music_list` as a WAV file and
        computes per-segment RMS values to render a filled waveform. If the file
        can't be read, a placeholder colored bar is drawn instead.
        """
        if not self.music_list:
            return
        music_path = self.music_list[0]
        display_time = max(self.total_time, 1.0)
        total_width = int(display_time * self.px_per_s)
        x0 = self.left_width
        x1 = self.left_width + total_width

        # background
        self.canvas.create_rectangle(
            x0,
            y_top,
            x1,
            y_top + self.music_track_height,
            fill="#f8f8ff",
            outline="#ddd",
        )
        label_x = 8
        self.canvas.create_text(
            label_x,
            y_top + 12,
            text="🎵 音楽 (波形)",
            anchor="nw",
            font=(self.FONT_FAMILY, max(10, self.FONT_SIZE)),
            fill=COLOR_ACCENT,
        )

        try:
            wf = wave.open(music_path, "rb")
            nframes = wf.getnframes()
            fr = wf.getframerate()
            sampwidth = wf.getsampwidth()
            nch = wf.getnchannels()
            duration = nframes / float(fr) if fr else 0.0
            # number of samples to render (cap for performance)
            segments = min(max(80, int(total_width / 4)), 400)
            frames_per_segment = max(1, int(nframes / segments))
            rms_values = []
            wf.rewind()
            for i in range(segments):
                frames = wf.readframes(frames_per_segment)
                if not frames:
                    break
                # convert to mono RMS
                if nch > 1:
                    mono = audioop.tomono(frames, sampwidth, 0.5, 0.5)
                else:
                    mono = frames
                try:
                    rms = audioop.rms(mono, sampwidth)
                except Exception:
                    rms = 0
                rms_values.append(rms)
            wf.close()

            if not rms_values:
                raise RuntimeError("no audio data")

            max_rms = max(rms_values) or 1
            # build polygon points
            seg_w = float(total_width) / len(rms_values)
            points_top = []
            points_bottom = []
            mid = y_top + self.music_track_height / 2
            amp_scale = (self.music_track_height / 2) * 0.9
            for i, r in enumerate(rms_values):
                cx = self.left_width + int(i * seg_w + seg_w / 2)
                h = (r / float(max_rms)) * amp_scale
                points_top.append((cx, mid - h))
                points_bottom.append((cx, mid + h))

            # combine polygon (top left->right then bottom right->left)
            poly = []
            for p in points_top:
                poly.extend(p)
            for p in reversed(points_bottom):
                poly.extend(p)
            self.canvas.create_polygon(poly, fill="#add8e6", outline="#5aa6c7")
        except Exception:
            # fallback: draw simple bar for each music file block proportional to duration
            # try ffmpeg conversion to wav if available and input isn't wav
            tmp_wav = None
            try:
                import shutil
                import subprocess
                import tempfile

                if not music_path.lower().endswith(".wav") and shutil.which("ffmpeg"):
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                    tmp_wav = tf.name
                    tf.close()
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        music_path,
                        "-ar",
                        "22050",
                        "-ac",
                        "1",
                        tmp_wav,
                    ]
                    subprocess.run(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    try:
                        wf = wave.open(tmp_wav, "rb")
                        # if successful, reuse logic by reading frames
                        nframes = wf.getnframes()
                        fr = wf.getframerate()
                        sampwidth = wf.getsampwidth()
                        nch = wf.getnchannels()
                        duration = nframes / float(fr) if fr else 0.0
                        segments = min(max(80, int(total_width / 4)), 400)
                        frames_per_segment = max(1, int(nframes / segments))
                        rms_values = []
                        wf.rewind()
                        for i in range(segments):
                            frames = wf.readframes(frames_per_segment)
                            if not frames:
                                break
                            mono = frames
                            try:
                                rms = audioop.rms(mono, sampwidth)
                            except Exception:
                                rms = 0
                            rms_values.append(rms)
                        wf.close()
                        if rms_values:
                            max_rms = max(rms_values) or 1
                            seg_w = float(total_width) / len(rms_values)
                            points_top = []
                            points_bottom = []
                            mid = y_top + self.music_track_height / 2
                            amp_scale = (self.music_track_height / 2) * 0.9
                            for i, r in enumerate(rms_values):
                                cx = self.left_width + int(i * seg_w + seg_w / 2)
                                h = (r / float(max_rms)) * amp_scale
                                points_top.append((cx, mid - h))
                                points_bottom.append((cx, mid + h))
                            poly = []
                            for p in points_top:
                                poly.extend(p)
                            for p in reversed(points_bottom):
                                poly.extend(p)
                            self.canvas.create_polygon(
                                poly, fill="#add8e6", outline="#5aa6c7"
                            )
                            # cleanup temp
                            try:
                                os.unlink(tmp_wav)
                            except Exception:
                                pass
                            return
                    except Exception:
                        pass
                    finally:
                        try:
                            if wf:
                                wf.close()
                        except Exception:
                            pass

            except Exception:
                pass

            block_w = max(4, int(total_width / max(1, len(self.music_list))))
            cur = 0
            for i, mp in enumerate(self.music_list):
                bx0 = self.left_width + cur
                bx1 = bx0 + block_w
                self.canvas.create_rectangle(
                    bx0,
                    y_top + 8,
                    bx1,
                    y_top + self.music_track_height - 8,
                    fill="#90EE90",
                    outline="#2e8b57",
                )
                fname = os.path.basename(mp)
                self.canvas.create_text(
                    bx0 + 4,
                    y_top + 10,
                    text=(fname if len(fname) < 20 else fname[:17] + "..."),
                    anchor="nw",
                    font=(self.FONT_FAMILY, max(8, self.FONT_SIZE - 2)),
                )
                cur += block_w + 6

        # no extra redraw here; caller (_draw) continues drawing tracks
        return

    def _update_zoom_label(self):
        """ズームラベルを更新"""
        try:
            zoom_percent = int((self.px_per_s / 60) * 100)
            self.zoom_label.config(text=f"{zoom_percent}%")
        except Exception:
            pass
