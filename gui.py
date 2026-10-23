"""
Interface Gráfica Desktop em CustomTkinter para Conversão em Massa de QRP para PDF.
Salva automaticamente os arquivos convertidos na pasta de origem do QRP.
"""

import os
import sys
import queue
import threading
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from converter import QRPConverter


# Configurações de Aparência do CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class QRPConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configurações da Janela Principal
        self.title("Conversor QRP para PDF em Massa")
        self.geometry("1060x720")
        self.minsize(920, 600)

        # Fila Thread-Safe de Mensagens entre Worker Thread e Main Loop
        self.msg_queue: queue.Queue = queue.Queue()

        # Estado da Aplicação
        self.files_queue: List[Dict[str, Any]] = []
        self.is_converting: bool = False
        self.cancel_requested: bool = False
        self.row_widgets: Dict[str, Dict[str, Any]] = {}

        # Opções de Configuração
        self.var_dpi = ctk.StringVar(value="300")
        self.var_overwrite = ctk.BooleanVar(value=True)
        self.var_subfolders = ctk.BooleanVar(value=True)
        self.var_theme = ctk.StringVar(value="Escuro")

        # Construção da Interface
        self._build_header()
        self._build_toolbar()
        self._build_stats_and_progress()
        self._build_main_tabs()

        # Inicia o poller thread-safe de mensagens da interface
        self._start_queue_poller()

        # Atualiza a interface inicial
        self._update_stats()
        self._render_file_list()

    # ==========================================
    # POLLER DE MENSAGENS THREAD-SAFE
    # ==========================================

    def _start_queue_poller(self):
        """
        Escuta eventos emitidos pela thread de conversão e atualiza a interface
        exclusivamente na thread principal do Tkinter (compatibilidade total com Python 3.10-3.14).
        """
        def poll():
            try:
                while True:
                    msg_type, data = self.msg_queue.get_nowait()
                    if msg_type == "log":
                        self._log(data)
                    elif msg_type == "row_state":
                        self._update_row_state(data)
                    elif msg_type == "stats":
                        self._update_stats()
                    elif msg_type == "progress_status":
                        self.lbl_progress_status.configure(text=data)
                    elif msg_type == "finished":
                        completed, errors = data
                        self._on_conversion_finished(completed, errors)
                    self.msg_queue.task_done()
            except queue.Empty:
                pass
            except Exception:
                pass
            self.after(40, poll)

        self.after(40, poll)

    # ==========================================
    # CONSTRUÇÃO DOS COMPONENTES DA INTERFACE
    # ==========================================

    def _build_header(self):
        """Cabeçalho superior com título, badge e seletores rápidos."""
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#181a20"))
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Título e Subtítulo
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=12)

        title_row = ctk.CTkFrame(title_box, fg_color="transparent")
        title_row.pack(anchor="w")

        title_label = ctk.CTkLabel(
            title_row,
            text="Conversor QRP para PDF",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left")

        badge = ctk.CTkLabel(
            title_row,
            text="PRO v1.0",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#2563eb", "#1d4ed8"),
            text_color="white",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge.pack(side="left", padx=(10, 0))

        subtitle_label = ctk.CTkLabel(
            title_box,
            text="Conversão em massa de relatórios QuickReport com salvamento automático na pasta de origem",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60")
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Configurações rápidas no lado direito
        controls_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_box.pack(side="right", padx=16, pady=12)

        # Seletor de Resolução / DPI
        dpi_label = ctk.CTkLabel(controls_box, text="Resolução:", font=ctk.CTkFont(size=12, weight="bold"))
        dpi_label.pack(side="left", padx=(0, 6))

        self.dpi_menu = ctk.CTkOptionMenu(
            controls_box,
            values=["300 DPI (Alta Qualidade)", "200 DPI (Equilibrado)", "150 DPI (Rápido)"],
            command=self._on_dpi_changed,
            width=180,
            dynamic_resizing=False
        )
        self.dpi_menu.set("300 DPI (Alta Qualidade)")
        self.dpi_menu.pack(side="left", padx=(0, 14))

        # Alternador de Tema (Escuro / Claro)
        theme_btn = ctk.CTkSegmentedButton(
            controls_box,
            values=["Escuro", "Claro"],
            command=self._on_theme_toggle,
            width=130
        )
        theme_btn.set("Escuro")
        theme_btn.pack(side="left")

    def _build_toolbar(self):
        """Barra de ferramentas de ação: Adicionar Arquivos, Pastas e Iniciar."""
        toolbar_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#181a20"))
        toolbar_frame.pack(fill="x", padx=16, pady=6)

        inner = ctk.CTkFrame(toolbar_frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # Botão Adicionar Arquivos
        self.btn_add_files = ctk.CTkButton(
            inner,
            text="➕ Adicionar Arquivos (.QRP)",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.action_add_files,
            height=36,
            fg_color=("#3b82f6", "#2563eb"),
            hover_color=("#1d4ed8", "#1e40af")
        )
        self.btn_add_files.pack(side="left", padx=(0, 8))

        # Botão Adicionar Pasta
        self.btn_add_folder = ctk.CTkButton(
            inner,
            text="📁 Adicionar Pasta",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.action_add_folder,
            height=36,
            fg_color=("gray75", "#2b2f3a"),
            hover_color=("gray65", "#3a404e"),
            text_color=("gray10", "white")
        )
        self.btn_add_folder.pack(side="left", padx=(0, 8))

        # Checkbox Subpastas
        self.chk_subfolders = ctk.CTkCheckBox(
            inner,
            text="Incluir subpastas",
            variable=self.var_subfolders,
            font=ctk.CTkFont(size=12)
        )
        self.chk_subfolders.pack(side="left", padx=(4, 12))

        # Checkbox Sobrescrever
        self.chk_overwrite = ctk.CTkCheckBox(
            inner,
            text="Sobrescrever existentes",
            variable=self.var_overwrite,
            font=ctk.CTkFont(size=12)
        )
        self.chk_overwrite.pack(side="left", padx=(0, 16))

        # Botão Limpar Fila
        self.btn_clear = ctk.CTkButton(
            inner,
            text="🗑️ Limpar Lista",
            font=ctk.CTkFont(size=12),
            command=self.action_clear_queue,
            height=36,
            width=100,
            fg_color=("gray80", "#2a2d36"),
            hover_color=("gray70", "#383c48"),
            text_color=("gray20", "gray70")
        )
        self.btn_clear.pack(side="left")

        # Botão de Conversão Principal (Lado Direito)
        self.btn_convert = ctk.CTkButton(
            inner,
            text="⚡ Iniciar Conversão em Massa",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.action_start_conversion,
            height=38,
            width=220,
            fg_color=("#10b981", "#059669"),
            hover_color=("#059669", "#047857"),
            text_color="white"
        )
        self.btn_convert.pack(side="right")

        # Botão de Cancelamento (inicialmente oculto)
        self.btn_cancel = ctk.CTkButton(
            inner,
            text="⏹ Cancelar",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.action_cancel_conversion,
            height=38,
            width=120,
            fg_color=("#ef4444", "#dc2626"),
            hover_color=("#dc2626", "#b91c1c"),
            text_color="white"
        )

    def _build_stats_and_progress(self):
        """Painel de estatísticas rápidas e barra de progresso."""
        stats_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#181a20"))
        stats_frame.pack(fill="x", padx=16, pady=6)

        inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        # Contadores em linha
        cards_box = ctk.CTkFrame(inner, fg_color="transparent")
        cards_box.pack(fill="x", pady=(0, 8))

        self.lbl_stat_total = self._create_stat_badge(cards_box, "Total:", "0", "#3b82f6")
        self.lbl_stat_pending = self._create_stat_badge(cards_box, "Pendentes:", "0", "gray")
        self.lbl_stat_completed = self._create_stat_badge(cards_box, "Concluídos:", "0", "#10b981")
        self.lbl_stat_errors = self._create_stat_badge(cards_box, "Erros:", "0", "#ef4444")

        # Status text e percentual
        status_box = ctk.CTkFrame(inner, fg_color="transparent")
        status_box.pack(fill="x", pady=(0, 4))

        self.lbl_progress_status = ctk.CTkLabel(
            status_box,
            text="Adicione arquivos .QRP ou pastas para iniciar.",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70")
        )
        self.lbl_progress_status.pack(side="left")

        self.lbl_progress_pct = ctk.CTkLabel(
            status_box,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray20", "gray80")
        )
        self.lbl_progress_pct.pack(side="right")

        # Barra de Progresso
        self.progress_bar = ctk.CTkProgressBar(inner, height=10, corner_radius=5)
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0.0)

    def _create_stat_badge(self, parent, label_text: str, value_text: str, color: str):
        badge_frame = ctk.CTkFrame(parent, fg_color=("gray85", "#20232a"), corner_radius=6)
        badge_frame.pack(side="left", padx=(0, 10))

        lbl = ctk.CTkLabel(badge_frame, text=label_text, font=ctk.CTkFont(size=12), text_color=("gray30", "gray60"))
        lbl.pack(side="left", padx=(8, 4), pady=4)

        val = ctk.CTkLabel(badge_frame, text=value_text, font=ctk.CTkFont(size=13, weight="bold"), text_color=color)
        val.pack(side="left", padx=(0, 8), pady=4)
        return val

    def _build_main_tabs(self):
        """Área central com abas: Fila de Arquivos e Log de Execução."""
        self.tabview = ctk.CTkTabview(self, corner_radius=10, fg_color=("gray90", "#181a20"))
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(6, 16))

        self.tab_queue = self.tabview.add("📋 Fila de Arquivos")
        self.tab_log = self.tabview.add("📜 Log de Execução")

        # --- Aba 1: Fila de Arquivos ---
        # Cabeçalho da Lista
        list_header = ctk.CTkFrame(self.tab_queue, fg_color=("gray85", "#20232a"), height=32, corner_radius=6)
        list_header.pack(fill="x", padx=6, pady=(4, 6))

        h_status = ctk.CTkLabel(list_header, text="Status", width=100, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        h_status.pack(side="left", padx=(12, 4))

        h_name = ctk.CTkLabel(list_header, text="Arquivo QRP", width=220, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        h_name.pack(side="left", padx=4)

        h_folder = ctk.CTkLabel(list_header, text="Pasta de Origem (Destino do PDF)", anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        h_folder.pack(side="left", fill="x", expand=True, padx=4)

        h_size = ctk.CTkLabel(list_header, text="Tamanho / Pág", width=120, anchor="center", font=ctk.CTkFont(size=12, weight="bold"))
        h_size.pack(side="left", padx=4)

        h_actions = ctk.CTkLabel(list_header, text="Ações", width=180, anchor="center", font=ctk.CTkFont(size=12, weight="bold"))
        h_actions.pack(side="right", padx=(4, 12))

        # Lista com rolagem
        self.scroll_files = ctk.CTkScrollableFrame(
            self.tab_queue,
            fg_color="transparent",
            corner_radius=6
        )
        self.scroll_files.pack(fill="both", expand=True, padx=4, pady=2)

        # Placeholder para lista vazia
        self.empty_placeholder = ctk.CTkFrame(self.scroll_files, fg_color="transparent")
        lbl_empty_icon = ctk.CTkLabel(
            self.empty_placeholder,
            text="📄",
            font=ctk.CTkFont(size=48)
        )
        lbl_empty_icon.pack(pady=(50, 8))

        lbl_empty_title = ctk.CTkLabel(
            self.empty_placeholder,
            text="Nenhum arquivo QRP na fila",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        lbl_empty_title.pack(pady=(0, 4))

        lbl_empty_sub = ctk.CTkLabel(
            self.empty_placeholder,
            text="Clique em 'Adicionar Arquivos (.QRP)' ou 'Adicionar Pasta' para carregar arquivos em massa.\nCada PDF convertido será salvo na mesma pasta de origem do seu respectivo arquivo QRP.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            justify="center"
        )
        lbl_empty_sub.pack()

        # --- Aba 2: Log de Execução ---
        log_toolbar = ctk.CTkFrame(self.tab_log, fg_color="transparent")
        log_toolbar.pack(fill="x", padx=6, pady=(4, 6))

        btn_copy_log = ctk.CTkButton(
            log_toolbar,
            text="📋 Copiar Log",
            width=110,
            height=28,
            font=ctk.CTkFont(size=11),
            command=self._action_copy_log
        )
        btn_copy_log.pack(side="left", padx=(0, 8))

        btn_clear_log = ctk.CTkButton(
            log_toolbar,
            text="🗑️ Limpar Log",
            width=110,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#2a2d36"),
            hover_color=("gray65", "#383c48"),
            command=self._action_clear_log
        )
        btn_clear_log.pack(side="left")

        self.txt_log = ctk.CTkTextbox(
            self.tab_log,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=6
        )
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self._log("Sistema iniciado. Pronto para converter arquivos QRP para PDF.")

    # ==========================================
    # LOG E UTILITÁRIOS
    # ==========================================

    def _log(self, message: str):
        """Registra mensagem com carimbo de data/hora no console da aplicação."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", log_entry)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _action_copy_log(self):
        text = self.txt_log.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Log", "Log copiado para a área de transferência!")

    def _action_clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")
        self._log("Log limpo.")

    def _on_theme_toggle(self, value):
        if value == "Escuro":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")

    def _on_dpi_changed(self, value):
        if "300" in value:
            self.var_dpi.set("300")
        elif "200" in value:
            self.var_dpi.set("200")
        else:
            self.var_dpi.set("150")
        self._log(f"Resolução alterada para {self.var_dpi.get()} DPI.")

    def _format_size(self, size_bytes: int) -> str:
        """Formata tamanho de bytes para KB ou MB de forma amigável."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

    # ==========================================
    # GERENCIAMENTO DA FILA DE ARQUIVOS
    # ==========================================

    def action_add_files(self):
        """Abre diálogo para selecionar múltiplos arquivos .QRP."""
        files = filedialog.askopenfilenames(
            title="Selecionar Arquivos QuickReport (.QRP)",
            filetypes=[
                ("Arquivos QuickReport (*.qrp;*.QRP)", "*.qrp;*.QRP"),
                ("Todos os arquivos (*.*)", "*.*")
            ]
        )
        if not files:
            return

        added_count = self._add_filepaths_to_queue(files)
        self._log(f"Adicionados {added_count} arquivo(s) à fila.")
        self._update_stats()
        self._render_file_list()

    def action_add_folder(self):
        """Abre diálogo para selecionar uma pasta e varre arquivos .QRP."""
        folder = filedialog.askdirectory(title="Selecionar Pasta com Arquivos .QRP")
        if not folder:
            return

        recursive = self.var_subfolders.get()
        found_files = []

        if recursive:
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".qrp"):
                        found_files.append(os.path.join(root, f))
        else:
            for f in os.listdir(folder):
                if f.lower().endswith(".qrp"):
                    full_p = os.path.join(folder, f)
                    if os.path.isfile(full_p):
                        found_files.append(full_p)

        if not found_files:
            messagebox.showinfo("Nenhum arquivo encontrado", f"Nenhum arquivo .QRP foi encontrado na pasta:\n{folder}")
            return

        added_count = self._add_filepaths_to_queue(found_files)
        self._log(f"Adicionados {added_count} arquivo(s) da pasta: {folder}")
        self._update_stats()
        self._render_file_list()

    def _add_filepaths_to_queue(self, paths: List[str]) -> int:
        existing_paths = {item["path"] for item in self.files_queue}
        added = 0
        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p in existing_paths or not abs_p.lower().endswith(".qrp"):
                continue

            info = QRPConverter.get_qrp_info(abs_p)
            item = {
                "path": abs_p,
                "filename": info["filename"],
                "origin_dir": info["origin_dir"],
                "size_bytes": info["size_bytes"],
                "page_count": info["page_count"],
                "status": "Pendente",
                "pdf_path": None,
                "error": info["error"]
            }
            self.files_queue.append(item)
            existing_paths.add(abs_p)
            added += 1

        return added

    def action_clear_queue(self):
        """Limpa toda a fila de arquivos (se não estiver convertendo)."""
        if self.is_converting:
            messagebox.showwarning("Aguarde", "A conversão está em andamento. Cancele antes de limpar.")
            return

        self.files_queue.clear()
        self.row_widgets.clear()
        self._update_stats()
        self._render_file_list()
        self._log("Fila de arquivos limpa.")

    def action_remove_item(self, path: str):
        """Remove um item individual da fila."""
        if self.is_converting:
            return
        self.files_queue = [item for item in self.files_queue if item["path"] != path]
        self._update_stats()
        self._render_file_list()

    def _update_stats(self):
        """Recalcula e atualiza os contadores e barra de progresso."""
        total = len(self.files_queue)
        completed = sum(1 for f in self.files_queue if f["status"] == "Concluído")
        errors = sum(1 for f in self.files_queue if f["status"] == "Erro")
        converting = sum(1 for f in self.files_queue if f["status"] == "Convertendo...")
        pending = total - completed - errors - converting

        self.lbl_stat_total.configure(text=str(total))
        self.lbl_stat_pending.configure(text=str(pending))
        self.lbl_stat_completed.configure(text=str(completed))
        self.lbl_stat_errors.configure(text=str(errors))

        if total == 0:
            pct = 0.0
            self.progress_bar.set(0.0)
            self.lbl_progress_pct.configure(text="0%")
        else:
            pct = (completed + errors) / total
            self.progress_bar.set(pct)
            self.lbl_progress_pct.configure(text=f"{int(pct * 100)}%")

    # ==========================================
    # RENDERIZAÇÃO DA TABELA DE ARQUIVOS
    # ==========================================

    def _render_file_list(self):
        """Renderiza as linhas da fila de arquivos com layout limpo e performático."""
        # Limpa widgets anteriores
        for widget in self.scroll_files.winfo_children():
            widget.destroy()
        self.row_widgets.clear()

        if not self.files_queue:
            self.empty_placeholder = ctk.CTkFrame(self.scroll_files, fg_color="transparent")
            self.empty_placeholder.pack(fill="both", expand=True)

            lbl_empty_icon = ctk.CTkLabel(self.empty_placeholder, text="📄", font=ctk.CTkFont(size=48))
            lbl_empty_icon.pack(pady=(40, 8))

            lbl_empty_title = ctk.CTkLabel(
                self.empty_placeholder,
                text="Nenhum arquivo QRP na fila",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            lbl_empty_title.pack(pady=(0, 4))

            lbl_empty_sub = ctk.CTkLabel(
                self.empty_placeholder,
                text="Clique em 'Adicionar Arquivos (.QRP)' ou 'Adicionar Pasta' para carregar arquivos em massa.\nCada PDF convertido será salvo na mesma pasta de origem do seu respectivo arquivo QRP.",
                font=ctk.CTkFont(size=12),
                text_color=("gray40", "gray60"),
                justify="center"
            )
            lbl_empty_sub.pack(pady=(0, 40))
            return

        for item in self.files_queue:
            self._create_row_widget(item)

    def _create_row_widget(self, item: Dict[str, Any]):
        path = item["path"]

        row = ctk.CTkFrame(
            self.scroll_files,
            fg_color=("white", "#1e2128"),
            corner_radius=6,
            height=40
        )
        row.pack(fill="x", pady=2)

        # Status Badge
        lbl_status = ctk.CTkLabel(
            row,
            text=self._get_status_label(item["status"]),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._get_status_color(item["status"]),
            width=100,
            anchor="w"
        )
        lbl_status.pack(side="left", padx=(12, 4))

        # Nome do Arquivo
        lbl_name = ctk.CTkLabel(
            row,
            text=item["filename"],
            font=ctk.CTkFont(size=12, weight="bold"),
            width=220,
            anchor="w"
        )
        lbl_name.pack(side="left", padx=4)

        # Pasta de Origem
        lbl_folder = ctk.CTkLabel(
            row,
            text=item["origin_dir"],
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="w"
        )
        lbl_folder.pack(side="left", fill="x", expand=True, padx=4)

        # Tamanho e Páginas
        size_str = self._format_size(item["size_bytes"])
        p_str = f"{item['page_count']} pág" if item["page_count"] > 0 else "-"
        lbl_size = ctk.CTkLabel(
            row,
            text=f"{size_str} ({p_str})",
            font=ctk.CTkFont(size=11),
            width=120,
            anchor="center",
            text_color=("gray40", "gray60")
        )
        lbl_size.pack(side="left", padx=4)

        # Caixa de Ações
        actions_box = ctk.CTkFrame(row, fg_color="transparent", width=180)
        actions_box.pack(side="right", padx=(4, 12))

        # Botão Abrir PDF
        btn_open_pdf = ctk.CTkButton(
            actions_box,
            text="Ver PDF",
            width=65,
            height=26,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#10b981", "#059669"),
            hover_color=("#059669", "#047857"),
            state="normal" if item.get("pdf_path") else "disabled",
            command=lambda p=path: self._action_open_pdf(p)
        )
        btn_open_pdf.pack(side="left", padx=2)

        # Botão Abrir Pasta
        btn_open_dir = ctk.CTkButton(
            actions_box,
            text="Pasta",
            width=55,
            height=26,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "#2b2f3a"),
            hover_color=("gray65", "#3a404e"),
            text_color=("gray20", "white"),
            command=lambda d=item["origin_dir"]: self._action_open_folder(d)
        )
        btn_open_dir.pack(side="left", padx=2)

        # Botão Remover
        btn_remove = ctk.CTkButton(
            actions_box,
            text="✕",
            width=26,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="transparent",
            hover_color=("#ef4444", "#7f1d1d"),
            text_color=("gray40", "gray60"),
            command=lambda p=path: self.action_remove_item(p)
        )
        btn_remove.pack(side="left", padx=2)

        self.row_widgets[path] = {
            "row": row,
            "status_label": lbl_status,
            "btn_pdf": btn_open_pdf,
            "btn_remove": btn_remove
        }

    def _get_status_label(self, status: str) -> str:
        icons = {
            "Pendente": "⏳ Pendente",
            "Convertendo...": "🔄 Convertendo",
            "Concluído": "✅ Concluído",
            "Erro": "❌ Erro"
        }
        return icons.get(status, status)

    def _get_status_color(self, status: str) -> str:
        colors = {
            "Pendente": ("gray40", "gray60"),
            "Convertendo...": ("#2563eb", "#3b82f6"),
            "Concluído": ("#059669", "#10b981"),
            "Erro": ("#dc2626", "#ef4444")
        }
        return colors.get(status, ("gray30", "gray70"))

    def _update_row_state(self, path: str):
        """Atualiza o estado visual de uma linha específica sem re-renderizar toda a lista."""
        item = next((x for x in self.files_queue if x["path"] == path), None)
        if not item or path not in self.row_widgets:
            return

        widgets = self.row_widgets[path]
        widgets["status_label"].configure(
            text=self._get_status_label(item["status"]),
            text_color=self._get_status_color(item["status"])
        )

        if item.get("pdf_path") and os.path.exists(item["pdf_path"]):
            widgets["btn_pdf"].configure(state="normal")
        else:
            widgets["btn_pdf"].configure(state="disabled")

    # ==========================================
    # AÇÕES DOS ARQUIVOS E PASTAS
    # ==========================================

    def _action_open_pdf(self, path: str):
        """Abre o arquivo PDF gerado no leitor padrão do Windows."""
        item = next((x for x in self.files_queue if x["path"] == path), None)
        if item and item.get("pdf_path") and os.path.exists(item["pdf_path"]):
            try:
                os.startfile(item["pdf_path"])
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o PDF: {e}")

    def _action_open_folder(self, folder_path: str):
        """Abre a pasta de origem no Windows Explorer."""
        if os.path.exists(folder_path):
            try:
                subprocess.Popen(f'explorer "{folder_path}"')
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir a pasta: {e}")

    # ==========================================
    # PROCESSO DE CONVERSÃO EM MASSA (THREAD)
    # ==========================================

    def action_start_conversion(self):
        """Inicia a conversão de todos os arquivos pendentes em uma thread em segundo plano."""
        if not self.files_queue:
            messagebox.showinfo("Fila vazia", "Por favor, adicione arquivos .QRP ou pastas antes de iniciar a conversão.")
            return

        pending_items = [item for item in self.files_queue if item["status"] != "Concluído"]
        if not pending_items:
            # Pergunta se deseja converter todos novamente
            resp = messagebox.askyesno(
                "Reiniciar Conversão",
                "Todos os arquivos já foram convertidos. Deseja reprocessar todos novamente?"
            )
            if not resp:
                return
            for item in self.files_queue:
                item["status"] = "Pendente"
                item["pdf_path"] = None
                self._update_row_state(item["path"])
            self._update_stats()

        self.is_converting = True
        self.cancel_requested = False

        # Alterna botões da interface
        self.btn_convert.pack_forget()
        self.btn_cancel.pack(side="right")
        self.btn_add_files.configure(state="disabled")
        self.btn_add_folder.configure(state="disabled")
        self.btn_clear.configure(state="disabled")

        dpi = int(self.var_dpi.get())
        overwrite = self.var_overwrite.get()

        self._log(f"Iniciando conversão em massa. DPI selecionado: {dpi}.")

        # Inicia a thread trabalhadora com parâmetros passados com segurança
        worker = threading.Thread(
            target=self._conversion_worker,
            args=(dpi, overwrite),
            daemon=True
        )
        worker.start()

    def action_cancel_conversion(self):
        """Sinaliza cancelamento da conversão."""
        if self.is_converting:
            self.cancel_requested = True
            self._log("Cancelamento solicitado pelo usuário. Aguardando conclusão do arquivo atual...")
            self.lbl_progress_status.configure(text="Cancelando conversão...")

    def _conversion_worker(self, dpi: int, overwrite: bool):
        """Função executada na thread de segundo plano para processar a fila."""
        total = len(self.files_queue)
        completed_count = 0
        error_count = 0

        for index, item in enumerate(self.files_queue):
            if self.cancel_requested:
                self.msg_queue.put(("log", "Conversão cancelada pelo usuário."))
                break

            if item["status"] == "Concluído":
                completed_count += 1
                continue

            qrp_path = item["path"]
            filename = item["filename"]

            # Atualiza status para 'Convertendo...' via fila thread-safe
            item["status"] = "Convertendo..."
            self.msg_queue.put(("row_state", qrp_path))
            self.msg_queue.put(("stats", None))
            self.msg_queue.put(("progress_status", f"Convertendo ({index + 1}/{total}): {filename}..."))

            # Executa a conversão propriamente dita
            # Salva na pasta de origem do QRP (output_path=None faz o salvamento na pasta de origem)
            success, result, page_count = QRPConverter.convert_file(
                qrp_path=qrp_path,
                output_path=None,  # Garante que salva na pasta de origem!
                dpi=dpi,
                overwrite=overwrite
            )

            if success:
                item["status"] = "Concluído"
                item["pdf_path"] = result
                item["page_count"] = page_count
                completed_count += 1
                self.msg_queue.put(("log", f"✔ Concluído: {filename} -> {os.path.basename(result)} ({page_count} pág)"))
            else:
                item["status"] = "Erro"
                item["error"] = result
                error_count += 1
                self.msg_queue.put(("log", f"✖ Erro em {filename}: {result}"))

            self.msg_queue.put(("row_state", qrp_path))
            self.msg_queue.put(("stats", None))

        # Finalização da thread via fila
        self.msg_queue.put(("finished", (completed_count, error_count)))

    def _on_conversion_finished(self, completed_count: int, error_count: int):
        """Executado na thread principal após término ou cancelamento da conversão."""
        self.is_converting = False

        # Restaura botões
        self.btn_cancel.pack_forget()
        self.btn_convert.pack(side="right")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear.configure(state="normal")

        self._update_stats()

        if self.cancel_requested:
            self.lbl_progress_status.configure(text="Conversão interrompida.")
            messagebox.showwarning(
                "Cancelado",
                f"Conversão interrompida.\nConcluídos: {completed_count}\nErros: {error_count}"
            )
        else:
            self.lbl_progress_status.configure(
                text=f"Processo finalizado! {completed_count} convertido(s) com sucesso."
            )
            self._log(f"Processamento concluído. Sucesso: {completed_count}, Erros: {error_count}.")
            messagebox.showinfo(
                "Conversão Concluída",
                f"A conversão em massa foi finalizada com sucesso!\n\n"
                f"✅ Concluídos: {completed_count}\n"
                f"❌ Erros: {error_count}\n\n"
                f"Todos os arquivos PDF foram salvos em suas respectivas pastas de origem."
            )


def main():
    app = QRPConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
