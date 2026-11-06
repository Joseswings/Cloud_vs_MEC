"""Ejecutar: python app.py"""
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid

from meccloud.core import DEFAULT_URLS, Runner, export_csv, summary, validate_url
from meccloud.power import PowerMonitor

BG, PANEL, TEXT, MUTED = '#101722', '#192333', '#edf2fa', '#a6b6ca'
COLORS = {'MEC': '#44d5bd', 'Cloud': '#76aaff'}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('IoT MEC–Cloud | Tiempo de respuesta HTTP')
        self.geometry('1120x850')
        self.minsize(850, 720)
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('TLabel', background=BG)
        style.configure('Panel.TLabel', background=PANEL)
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
        style.configure('TButton', padding=(12, 8), background='#2a3d56')
        style.map('TButton', background=[('active', '#385477'), ('disabled', '#202a38')])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)
        style.configure('TCombobox', fieldbackground=PANEL, foreground=TEXT, arrowcolor=TEXT)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL)], selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', TEXT)])
        self.out = queue.Queue()
        self.runner = None
        self.samples = []
        self.session_id = str(uuid.uuid4())
        self.segment = 1
        self.round_no = 0
        self.condition = tk.StringVar(value='Base')
        self.active_condition = 'Base · serie 1'
        self.pending_condition = False
        self.controls = []
        self.urls = {d: tk.StringVar(value=u) for d, u in DEFAULT_URLS.items()}
        self.interval, self.limit, self.timeout = (tk.StringVar(value=v) for v in ('1', '100', '5'))
        self.status = tk.StringVar(value='Listo. Sin mediciones.')
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='MEC / Cloud', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Tiempo de respuesta HTTP · GET /api/iot/health', foreground=MUTED).pack(anchor='w', pady=(0, 12))
        config = ttk.Frame(outer)
        config.pack(fill='x')
        config.columnconfigure(1, weight=1)
        for i, d in enumerate(('MEC', 'Cloud')):
            ttk.Label(config, text=d, foreground=COLORS[d]).grid(row=i, column=0, sticky='w', padx=(0, 12), pady=3)
            entry = ttk.Entry(config, textvariable=self.urls[d])
            entry.grid(row=i, column=1, sticky='ew', pady=3)
            self.controls.append(entry)
        options = ttk.Frame(outer)
        options.pack(fill='x', pady=10)
        for col, (label, variable) in enumerate((('Intervalo (s)', self.interval), ('Timeout (s)', self.timeout), ('Límite / destino', self.limit))):
            ttk.Label(options, text=label).grid(row=0, column=col*2, padx=(0, 6))
            entry = ttk.Entry(options, textvariable=variable, width=7)
            entry.grid(row=0, column=col*2+1, padx=(0, 16))
            self.controls.append(entry)
        ttk.Label(options, text='Condición').grid(row=0, column=6, padx=(0, 6))
        self.combo = ttk.Combobox(options, values=('Base', 'Cloud degradado', 'Recuperado'), textvariable=self.condition, state='readonly', width=18)
        self.combo.grid(row=0, column=7)
        self.combo.bind('<<ComboboxSelected>>', self.change_condition)
        ttk.Label(outer, text='“Cloud degradado” solo etiqueta la prueba; la app no activa ni verifica tc/netem.', foreground=MUTED).pack(anchor='w')
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=12)
        self.start_button = ttk.Button(buttons, text='Iniciar', command=self.start)
        self.start_button.pack(side='left', padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text='Detener', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        ttk.Button(buttons, text='Nueva sesión', command=self.new_session).pack(side='left', padx=8)
        ttk.Button(buttons, text='Exportar CSV', command=self.export).pack(side='right')
        self.session_label = ttk.Label(outer, foreground=MUTED)
        self.session_label.pack(anchor='w')
        panels = ttk.Frame(outer)
        panels.pack(fill='x', pady=10)
        panels.columnconfigure((0, 1), weight=1, uniform='panels')
        self.metrics, self.errors = {}, {}
        for col, d in enumerate(('MEC', 'Cloud')):
            panel = ttk.Frame(panels, style='Panel.TFrame', padding=14)
            panel.grid(row=0, column=col, sticky='nsew', padx=(0, 6) if col == 0 else (6, 0))
            ttk.Label(panel, text=d, foreground=COLORS[d], font=('Segoe UI', 16, 'bold'), style='Panel.TLabel').pack(anchor='w')
            self.metrics[d] = ttk.Label(panel, style='Panel.TLabel', justify='left')
            self.metrics[d].pack(anchor='w', pady=6)
            self.errors[d] = ttk.Label(panel, style='Panel.TLabel', foreground='#ffb6ac', wraplength=360)
            self.errors[d].pack(anchor='w')
        self.difference = ttk.Label(outer, font=('Segoe UI', 11, 'bold'))
        self.difference.pack(anchor='w', pady=(0, 8))
        self.canvas = tk.Canvas(outer, background=PANEL, highlightthickness=0, height=220)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        ttk.Label(outer, text='Líneas: respuestas correctas. ×: fallo en banda separada, sin valor de tiempo. Gráfica de la serie actual.', foreground=MUTED).pack(anchor='w', pady=(6, 0))
        ttk.Label(outer, textvariable=self.status, wraplength=1000).pack(anchor='w', pady=(8, 0))
        ttk.Label(outer, text='Duración = conexión + solicitud + lectura completa del cuerpo. Las estadísticas excluyen todos los fallos.', foreground=MUTED).pack(anchor='w')
        self.power = PowerMonitor(self, self.on_suspend)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.after(60, self.poll)

    def selected_samples(self, dest=None):
        return [s for s in self.samples if s.condicion == self.active_condition and (dest is None or s.destino == dest)]

    def start(self):
        if self.runner:
            return
        try:
            urls = {d: v.get().strip() for d, v in self.urls.items()}
            for url in urls.values():
                validate_url(url)
            interval, timeout, limit = float(self.interval.get()), float(self.timeout.get()), int(self.limit.get())
            import math
            if not all(math.isfinite(x) and x > 0 for x in (interval, timeout)) or limit < 1:
                raise ValueError('Intervalo y timeout deben ser positivos y finitos; límite entero ≥ 1.')
        except ValueError as exc:
            messagebox.showerror('Configuración inválida', str(exc))
            return
        counts = {d: sum(s.destino == d for s in self.samples) for d in urls}
        if all(n >= limit for n in counts.values()):
            self.status.set('Límite de sesión alcanzado. Aumente el límite o cree una nueva sesión.')
            return
        # Changing endpoints must not mix statistics with the previous endpoints.
        if self.samples and any(s.url != urls[s.destino] for s in self.selected_samples()):
            self.segment += 1
            self.active_condition = f'{self.condition.get()} · serie {self.segment}'
        self.runner = Runner(self.session_id, self.active_condition, urls, interval, limit, timeout,
                             self.out, self.round_no, counts)
        self.runner.thread.start()
        self.set_running(True)
        self.status.set('Midiendo desde esta laptop. Cada petición usa una conexión TCP nueva.')
        self.refresh()

    def set_running(self, value):
        self.start_button.configure(state='disabled' if value else 'normal')
        self.stop_button.configure(state='normal' if value else 'disabled')
        for control in self.controls:
            control.configure(state='disabled' if value else 'normal')

    def stop(self):
        if self.runner:
            self.runner.stop.set()
            self.stop_button.configure(state='disabled')
            self.status.set('Deteniendo: el intento en curso puede terminar hasta su timeout.')

    def change_condition(self, event=None):
        if self.runner:
            self.pending_condition = True
            self.combo.configure(state='disabled')
            self.stop()
        else:
            self.apply_condition()

    def apply_condition(self):
        self.segment += 1
        self.active_condition = f'{self.condition.get()} · serie {self.segment}'
        self.status.set('Nueva serie estadística. Pulse Iniciar para medir esta condición.')
        self.refresh()

    def new_session(self):
        if (self.samples or self.runner) and not messagebox.askyesno('Nueva sesión', '¿Descartar la sesión actual? Exporte el CSV antes si desea conservarla.'):
            return
        if self.runner:
            self.runner.stop.set()
        self.session_id = str(uuid.uuid4())
        self.samples.clear()
        self.round_no, self.segment = 0, 1
        self.active_condition = f'{self.condition.get()} · serie 1'
        self.pending_condition = False
        self.status.set('Nueva sesión lista.' if not self.runner else 'Nueva sesión creada. Esperando finalizar el intento anterior.')
        self.refresh()

    def on_suspend(self):
        if self.runner:
            self.runner.suspended.set()
            self.runner.stop.set()
        self.status.set('Pausa por suspensión/reanudación de Windows. Pulse Iniciar cuando la red esté disponible.')

    def poll(self):
        try:
            while True:
                kind, runner, payload = self.out.get_nowait()
                if kind == 'sample' and runner.session_id == self.session_id:
                    self.samples.append(payload)
                    self.round_no = max(self.round_no, payload.ronda)
                elif kind == 'error' and runner.session_id == self.session_id:
                    self.status.set('Error del trabajador: ' + payload)
                elif kind == 'done' and self.runner is runner:
                    self.runner = None
                    self.set_running(False)
                    self.combo.configure(state='readonly')
                    if self.pending_condition:
                        self.pending_condition = False
                        self.apply_condition()
                    elif not runner.suspended.is_set():
                        self.status.set('Detenido. Mediciones conservadas para exportar.')
                self.refresh()
        except queue.Empty:
            pass
        self.after(60, self.poll)

    def refresh(self):
        self.session_label.configure(text=f'Sesión {self.session_id[:8]} · {self.active_condition} · {len(self.samples)} intentos conservados')
        stats = {}
        fmt = lambda v: '—' if v is None else f'{v:.2f} ms'
        for d in ('MEC', 'Cloud'):
            samples = self.selected_samples(d)
            st = stats[d] = summary(samples)
            last = samples[-1] if samples else None
            last_text = fmt(last.duracion_ms) if last else '—'
            if last and last.resultado != 'correcto':
                last_text += ' (intento fallido)'
            self.metrics[d].configure(text=f'Último tiempo HTTP: {last_text}\nMediana: {fmt(st["mediana"])}     P95: {fmt(st["p95"])}\nMínimo: {fmt(st["minimo"])}     Máximo: {fmt(st["maximo"])}\nCorrectas: {st["correctas"]}    Fallidas: {st["fallidas"]}    Muestras: {st["muestras"]}')
            last_error = next((s for s in reversed(samples) if s.resultado != 'correcto'), None)
            self.errors[d].configure(text=('Último fallo: ' + last_error.resultado + ' · ' + last_error.detalle_error) if last_error else 'Sin fallos registrados en esta serie.')
        a, b = stats['MEC']['mediana'], stats['Cloud']['mediana']
        self.difference.configure(text=f'Diferencia de medianas (Cloud − MEC): {b-a:+.2f} ms' if a is not None and b is not None else 'Diferencia de medianas: pendiente de respuestas correctas de ambos destinos.')
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 100:
            return
        left, right, top, bottom = 70, w-24, 34, h-68
        data = self.selected_samples()
        good = [s.duracion_ms for s in data if s.resultado == 'correcto']
        ymax = max(good, default=1) * 1.15 or 1
        rounds = [s.ronda for s in data]
        first, last = min(rounds, default=1), max(rounds, default=2)
        x = lambda r: left + (r-first) / max(1, last-first) * (right-left)
        y = lambda v: bottom - v/ymax*(bottom-top)
        for i in range(5):
            val = ymax*i/4
            yy = y(val)
            c.create_line(left, yy, right, yy, fill='#304056')
            c.create_text(left-8, yy, text=f'{val:.1f}', anchor='e', fill=MUTED)
        c.create_text(10, 13, text='ms', anchor='w', fill=MUTED)
        c.create_text(right, h-8, text='Ronda (orden temporal)', anchor='e', fill=MUTED)
        for i in range(5):
            r = first + (last-first)*i/4
            c.create_text(x(r), bottom+14, text=f'{r:g}', fill=MUTED)
        for j, dest in enumerate(('MEC', 'Cloud')):
            color = COLORS[dest]
            c.create_text(left+j*160, 14, text=f'● {dest}', anchor='w', fill=color)
            previous = None
            for s in (s for s in data if s.destino == dest):
                xx = x(s.ronda)
                if s.resultado == 'correcto':
                    yy = y(s.duracion_ms)
                    if previous:
                        c.create_line(*previous, xx, yy, fill=color, width=2)
                    c.create_oval(xx-3, yy-3, xx+3, yy+3, fill=color, outline='')
                    previous = (xx, yy)
                else:
                    previous = None
                    yy = bottom + 31 + j*13
                    c.create_line(xx-4, yy-4, xx+4, yy+4, fill=color, width=2)
                    c.create_line(xx-4, yy+4, xx+4, yy-4, fill=color, width=2)
        c.create_text(left-8, bottom+35, text='Fallos', anchor='e', fill='#ffb6ac')
        if not data:
            c.create_text((left+right)/2, (top+bottom)/2, text='Sin mediciones en esta serie', fill=MUTED)

    def export(self):
        path = filedialog.asksaveasfilename(title='Exportar todos los intentos de la sesión', defaultextension='.csv',
                                          filetypes=[('CSV', '*.csv')], initialfile=f'mec_cloud_{self.session_id[:8]}.csv')
        if not path:
            return
        try:
            try:
                export_csv(path, self.samples)
            except FileExistsError:
                if not messagebox.askyesno('Archivo existente', '¿Sobrescribir este archivo CSV?\n' + path):
                    return
                export_csv(path, self.samples, overwrite=True)
        except OSError as exc:
            messagebox.showerror('No se pudo exportar', str(exc))
        else:
            self.status.set(f'CSV exportado: {len(self.samples)} intentos. Duraciones en ms; solo resultado=correcto entra en estadísticas.')

    def close(self):
        if self.runner:
            self.runner.stop.set()
        self.power.close()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
