"""Ventana principal de GuiaClick."""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

from . import APP_NAME, APP_VERSION, theme
from . import capture, guide, llm, project
from .config import AppConfig, load_config, save_config, get_data_dir

logger = logging.getLogger(__name__)

REC_TITLE = "● GuiaClick — Grabando"   # marcador unico para ignorar sus propios clics


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1080x740")
        self.minsize(960, 660)
        theme.apply(self)
        try:
            ico = Path(__file__).resolve().parent.parent / "build" / "icon.ico"
            if ico.is_file():
                self.iconbitmap(str(ico))
        except tk.TclError:
            pass

        self.cfg: AppConfig = load_config()
        self.recorder: capture.ClickRecorder | None = None
        self.steps: list[capture.Step] = []
        self.sel = -1
        self._toolbar: tk.Toplevel | None = None
        self._poll_id: str | None = None
        self._closing = False
        self._photo = None
        self._disp_scale = 1.0
        self._drag = None
        self._tool_mode = "blur"       # "blur" (difuminar) | "crop" (recortar)
        self._project_path: str | None = None
        self._autosave_id: str | None = None
        self._append_base: list | None = None   # pasos previos al grabar en modo "añadir"

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._first_run_check)
        self.after(350, self._offer_restore)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        theme.header(self, APP_NAME, "Graba un proceso y crea una guia paso a paso · 100% local")
        self.status = theme.status_bar(self, "Pulsa 'Grabar guia' y haz tu proceso normalmente.")

        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill="x")
        self.btn_rec = ttk.Button(top, text="●  Grabar guia", style="Rec.TButton",
                                  command=self._toggle_record)
        self.btn_rec.pack(side="left")
        meta = ttk.Frame(top); meta.pack(side="left", padx=16, fill="x", expand=True)
        ttk.Label(meta, text="Titulo de la guia", style="Muted.TLabel").pack(anchor="w")
        self.var_title = tk.StringVar(value="Como hacer …")
        ttk.Entry(meta, textvariable=self.var_title, width=40).pack(anchor="w", fill="x")
        ttk.Button(top, text="⚙ Opciones", command=self._settings_dialog).pack(side="right")
        ttk.Button(top, text="Configurar IA…", command=self._ollama_dialog).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="📂 Abrir", command=self._open_project).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="💾 Guardar", command=self._save_project).pack(side="right", padx=(0, 6))

        body = ttk.Frame(self, padding=(14, 0)); body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # lista de pasos
        left = ttk.LabelFrame(body, text="Pasos", padding=8)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        self.lst = tk.Listbox(left, width=30, height=22, activestyle="none",
                              font=(theme.FONT, 10), bg=theme.WHITE, fg=theme.TEXT,
                              selectbackground=theme.PRIMARY, selectforeground=theme.WHITE)
        self.lst.pack(fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", self._on_list_select)
        row = ttk.Frame(left); row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="▲", width=3, command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(row, text="▼", width=3, command=lambda: self._move(1)).pack(side="left", padx=2)
        ttk.Button(row, text="🗑", width=3, command=self._delete_step).pack(side="left")
        ttk.Button(row, text="+ paso manual", command=self._add_manual_step).pack(side="right")

        # editor del paso
        right = ttk.Frame(body); right.grid(row=0, column=1, sticky="nsew")
        ed = ttk.Frame(right); ed.pack(fill="x")
        ttk.Label(ed, text="Texto del paso", style="H.TLabel").pack(side="left")
        self.lbl_step = ttk.Label(ed, text="", style="Muted.TLabel"); self.lbl_step.pack(side="right")
        self.var_step = tk.StringVar()
        e = ttk.Entry(right, textvariable=self.var_step)
        e.pack(fill="x", pady=(2, 4))
        e.bind("<KeyRelease>", self._on_edit_title)
        ttk.Label(right, text="Nota / descripcion (opcional)", style="Muted.TLabel").pack(anchor="w")
        self.txt_note = tk.Text(right, height=2, wrap="word", font=(theme.FONT, 10),
                                bg=theme.WHITE, relief="solid", borderwidth=1)
        self.txt_note.pack(fill="x", pady=(0, 6))
        self.txt_note.bind("<KeyRelease>", self._on_edit_note)

        canwrap = ttk.Frame(right); canwrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canwrap, bg="#33445A", highlightthickness=1,
                                highlightbackground=theme.BORDER, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._blur_start)
        self.canvas.bind("<B1-Motion>", self._blur_drag)
        self.canvas.bind("<ButtonRelease-1>", self._blur_end)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self._resize_id: str | None = None
        self._last_canvas_size = (0, 0)
        toolrow = ttk.Frame(right); toolrow.pack(fill="x", pady=(4, 0))
        ttk.Label(toolrow, text="Herramienta:", style="Muted.TLabel").pack(side="left")
        self.var_tool = tk.StringVar(value="blur")
        ttk.Radiobutton(toolrow, text="Difuminar", value="blur", variable=self.var_tool,
                        command=self._on_tool_change).pack(side="left", padx=(6, 0))
        ttk.Radiobutton(toolrow, text="Recortar", value="crop", variable=self.var_tool,
                        command=self._on_tool_change).pack(side="left", padx=(6, 0))
        self.lbl_tool = ttk.Label(toolrow, text="Arrastra sobre la imagen para difuminar datos "
                                  "sensibles.", style="Muted.TLabel")
        self.lbl_tool.pack(side="left", padx=(12, 0))

        tiprow = ttk.Frame(right); tiprow.pack(fill="x", pady=(4, 0))
        ttk.Button(tiprow, text="Previsualizar paso", command=self._preview_step).pack(side="left")
        ttk.Button(tiprow, text="Reemplazar imagen…", command=self._replace_image).pack(side="left", padx=6)
        ttk.Button(tiprow, text="Deshacer recorte", command=self._undo_crop).pack(side="right")
        ttk.Button(tiprow, text="Quitar difuminados", command=self._clear_blur).pack(side="right", padx=6)

        bar = ttk.Frame(self, padding=(14, 8)); bar.pack(fill="x")
        ttk.Button(bar, text="Mejorar textos con IA", command=self._improve_ai).pack(side="left")
        ttk.Button(bar, text="Abrir carpeta", command=self._open_folder).pack(side="left", padx=(8, 0))
        self.btn_pdf = ttk.Button(bar, text="Exportar PDF", style="Primary.TButton",
                                  command=lambda: self._export("pdf"))
        self.btn_pdf.pack(side="right")
        ttk.Button(bar, text="HTML", command=lambda: self._export("html")).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="Markdown", command=lambda: self._export("md")).pack(side="right", padx=(0, 6))

    # -------------------------------------------------------------- grabar
    def _toggle_record(self) -> None:
        if self.recorder is not None:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self) -> None:
        if not capture.AVAILABLE:
            messagebox.showerror(APP_NAME, "La captura no esta disponible en este equipo.")
            return
        self._append_base = None
        if self.steps:
            # 3 opciones: añadir al final (continuar la guia), empezar de cero, o cancelar
            ans = messagebox.askyesnocancel(
                APP_NAME,
                "Ya tienes una guia abierta con "
                f"{len(self.steps)} paso(s).\n\n"
                "•  Si  →  AÑADIR los nuevos pasos al final de esta guia.\n"
                "•  No  →  empezar una guia NUEVA (descarta la actual).\n"
                "•  Cancelar  →  no grabar.")
            if ans is None:
                return
            if ans:
                self._append_base = list(self.steps)   # se conservan y se anteponen al parar
        # Cancela un autoguardado con debounce pendiente: si saltara ahora (con
        # steps vacio) borraria la copia de recuperacion en disco.
        if self._autosave_id is not None:
            try:
                self.after_cancel(self._autosave_id)
            except (tk.TclError, ValueError):
                pass
            self._autosave_id = None
        self.steps = []
        self.sel = -1
        self._refresh_list()
        self._draw_canvas()
        self.recorder = capture.ClickRecorder(
            capture_right=self.cfg.capture_right_click,
            ignore_hwnds=self._ignore_hwnds, ignore_titles=lambda: {REC_TITLE})
        self.recorder.start()
        self.btn_rec.config(text="⏹  Detener")
        self._show_toolbar()
        self.withdraw()
        self._set_status("Grabando… haz tu proceso. Cada clic = un paso.")
        self._poll_recording()

    def _ignore_hwnds(self) -> set:
        s = set()
        for w in (self, self._toolbar):
            try:
                if w is not None:
                    wid = int(w.winfo_id())
                    s.add(wid)
                    s.add(capture.root_hwnd(wid))   # Tk envuelve: anade la ventana raiz
            except (tk.TclError, ValueError):
                pass
        return s

    def _show_toolbar(self) -> None:
        tb = tk.Toplevel(self)
        tb.title(REC_TITLE)
        tb.configure(bg=theme.NAVY)
        tb.attributes("-topmost", True)
        tb.resizable(False, False)
        try:
            tb.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        f = tk.Frame(tb, bg=theme.NAVY)
        f.pack(padx=12, pady=8)
        grip = tk.Label(f, text="⠿", bg=theme.NAVY, fg="#8aa0bd", font=(theme.FONT, 11),
                        cursor="fleur")
        grip.pack(side="left", padx=(0, 8))
        self._tb_lbl = tk.Label(f, text="● Grabando · 0 pasos", bg=theme.NAVY, fg="#fff",
                                font=(theme.FONT, 11, "bold"), cursor="fleur")
        self._tb_lbl.pack(side="left", padx=(0, 12))
        tk.Button(f, text="⏹ Detener", command=self._stop_record, bg=theme.PRIMARY, fg="#fff",
                  relief="flat", font=(theme.FONT, 10, "bold"), padx=12, pady=4).pack(side="left")
        # arrastrar la barra (por si tapa lo que el usuario necesita clicar)
        self._tb_drag = None
        for w in (grip, self._tb_lbl, f):
            w.bind("<ButtonPress-1>", self._tb_drag_start)
            w.bind("<B1-Motion>", self._tb_drag_move)
        tb.update_idletasks()
        sw = tb.winfo_screenwidth()
        tb.geometry(f"+{(sw - tb.winfo_width()) // 2}+24")
        # La barra NO debe salir en las capturas (es un control de grabacion). En
        # Windows 10 2004+ la ocultamos de la captura sin ocultarla en pantalla.
        if not capture.exclude_from_capture(capture.root_hwnd(tb.winfo_id())):
            logger.debug("SetWindowDisplayAffinity no aplico; la barra podria salir en capturas.")
        # Cerrar la barra con la X (o Alt+F4) equivale a 'Detener': sin esto la
        # ventana principal seguiria oculta y la grabacion quedaria zombie (habria
        # que matar el proceso), perdiendo los pasos aun en memoria.
        tb.protocol("WM_DELETE_WINDOW", self._stop_record)
        self._toolbar = tb

    def _tb_drag_start(self, e) -> None:
        self._tb_drag = (e.x_root, e.y_root)

    def _tb_drag_move(self, e) -> None:
        if self._tb_drag is None or self._toolbar is None:
            return
        dx, dy = e.x_root - self._tb_drag[0], e.y_root - self._tb_drag[1]
        try:
            x = self._toolbar.winfo_x() + dx
            y = self._toolbar.winfo_y() + dy
            self._toolbar.geometry(f"+{x}+{y}")
        except tk.TclError:
            return
        self._tb_drag = (e.x_root, e.y_root)

    def _poll_recording(self) -> None:
        if self.recorder is None or self._closing:
            return
        try:
            self._tb_lbl.config(text=f"● Grabando · {self.recorder.count()} pasos")
        except (tk.TclError, AttributeError):
            pass
        self._poll_id = self.after(300, self._poll_recording)

    def _stop_record(self) -> None:
        if self.recorder is None:
            return
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except (tk.TclError, ValueError):
                pass
            self._poll_id = None
        recorded = self.recorder.stop()
        self.recorder = None
        if self._toolbar is not None:
            try:
                self._toolbar.destroy()
            except tk.TclError:
                pass
            self._toolbar = None
            self._tb_lbl = None     # evita referencia colgada a un widget destruido
        self.deiconify()
        self.lift()
        self.btn_rec.config(text="●  Grabar guia")
        # modo "añadir": los nuevos pasos van al final de la guia previa
        base = self._append_base or []
        self._append_base = None
        self.steps = base + recorded
        # texto por defecto de cada paso (numerado por su posicion final)
        for i, st in enumerate(self.steps, 1):
            if not st.title:
                st.title = guide.auto_title(st, i)
        self._refresh_list()
        if self.steps:
            if base and recorded:
                self._select(len(base))      # primer paso nuevo, para verlo enseguida
                self._set_status(f"{len(recorded)} paso(s) añadido(s) · {len(self.steps)} en total.")
            else:
                self._select(0)
                if base:                     # se grabo en modo añadir pero sin clics
                    self._set_status("No se capturo ningun clic; la guia se mantiene intacta.")
                else:
                    self._set_status(f"{len(self.steps)} pasos capturados. Edita y exporta.")
        else:
            self._set_status("No se capturo ningun clic.")
        self._autosave()

    # -------------------------------------------------------------- lista
    def _refresh_list(self) -> None:
        self.lst.delete(0, "end")
        for i, st in enumerate(self.steps, 1):
            self.lst.insert("end", f"{i}. {guide.title_or_auto(st, i)[:38]}")

    def _on_list_select(self, _e=None) -> None:
        idx = self.lst.curselection()
        if idx:
            self._select(idx[0])

    def _select(self, i: int) -> None:
        if not (0 <= i < len(self.steps)):
            return
        self.sel = i
        self.lst.selection_clear(0, "end")
        self.lst.selection_set(i)
        st = self.steps[i]
        self.lbl_step.config(text=f"Paso {i + 1} de {len(self.steps)}")
        self.var_step.set(guide.title_or_auto(st, i + 1))
        self.txt_note.delete("1.0", "end")
        self.txt_note.insert("1.0", st.note)
        self._draw_canvas()

    def _cur(self) -> capture.Step | None:
        return self.steps[self.sel] if 0 <= self.sel < len(self.steps) else None

    # -------------------------------------------------------------- editor
    def _on_edit_title(self, _e=None) -> None:
        st = self._cur()
        if st is not None:
            st.title = self.var_step.get()
            i = self.sel
            try:
                self.lst.delete(i)
                self.lst.insert(i, f"{i + 1}. {guide.title_or_auto(st, i + 1)[:38]}")
                self.lst.selection_set(i)
            except tk.TclError:
                pass
            self._schedule_autosave()

    def _on_edit_note(self, _e=None) -> None:
        st = self._cur()
        if st is not None:
            st.note = self.txt_note.get("1.0", "end").strip()
            self._schedule_autosave()

    def _on_canvas_resize(self, event) -> None:
        """Redibuja al redimensionar la ventana, pero con freno: durante un arrastre
        de borde llegan decenas de <Configure>/seg y cada redibujo crea un PhotoImage
        nuevo. Debounce de 120 ms y salta si el tamano no cambio de verdad."""
        size = (event.width, event.height)
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size
        if self._resize_id is not None:
            try:
                self.after_cancel(self._resize_id)
            except (tk.TclError, ValueError):
                pass
        self._resize_id = self.after(120, self._draw_canvas)

    def _draw_canvas(self) -> None:
        from PIL import Image, ImageTk
        self._resize_id = None
        if self._closing:
            return
        self.canvas.delete("all")
        st = self._cur()
        if st is None:
            self.canvas.create_text(self.canvas.winfo_width() // 2 or 360, 180,
                                    text="Graba una guia para ver los pasos aqui", fill="white")
            self._photo = None
            return
        self.canvas.update_idletasks()
        cw = max(400, self.canvas.winfo_width() - 4)
        ch = max(300, self.canvas.winfo_height() - 4)
        img = st.image
        scale = min(cw / img.width, ch / img.height, 1.0)
        self._disp_scale = scale
        disp = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        photo = ImageTk.PhotoImage(disp)
        self._photo = photo
        self._img_w, self._img_h = disp.width, disp.height
        # offsets en float: el difuminado mapea canvas<->imagen sin perder precision
        self._off_x = (self.canvas.winfo_width() - disp.width) / 2
        self._off_y = (self.canvas.winfo_height() - disp.height) / 2
        self.canvas.create_image(self._off_x, self._off_y, image=photo, anchor="nw")
        # marca del clic
        cx = self._off_x + int(st.x * scale)
        cy = self._off_y + int(st.y * scale)
        rr = 14
        self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=theme.PRIMARY, width=3)
        # zonas difuminadas
        for r in st.blur:
            x0, y0, x1, y1 = r
            self.canvas.create_rectangle(
                self._off_x + x0 * scale, self._off_y + y0 * scale,
                self._off_x + x1 * scale, self._off_y + y1 * scale,
                outline="#111", fill="#94A3B8", stipple="gray50")

    # blur con arrastre
    def _blur_start(self, e) -> None:
        if self._cur() is None:
            return
        self._drag = (e.x, e.y)
        self._drag_rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                       outline=theme.PRIMARY, width=2)

    def _blur_drag(self, e) -> None:
        if self._drag:
            self.canvas.coords(self._drag_rect, self._drag[0], self._drag[1], e.x, e.y)

    def _blur_end(self, e) -> None:
        if not self._drag:
            return
        x0, y0 = self._drag
        x1, y1 = e.x, e.y
        self._drag = None
        st = self._cur()
        if st is None:
            return
        # a coords de imagen
        s = self._disp_scale or 1.0
        ix0 = (min(x0, x1) - self._off_x) / s
        iy0 = (min(y0, y1) - self._off_y) / s
        ix1 = (max(x0, x1) - self._off_x) / s
        iy1 = (max(y0, y1) - self._off_y) / s
        if self._tool_mode == "crop":
            if capture.crop_step(st, (ix0, iy0, ix1, iy1)):
                self._set_status("Paso recortado. 'Deshacer recorte' vuelve al original.")
                self._autosave()
            else:
                self._set_status("El recorte es demasiado pequeno.")
        elif (ix1 - ix0) >= 4 and (iy1 - iy0) >= 4:
            st.blur.append((int(ix0), int(iy0), int(ix1), int(iy1)))
            self._autosave()
        self._draw_canvas()

    def _on_tool_change(self) -> None:
        self._tool_mode = self.var_tool.get()
        if self._tool_mode == "crop":
            self.lbl_tool.config(text="Arrastra para recortar la imagen y resaltar el paso.")
        else:
            self.lbl_tool.config(text="Arrastra sobre la imagen para difuminar datos sensibles.")

    def _undo_crop(self) -> None:
        st = self._cur()
        if st is not None and capture.restore_step(st):
            self._draw_canvas()
            self._set_status("Recorte deshecho: imagen original restaurada.")
            self._autosave()

    def _clear_blur(self) -> None:
        st = self._cur()
        if st is not None:
            st.blur = []
            self._draw_canvas()
            self._autosave()

    def _preview_step(self) -> None:
        st = self._cur()
        if st is None:
            return
        try:
            img = guide.render_step(st, self.sel + 1, highlight_color=self.cfg.highlight_color,
                                    blur_strength=self.cfg.blur_strength)
            out = get_data_dir() / "_preview.png"
            img.save(out)
            os.startfile(str(out))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"No se pudo previsualizar: {exc}")

    def _move(self, delta: int) -> None:
        i = self.sel
        j = i + delta
        if 0 <= i < len(self.steps) and 0 <= j < len(self.steps):
            self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
            self._refresh_list()
            self._select(j)
            self._autosave()   # persistir el nuevo orden como el resto de mutaciones

    def _delete_step(self) -> None:
        i = self.sel
        if 0 <= i < len(self.steps):
            del self.steps[i]
            self._refresh_list()
            self._select(min(i, len(self.steps) - 1))
            if not self.steps:
                self._draw_canvas()
            self._autosave()

    def _add_manual_step(self) -> None:
        if not self.steps:
            messagebox.showinfo(APP_NAME, "Primero graba una guia (o abre una guardada). "
                                "El paso manual se crea copiando el paso actual; luego puedes "
                                "'Reemplazar imagen…' para poner otra captura.")
            return
        st = self._cur()
        if st is None:
            return
        new = capture.Step(image=st.image.copy(), x=st.x, y=st.y, window=st.window,
                           button=st.button, title="Paso nuevo", note="", blur=list(st.blur))
        self.steps.insert(self.sel + 1, new)
        self._refresh_list()
        self._select(self.sel + 1)
        self._set_status("Paso manual añadido. Usa 'Reemplazar imagen…' para cambiar su captura.")
        self._autosave()

    def _replace_image(self) -> None:
        """Sustituye la captura del paso actual por una imagen de archivo. Util para
        pasos manuales o para corregir una captura concreta sin volver a grabar."""
        st = self._cur()
        if st is None:
            messagebox.showinfo(APP_NAME, "Selecciona primero un paso de la lista.")
            return
        p = filedialog.askopenfilename(
            title="Elegir imagen para este paso", initialdir=self.cfg.output_dir,
            filetypes=[("Imagenes", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Todos", "*.*")])
        if not p:
            return
        from PIL import Image
        try:
            img = Image.open(p)
            img.load()
            img = img.convert("RGB")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"No se pudo abrir la imagen:\n{exc}")
            return
        st.image = img
        st.original = None            # el recorte previo ya no aplica a la nueva imagen
        st.blur = []                  # los difuminados eran para la imagen anterior
        st.x = min(max(0, st.x), img.width - 1)    # marca del clic dentro de la nueva imagen
        st.y = min(max(0, st.y), img.height - 1)
        self._draw_canvas()
        self._set_status("Imagen del paso reemplazada.")
        self._autosave()

    # -------------------------------------------------------------- export
    def _export(self, fmt: str) -> None:
        if not self.steps:
            messagebox.showinfo(APP_NAME, "No hay pasos que exportar. Graba una guia primero.")
            return
        title = self.var_title.get().strip() or "Guia"
        safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Guia"
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        outdir = Path(self.cfg.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        hl, bs = self.cfg.highlight_color, self.cfg.blur_strength
        steps = list(self.steps)   # snapshot: evita carrera si se edita/borra mientras exporta

        def work():
            if fmt == "html":
                p = str(outdir / f"{safe}_{stamp}.html")
                return guide.export_html(steps, p, title=title, highlight_color=hl, blur_strength=bs)
            if fmt == "md":
                p = str(outdir / f"{safe}_{stamp}.md")
                return guide.export_markdown(steps, p, title=title, highlight_color=hl, blur_strength=bs)
            p = str(outdir / f"{safe}_{stamp}.pdf")
            return guide.export_pdf(steps, p, title=title, highlight_color=hl, blur_strength=bs)

        self._set_status(f"Exportando {fmt.upper()}…")

        def runner():
            try:
                out = work()
                self._ui(lambda: self._export_done(out, fmt))
            except Exception as exc:  # noqa: BLE001
                logger.exception("export fallo")
                self._ui(lambda: messagebox.showerror(APP_NAME, f"No se pudo exportar:\n{exc}"))
        threading.Thread(target=runner, daemon=True).start()

    def _export_done(self, out: str, fmt: str) -> None:
        self._set_status(f"Exportado: {out}")
        if messagebox.askyesno(APP_NAME, f"Guardado:\n{out}\n\n¿Abrirlo ahora?"):
            try:
                if fmt == "html":
                    webbrowser.open(Path(out).as_uri())
                else:
                    os.startfile(out)
            except OSError:
                pass

    def _improve_ai(self) -> None:
        if not self.steps:
            return
        if not llm.available():
            messagebox.showinfo(APP_NAME, "Para mejorar los textos necesitas Ollama. "
                                "Abre 'Configurar IA…' para elegir Ollama o una API.")
            return
        if getattr(self, "_improving", False):
            return                       # ya hay una mejora en curso: no relanzar
        self._improving = True
        steps = list(self.steps)   # snapshot: el usuario podria borrar pasos mientras corre
        n = len(steps)
        self._set_status(f"Mejorando textos con IA…  (0/{n})")

        def runner():
            # Feedback por paso: sin esto, la 1a llamada (que carga el modelo en
            # memoria: ~35 s o mas en frio) congela el estado y parece un cuelgue.
            done = failed = 0
            try:
                for i, st in enumerate(steps, 1):
                    if self._closing:
                        return
                    note = ("  ·  cargando el modelo la primera vez, aguarda…"
                            if i == 1 else "")
                    self._ui(lambda i=i, note=note: self._set_status(
                        f"Mejorando textos con IA…  ({i}/{n}){note}"))
                    base = guide.title_or_auto(st, i)
                    try:
                        better = llm.polish_step(base)
                    except Exception:    # noqa: BLE001  nunca matar el hilo en silencio
                        logger.exception("polish_step fallo en el paso %d", i)
                        better = None
                    if better:
                        st.title = better.strip().strip('"')
                        done += 1
                    else:
                        failed += 1
            except Exception:            # noqa: BLE001
                logger.exception("Fallo inesperado al mejorar textos con IA")
            finally:
                self._improving = False
                self._ui(lambda d=done, f=failed: self._after_improve(d, f))

        threading.Thread(target=runner, daemon=True).start()

    def _after_improve(self, done: int = 0, failed: int = 0) -> None:
        self._refresh_list()
        if 0 <= self.sel < len(self.steps):
            self._select(self.sel)
        if done and not failed:
            self._set_status(f"Textos mejorados con IA ({done}).")
        elif done:
            self._set_status(f"Mejorados {done}; {failed} sin cambios.")
        else:
            self._set_status("No se pudo mejorar ningun texto.")
            messagebox.showinfo(
                APP_NAME, "No se pudo conectar con la IA para mejorar los textos.\n\n"
                "Comprueba que Ollama sigue abierto (su icono en la barra de tareas) y que "
                "el modelo esta disponible, e intentalo de nuevo. La primera vez puede tardar "
                "unos segundos en cargar el modelo en memoria.")

    def _open_folder(self) -> None:
        try:
            os.startfile(self.cfg.output_dir)
        except OSError:
            pass

    # ---------------------------------------------------------- proyecto (.guiaclick)
    def _autosave(self) -> None:
        # Guarda la sesion en segundo plano para poder recuperarla si se cierra
        # la app. No molesta al usuario y no bloquea la UI.
        steps = list(self.steps)
        title = self.var_title.get()
        threading.Thread(
            target=lambda: project.autosave(get_data_dir(), steps, title), daemon=True).start()

    def _schedule_autosave(self) -> None:
        # Debounce para ediciones de texto (titulo/nota): no reescribir el zip en
        # cada tecla, solo 1,5 s despues de la ultima.
        if self._closing or not self.steps:
            return
        if self._autosave_id is not None:
            try:
                self.after_cancel(self._autosave_id)
            except (tk.TclError, ValueError):
                pass
        self._autosave_id = self.after(1500, self._autosave)

    def _save_project(self) -> None:
        if not self.steps:
            messagebox.showinfo(APP_NAME, "No hay ninguna guia que guardar. Graba una primero.")
            return
        title = self.var_title.get().strip() or "Guia"
        safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Guia"
        p = filedialog.asksaveasfilename(
            title="Guardar guia", defaultextension=project.EXT,
            initialfile=f"{safe}{project.EXT}", initialdir=self.cfg.output_dir,
            filetypes=[("Guia de GuiaClick", f"*{project.EXT}")])
        if not p:
            return
        try:
            project.save_project(p, list(self.steps), title)
            self._project_path = p
            self._set_status(f"Guia guardada: {p}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"No se pudo guardar:\n{exc}")

    def _open_project(self) -> None:
        if self.recorder is not None:
            return
        if self.steps and not messagebox.askyesno(
                APP_NAME, "Abrir otra guia descartara los pasos actuales sin guardar. ¿Seguir?"):
            return
        p = filedialog.askopenfilename(
            title="Abrir guia", initialdir=self.cfg.output_dir,
            filetypes=[("Guia de GuiaClick", f"*{project.EXT}")])
        if not p:
            return
        try:
            steps, title = project.load_project(p)
        except project.ProjectError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self._load_steps(steps, title)
        self._project_path = p
        self._set_status(f"Guia abierta: {len(steps)} pasos.")

    def _load_steps(self, steps, title: str) -> None:
        self.steps = steps
        if title:
            self.var_title.set(title)
        self.sel = -1
        self._refresh_list()
        if self.steps:
            self._select(0)
        else:
            self._draw_canvas()

    def _offer_restore(self) -> None:
        """Al abrir la app, si quedo una guia sin terminar, ofrece recuperarla."""
        if self._closing or self.steps:
            return
        data = project.load_autosave(get_data_dir())
        if not data or not data[0]:
            return
        steps, title = data
        if messagebox.askyesno(
                APP_NAME, f"Se encontro una guia sin terminar ({len(steps)} pasos"
                + (f": «{title}»" if title else "") + ").\n\n¿Quieres recuperarla?"):
            self._load_steps(steps, title)
            self._set_status(f"Guia recuperada: {len(steps)} pasos.")
        else:
            project.clear_autosave(get_data_dir())

    # -------------------------------------------------------------- dialogos
    def _settings_dialog(self) -> None:
        win = tk.Toplevel(self); theme.center_window(win)
        win.title("Opciones"); win.configure(bg=theme.BG); win.transient(self); win.resizable(False, False)
        frm = ttk.Frame(win, padding=16); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Opciones de GuiaClick", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        v_right = tk.BooleanVar(value=self.cfg.capture_right_click)
        ttk.Checkbutton(frm, text="Capturar tambien el clic derecho", variable=v_right).pack(anchor="w")
        cr = ttk.Frame(frm); cr.pack(fill="x", pady=(8, 0))
        ttk.Label(cr, text="Color del resaltado:").pack(side="left")
        col = {"v": self.cfg.highlight_color}
        sw = tk.Label(cr, text="    ", bg=self.cfg.highlight_color, relief="solid", borderwidth=1)
        sw.pack(side="left", padx=8)

        def pick():
            c = colorchooser.askcolor(color=col["v"], parent=win)[1]
            if c:
                col["v"] = c
                sw.config(bg=c)
        ttk.Button(cr, text="Elegir…", command=pick).pack(side="left")
        br = ttk.Frame(frm); br.pack(fill="x", pady=(8, 0))
        ttk.Label(br, text="Intensidad del difuminado:").pack(side="left")
        v_blur = tk.IntVar(value=self.cfg.blur_strength)
        ttk.Spinbox(br, from_=4, to=40, textvariable=v_blur, width=5).pack(side="left", padx=8)
        od = ttk.Frame(frm); od.pack(fill="x", pady=(8, 0))
        outdir = {"v": self.cfg.output_dir}   # pendiente: no se persiste hasta "Guardar"
        lbl_dir = ttk.Label(od, text=f"Carpeta de salida: {outdir['v']}", style="Muted.TLabel",
                            wraplength=360)
        lbl_dir.pack(side="left")

        def change_dir():
            # Actualiza la etiqueta EN SITIO: recrear el dialogo perderia los demas
            # cambios sin guardar (clic derecho, color, difuminado).
            d = filedialog.askdirectory(initialdir=outdir["v"], parent=win)
            if d:
                outdir["v"] = d
                lbl_dir.config(text=f"Carpeta de salida: {d}")

        def save():
            self.cfg.capture_right_click = bool(v_right.get())
            self.cfg.highlight_color = col["v"]
            self.cfg.blur_strength = int(v_blur.get())
            self.cfg.output_dir = outdir["v"]
            save_config(self.cfg)
            win.destroy()
            if 0 <= self.sel < len(self.steps):
                self._draw_canvas()
        ttk.Button(od, text="Cambiar…", command=change_dir).pack(side="right")
        ttk.Button(frm, text="Guardar", style="Primary.TButton", command=save).pack(anchor="e", pady=(14, 0))
        win.grab_set()

    def _ollama_dialog(self) -> None:
        # Dialogo de IA UNIFICADO de la suite: Ollama local (gratis) o una API
        # potente (OpenAI/Gemini/Anthropic). Se configura una vez para las 5 apps.
        from octonove_core.ai_dialog import show_ai_dialog
        show_ai_dialog(self, on_saved=lambda: self._set_status(
            "IA configurada. Ya puedes usar 'Mejorar textos con IA'."))

    # -------------------------------------------------------------- varios
    def _ui(self, fn) -> None:
        if self._closing:
            return
        try:
            self.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _set_status(self, text: str) -> None:
        try:
            self.status.config(text=text)
        except tk.TclError:
            pass

    def _first_run_check(self) -> None:
        if self._closing or self.cfg.seen_welcome:
            return
        self.cfg.seen_welcome = True
        save_config(self.cfg)
        messagebox.showinfo(
            APP_NAME, "Bienvenido a GuiaClick.\n\n"
            "1. Pulsa 'Grabar guia'.\n2. Haz tu proceso: cada clic captura un paso.\n"
            "3. Pulsa 'Detener' en la barra flotante (esa barra NO sale en las capturas).\n"
            "4. Edita los textos; con la herramienta puedes 'Difuminar' datos o 'Recortar' "
            "para resaltar el paso; exporta a HTML, Markdown o PDF.\n\n"
            "Puedes 'Guardar' la guia y seguir despues: al reabrir, GuiaClick te ofrece "
            "recuperar la ultima que dejaste sin terminar.\n\nTodo ocurre en tu PC.")

    def _on_close(self) -> None:
        if self.recorder is not None:
            if not messagebox.askyesno(APP_NAME, "Hay una grabacion en curso. ¿Salir igualmente?"):
                return
            try:
                recorded = self.recorder.stop()
            except Exception:  # noqa: BLE001
                recorded = []
            # Fusiona lo grabado con la guia previa (modo "añadir"): sin esto,
            # self.steps seria [] durante la grabacion y el autoguardado de abajo
            # borraria la guia cargada al cerrar.
            base = self._append_base or []
            self._append_base = None
            if base or recorded:
                self.steps = base + recorded
        # Guarda el estado final de forma sincrona (incluye ultimas ediciones de
        # texto) para poder recuperar la guia la proxima vez que abras la app.
        if self.steps:
            try:
                project.autosave(get_data_dir(), list(self.steps), self.var_title.get())
            except Exception:  # noqa: BLE001
                pass
        self._closing = True
        for tid in (self._poll_id, self._resize_id, self._autosave_id):
            if tid:
                try:
                    self.after_cancel(tid)
                except (tk.TclError, ValueError):
                    pass
        self.destroy()


def main() -> None:
    from .config import setup_logging
    setup_logging()
    App().mainloop()
