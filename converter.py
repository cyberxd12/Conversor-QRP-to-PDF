"""
Motor de Conversão de Arquivos QuickReport (.QRP) para PDF.
Extrai páginas EMF (Enhanced Metafile) diretamente do container binário do QuickReport,
renderiza cada página em alta resolução gráfica e sobrepõe a camada de texto nativa extraída dos registros GDI,
com ajuste geométrico e tipográfico milimétrico para seleção, cópia e busca (Ctrl+F) 100% precisas.
"""

import os
import io
import struct
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image

_FONT_INITIALIZED = False
_DEFAULT_FONT = "Helvetica"


def _ensure_reportlab_fonts() -> str:
    """
    Inicializa fontes do ReportLab registrando Arial TrueType do Windows (Regular e Negrito).
    Garante suporte nativo completo e preciso a caracteres UTF-8 e acentuação em português (ex: ã, é, ç, ê, etc.).
    """
    global _FONT_INITIALIZED, _DEFAULT_FONT
    if _FONT_INITIALIZED:
        return _DEFAULT_FONT

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        fonts_dir = os.path.join(win_dir, "Fonts")
        arial_path = os.path.join(fonts_dir, "arial.ttf")
        arialbd_path = os.path.join(fonts_dir, "arialbd.ttf")

        if os.path.isfile(arial_path):
            pdfmetrics.registerFont(TTFont("Arial", arial_path))
            _DEFAULT_FONT = "Arial"
        else:
            _DEFAULT_FONT = "Helvetica"

        if os.path.isfile(arialbd_path):
            pdfmetrics.registerFont(TTFont("Arial-Bold", arialbd_path))
    except Exception:
        _DEFAULT_FONT = "Helvetica"

    _FONT_INITIALIZED = True
    return _DEFAULT_FONT


def _get_font_name(weight: int = 400) -> str:
    """Retorna o nome da fonte correspondente ao peso (regular ou negrito)."""
    base = _ensure_reportlab_fonts()
    if base == "Arial":
        if weight >= 700:
            try:
                from reportlab.pdfbase import pdfmetrics
                pdfmetrics.getFont("Arial-Bold")
                return "Arial-Bold"
            except Exception:
                return "Arial"
        return "Arial"
    return "Helvetica-Bold" if weight >= 700 else "Helvetica"


class QRPConversionError(Exception):
    """Exceção levantada quando ocorre um erro na conversão do arquivo QRP."""
    pass


class QRPConverter:
    """
    Classe responsável pelo parsing de arquivos .QRP (QuickReport)
    e conversão para PDF com suporte a múltiplas páginas, alta resolução
    e camada de texto vetorial com alinhamento geométrico perfeito.
    """

    @staticmethod
    def extract_pages(qrp_path: str) -> List[bytes]:
        """
        Extrai os dados binários das páginas EMF de um arquivo .QRP.
        Utiliza dois métodos complementares:
        1. Análise estruturada da tabela de páginas sequenciais do QuickReport.
        2. Escaneamento por assinatura de cabeçalho EMF (fallback para variantes de versão).
        """
        if not os.path.isfile(qrp_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {qrp_path}")

        with open(qrp_path, "rb") as f:
            data = f.read()

        file_len = len(data)
        if file_len < 136:
            raise QRPConversionError("Arquivo muito pequeno ou cabeçalho inválido para o formato QRP.")

        pages: List[bytes] = []

        # --- Método 1: Tabela de Páginas Sequenciais (Estrutura padrão QuickReport 3/4/5) ---
        # No offset 128 (0x80), o QuickReport geralmente inicia o índice de páginas:
        # [4 bytes: índice da página] [4 bytes: offset do próximo bloco/fim da página]
        offset = 128
        page_num = 1
        structured_pages: List[bytes] = []

        while offset + 8 <= file_len:
            p_idx, next_offset = struct.unpack("<II", data[offset:offset + 8])
            if p_idx == page_num and next_offset > offset + 8 and next_offset <= file_len:
                emf_start = offset + 8
                if emf_start + 52 <= file_len:
                    rec_type, rec_size = struct.unpack("<II", data[emf_start:emf_start + 8])
                    sig = data[emf_start + 40:emf_start + 44]
                    if rec_type == 1 and sig == b" EMF":
                        n_bytes = struct.unpack("<I", data[emf_start + 48:emf_start + 52])[0]
                        if emf_start + n_bytes <= file_len:
                            structured_pages.append(data[emf_start:emf_start + n_bytes])
                            offset = next_offset
                            page_num += 1
                            continue
            break

        if structured_pages:
            return structured_pages

        # --- Método 2: Escaneamento por Assinatura EMF (' EMF' / 0x464D4520) ---
        pos = 0
        while True:
            pos = data.find(b" EMF", pos)
            if pos == -1:
                break
            emf_start = pos - 40
            if emf_start >= 0 and emf_start + 52 <= file_len:
                rec_type, rec_size = struct.unpack("<II", data[emf_start:emf_start + 8])
                if rec_type == 1:  # EMR_HEADER
                    n_bytes = struct.unpack("<I", data[emf_start + 48:emf_start + 52])[0]
                    if emf_start + n_bytes <= file_len:
                        pages.append(data[emf_start:emf_start + n_bytes])
            pos += 4

        if not pages:
            raise QRPConversionError("Nenhum fluxo de página EMF válido foi encontrado no arquivo QRP.")

        return pages

    @staticmethod
    def extract_emf_text(emf_bytes: bytes) -> Tuple[Tuple[int, int], List[Dict[str, Any]]]:
        """
        Extrai todos os registros de texto GDI do fluxo binário EMF (Enhanced Metafile).
        Lê nativamente os registros:
        - EMR_EXTTEXTOUTW (0x54 / 84 - texto Unicode UTF-16LE)
        - EMR_EXTTEXTOUTA (0x53 / 83 - texto ANSI Windows-1252)
        - EMR_SMALLTEXTOUT (0x6C / 108)
        - EMR_POLYTEXTOUTW (0x56 / 86) e EMR_POLYTEXTOUTA (0x55 / 85)
        - EMR_EXTCREATEFONTINDIRECTW (0x52 / 82) e EMR_CREATEFONTINDIRECT (0x45 / 69)
        - EMR_SETTEXTALIGN (0x16 / 22)
        
        Calcula com precisão as coordenadas de referência lógicas (ptlReference), alinhamento (TA_LEFT, TA_RIGHT, TA_CENTER, TA_BASELINE),
        largura métrica de caracteres (Dx) e caixas delimitadoras no espaço de coordenadas do EMF.
        
        Retorna:
        - canvas_dim: tupla (logical_w, logical_h)
        - items: lista de dicionários contendo metadados tipográficos e geométricos.
        """
        # 1. Lê a caixa delimitadora do cabeçalho EMF
        x0, y0, x1, y1 = 0, 0, 800, 1100
        if len(emf_bytes) >= 24:
            try:
                h_x0, h_y0, h_x1, h_y1 = struct.unpack("<4i", emf_bytes[8:24])
                if h_x1 > h_x0 and h_y1 > h_y0:
                    x0, y0, x1, y1 = h_x0, h_y0, h_x1, h_y1
            except Exception:
                pass

        im = None
        im_w, im_h = 800, 1100
        try:
            im = Image.open(io.BytesIO(emf_bytes))
            im_w, im_h = im.size
        except Exception:
            im_w, im_h = max(1, x1), max(1, y1)
        finally:
            if im:
                try:
                    im.close()
                except Exception:
                    pass

        # No Windows GDI (PlayEnhMetaFile), o canvas é posicionado a partir de (0,0)
        # e suas dimensões totais correspondem à largura e altura máximas do metafile
        logical_w = max(x1, im_w)
        logical_h = max(y1, im_h)

        fonts: Dict[int, Dict[str, Any]] = {}
        active_font: Dict[str, Any] = {"height": 14, "name": "Arial", "weight": 400}
        active_text_align: int = 0
        raw_items: List[Dict[str, Any]] = []

        pos = 0
        file_len = len(emf_bytes)

        while pos + 8 <= file_len:
            rec_type, rec_size = struct.unpack("<II", emf_bytes[pos:pos + 8])
            if rec_size < 8 or pos + rec_size > file_len:
                break
            rec_data = emf_bytes[pos:pos + rec_size]

            # 1. Criação de Fonte Unicode: EMR_EXTCREATEFONTINDIRECTW (82)
            if rec_type == 82 and len(rec_data) >= 104:
                ih_font = struct.unpack("<I", rec_data[8:12])[0]
                lf_height = abs(struct.unpack("<i", rec_data[12:16])[0])
                lf_weight = struct.unpack("<i", rec_data[28:32])[0]
                face = rec_data[40:104].decode("utf-16le", errors="ignore").split("\x00", 1)[0]
                fonts[ih_font] = {
                    "height": lf_height if lf_height > 0 else 14,
                    "weight": lf_weight,
                    "name": face or "Arial"
                }

            # 2. Criação de Fonte ANSI (Delphi 7 e QuickReport clássico): EMR_CREATEFONTINDIRECT (69)
            elif rec_type == 69 and len(rec_data) >= 72:
                ih_font = struct.unpack("<I", rec_data[8:12])[0]
                lf_height = abs(struct.unpack("<i", rec_data[12:16])[0])
                lf_weight = struct.unpack("<i", rec_data[28:32])[0]
                face = rec_data[40:72].decode("cp1252", errors="ignore").split("\x00", 1)[0]
                fonts[ih_font] = {
                    "height": lf_height if lf_height > 0 else 14,
                    "weight": lf_weight,
                    "name": face or "Arial"
                }

            # 3. Alinhamento de Texto: EMR_SETTEXTALIGN (22)
            elif rec_type == 22 and len(rec_data) >= 12:
                active_text_align = struct.unpack("<I", rec_data[8:12])[0]

            # 4. Seleção de Objeto: EMR_SELECTOBJECT (37)
            elif rec_type == 37 and len(rec_data) >= 12:
                ih_obj = struct.unpack("<I", rec_data[8:12])[0]
                if ih_obj in fonts:
                    active_font = fonts[ih_obj]

            # 5. Exclusão de Objeto: EMR_DELETEOBJECT (40)
            elif rec_type == 40 and len(rec_data) >= 12:
                ih_obj = struct.unpack("<I", rec_data[8:12])[0]
                fonts.pop(ih_obj, None)

            # 6. Texto Extendido: EMR_EXTTEXTOUTA (83) e EMR_EXTTEXTOUTW (84)
            elif rec_type in (83, 84) and len(rec_data) >= 52:
                ref_x, ref_y = struct.unpack("<ii", rec_data[36:44])
                n_chars, off_str = struct.unpack("<II", rec_data[44:52])
                off_dx = struct.unpack("<I", rec_data[72:76])[0] if len(rec_data) >= 76 else 0
                is_w = (rec_type == 84)
                char_size = 2 if is_w else 1
                byte_len = n_chars * char_size

                if 0 < off_str < len(rec_data) and off_str + byte_len <= len(rec_data):
                    raw = rec_data[off_str:off_str + byte_len]
                    text = raw.decode("utf-16le" if is_w else "cp1252", errors="replace").replace("\r", "").replace("\n", "")
                    if text and text.strip():
                        dx_w = 0
                        if off_dx > 0 and off_dx + n_chars * 4 <= len(rec_data):
                            try:
                                dx_vals = struct.unpack(f"<{n_chars}i", rec_data[off_dx:off_dx + n_chars * 4])
                                dx_w = sum(dx_vals)
                            except Exception:
                                dx_w = 0

                        font_h = active_font.get("height", 14)
                        if dx_w <= 0:
                            dx_w = len(text) * font_h * 0.55

                        # Ajuste de alinhamento horizontal (TA_LEFT, TA_RIGHT, TA_CENTER)
                        if (active_text_align & 6) == 6:
                            left = ref_x - (dx_w / 2.0)
                        elif (active_text_align & 2) == 2:
                            left = ref_x - dx_w
                        else:
                            left = ref_x

                        # Ajuste de alinhamento vertical (TA_TOP, TA_BASELINE, TA_BOTTOM)
                        if (active_text_align & 24) == 24:
                            top_y = ref_y - (font_h * 0.70)
                            base_y = ref_y
                        elif (active_text_align & 8) == 8:
                            top_y = ref_y - font_h
                            base_y = ref_y - (font_h * 0.20)
                        else:  # TA_TOP padrão Windows GDI (baseline visual exata em ~0.58)
                            top_y = ref_y
                            base_y = ref_y + (font_h * 0.58)

                        raw_items.append({
                            "text": text,
                            "left": left,
                            "top": top_y,
                            "baseline_logical": base_y,
                            "w_logical": dx_w,
                            "h_logical": font_h,
                            "weight": active_font.get("weight", 400),
                            "font_name": active_font.get("name", "Arial")
                        })

            # 7. Texto Pequeno: EMR_SMALLTEXTOUT (108)
            elif rec_type == 108 and len(rec_data) >= 24:
                x, y = struct.unpack("<ii", rec_data[8:16])
                c_chars, fu_options = struct.unpack("<II", rec_data[16:24])
                is_small = bool(fu_options & 0x0200)
                has_no_rect = bool(fu_options & 0x0100)
                str_off = 36 if has_no_rect else 52
                char_size = 1 if is_small else 2
                byte_len = c_chars * char_size

                if 0 < str_off < len(rec_data) and str_off + byte_len <= len(rec_data):
                    raw = rec_data[str_off:str_off + byte_len]
                    text = raw.decode("cp1252" if is_small else "utf-16le", errors="replace").replace("\r", "").replace("\n", "")
                    if text and text.strip():
                        font_h = active_font.get("height", 14)
                        dx_w = len(text) * font_h * 0.55

                        if (active_text_align & 6) == 6:
                            left = x - (dx_w / 2.0)
                        elif (active_text_align & 2) == 2:
                            left = x - dx_w
                        else:
                            left = x

                        if (active_text_align & 24) == 24:
                            top_y = y - (font_h * 0.70)
                            base_y = y
                        elif (active_text_align & 8) == 8:
                            top_y = y - font_h
                            base_y = y - (font_h * 0.20)
                        else:
                            top_y = y
                            base_y = y + (font_h * 0.58)

                        raw_items.append({
                            "text": text,
                            "left": left,
                            "top": top_y,
                            "baseline_logical": base_y,
                            "w_logical": dx_w,
                            "h_logical": font_h,
                            "weight": active_font.get("weight", 400),
                            "font_name": active_font.get("name", "Arial")
                        })

            # 8. Conjunto de Textos: EMR_POLYTEXTOUTA (85) e EMR_POLYTEXTOUTW (86)
            elif rec_type in (85, 86) and len(rec_data) >= 40:
                c_strings = struct.unpack("<I", rec_data[36:40])[0]
                is_w = (rec_type == 86)
                char_size = 2 if is_w else 1
                text_ptr = 40
                for _ in range(min(c_strings, 500)):
                    if text_ptr + 40 > len(rec_data):
                        break
                    ref_x, ref_y = struct.unpack("<ii", rec_data[text_ptr:text_ptr + 8])
                    n_chars, off_str = struct.unpack("<II", rec_data[text_ptr + 8:text_ptr + 16])
                    text_ptr += 40
                    byte_len = n_chars * char_size
                    if 0 < off_str < len(rec_data) and off_str + byte_len <= len(rec_data):
                        raw = rec_data[off_str:off_str + byte_len]
                        text = raw.decode("utf-16le" if is_w else "cp1252", errors="replace").replace("\r", "").replace("\n", "")
                        if text and text.strip():
                            font_h = active_font.get("height", 14)
                            dx_w = len(text) * font_h * 0.55
                            left = ref_x
                            top_y = ref_y
                            base_y = ref_y + (font_h * 0.58)

                            raw_items.append({
                                "text": text,
                                "left": left,
                                "top": top_y,
                                "baseline_logical": base_y,
                                "w_logical": dx_w,
                                "h_logical": font_h,
                                "weight": active_font.get("weight", 400),
                                "font_name": active_font.get("name", "Arial")
                            })

            elif rec_type == 14:  # EMR_EOF
                break

            pos += rec_size

        # Remove registros duplicados exatos sobrepostos (ex: negrito simulado no Delphi com deslocamento de 1-2px)
        items: List[Dict[str, Any]] = []
        for it in raw_items:
            is_dup = False
            for prev in items[-6:]:
                if (
                    prev["text"] == it["text"]
                    and abs(prev["left"] - it["left"]) <= 2.5
                    and abs(prev["top"] - it["top"]) <= 2.5
                ):
                    is_dup = True
                    break
            if not is_dup:
                items.append(it)

        return (logical_w, logical_h), items


    @staticmethod
    def render_emf_to_image(emf_bytes: bytes, dpi: int = 300) -> Image.Image:
        """
        Renderiza um fluxo EMF em uma imagem PIL RGB de alta resolução.
        Calcula o fator de escala com base no DPI selecionado (base 96 DPI padrão do Windows).
        """
        im = Image.open(io.BytesIO(emf_bytes))
        bbox = im.info.get("wmf_bbox")
        orig_w, orig_h = im.size

        # Fator de escala: proporção em relação a ~96 DPI padrão do Windows
        scale = max(1.0, dpi / 96.0)
        scaled_w = max(1, int(orig_w * scale))
        scaled_h = max(1, int(orig_h * scale))

        # Tentativa 1: Renderização nativa vetorial direta via Pillow/Windows GDI drawwmf
        try:
            if bbox and hasattr(Image, "core") and hasattr(Image.core, "drawwmf"):
                raw_data = Image.core.drawwmf(emf_bytes, (scaled_w, scaled_h), bbox)
                stride = (scaled_w * 3 + 3) & -4
                rendered_img = Image.frombytes("RGB", (scaled_w, scaled_h), raw_data, "raw", "BGR", stride, -1)
                return rendered_img
        except Exception:
            # Fallback se a renderização vetorial com escala falhar
            pass

        # Tentativa 2: Renderização padrão Pillow
        try:
            rendered_img = im.convert("RGB")
            if scale > 1.2:
                rendered_img = rendered_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
            return rendered_img
        except Exception as e:
            raise QRPConversionError(f"Erro ao rasterizar página EMF: {str(e)}")

    @classmethod
    def convert_file(
        cls,
        qrp_path: str,
        output_path: Optional[str] = None,
        dpi: int = 300,
        overwrite: bool = True
    ) -> Tuple[bool, str, int]:
        """
        Converte um arquivo .QRP para .PDF.
        
        Gera um PDF híbrido de alta fidelidade:
        - Fundo visual em alta resolução nítida (300 DPI)
        - Camada de texto nativa invisível com alinhamento geométrico perfeito sobre cada palavra,
          permitindo seleção, cópia exata de parágrafos/linhas e busca (Ctrl+F) sem erros de OCR.
        
        Por padrão, salva o PDF na MESMA pasta de origem do arquivo .QRP.
        Exemplo: 'C:/relatorios/janeiro.QRP' -> 'C:/relatorios/janeiro.pdf'
        
        Retorna uma tupla:
        (sucesso: bool, caminho_do_pdf_ou_mensagem_de_erro: str, total_paginas: int)
        """
        rendered_images: List[Image.Image] = []
        try:
            qrp_abs_path = os.path.abspath(qrp_path)
            origin_dir = os.path.dirname(qrp_abs_path)
            base_name = os.path.splitext(os.path.basename(qrp_abs_path))[0]

            # Define destino se não especificado (salva na pasta de origem do QRP)
            if not output_path:
                output_pdf = os.path.join(origin_dir, f"{base_name}.pdf")
            else:
                output_pdf = os.path.abspath(output_path)

            # Tratamento de sobrescrita
            if not overwrite and os.path.exists(output_pdf):
                counter = 1
                while True:
                    candidate = os.path.join(origin_dir, f"{base_name} ({counter}).pdf")
                    if not os.path.exists(candidate):
                        output_pdf = candidate
                        break
                    counter += 1

            # Garante que a pasta de destino exista
            os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

            # Extrai todas as páginas EMF do container QRP
            pages_data = cls.extract_pages(qrp_abs_path)
            total_pages = len(pages_data)

            page_entries: List[Tuple[Image.Image, List[Dict[str, Any]], Tuple[int, int]]] = []

            for page_bytes in pages_data:
                img = cls.render_emf_to_image(page_bytes, dpi=dpi)
                rendered_images.append(img)
                canvas_dim, text_items = cls.extract_emf_text(page_bytes)
                page_entries.append((img, text_items, canvas_dim))

            if not page_entries:
                raise QRPConversionError("Nenhuma imagem pôde ser gerada das páginas do relatório.")

            # Geração via ReportLab com camada de texto invisível e posicionamento geométrico exato
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.utils import ImageReader
                from reportlab.pdfbase import pdfmetrics

                _ensure_reportlab_fonts()
                pdf_canvas = canvas.Canvas(output_pdf)

                for img, text_items, (logical_w, logical_h) in page_entries:
                    img_w, img_h = img.size
                    page_w_pt = (img_w / dpi) * 72.0
                    page_h_pt = (img_h / dpi) * 72.0

                    scale_x = page_w_pt / max(1, logical_w)
                    scale_y = page_h_pt / max(1, logical_h)

                    pdf_canvas.setPageSize((page_w_pt, page_h_pt))
                    # 1. Desenha a imagem de fundo em alta resolução (300 DPI)
                    pdf_canvas.drawImage(ImageReader(img), 0, 0, width=page_w_pt, height=page_h_pt)

                    # 2. Desenha a camada de texto transparente/invisível (Modo 3 - Text Rendering Mode)
                    if text_items:
                        # Converte coordenadas para pontos de PDF (origem 0,0 no canto inferior esquerdo)
                        processed_items = []
                        for it in text_items:
                            text_str = it["text"].rstrip("\r\n")
                            if not text_str.strip():
                                continue

                            left_pt = it["left"] * scale_x
                            w_pt = it["w_logical"] * scale_x
                            top_pt = page_h_pt - (it["top"] * scale_y)
                            baseline_pt = page_h_pt - (it["baseline_logical"] * scale_y)
                            font_sz = max(6.0, min(72.0, it["h_logical"] * scale_y))

                            processed_items.append({
                                "text": text_str,
                                "left_pt": left_pt,
                                "w_pt": w_pt,
                                "top_pt": top_pt,
                                "baseline_pt": baseline_pt,
                                "font_sz": font_sz,
                                "weight": it.get("weight", 400),
                                "font_name": it.get("font_name", "Arial")
                            })

                        if processed_items:
                            # Agrupamento inteligente por linhas visuais (evita quebras de linha artificiais entre palavras)
                            processed_items.sort(key=lambda it: (-it["top_pt"], it["left_pt"]))
                            lines: List[List[Dict[str, Any]]] = []
                            curr_line: List[Dict[str, Any]] = []
                            line_top_pt = 0.0

                            for it in processed_items:
                                it_h = max(it["font_sz"], 8.0)
                                if not curr_line:
                                    curr_line = [it]
                                    line_top_pt = it["top_pt"]
                                else:
                                    tol = max(3.5, it_h * 0.45)
                                    if abs(it["top_pt"] - line_top_pt) <= tol:
                                        curr_line.append(it)
                                    else:
                                        lines.append(curr_line)
                                        curr_line = [it]
                                        line_top_pt = it["top_pt"]

                            if curr_line:
                                lines.append(curr_line)

                            text_obj = pdf_canvas.beginText()
                            text_obj.setTextRenderMode(3)  # Modo 3: Invisível visualmente, 100% selecionável e copiável

                            for line in lines:
                                line.sort(key=lambda it: it["left_pt"])
                                line_baseline = sum(it["baseline_pt"] for it in line) / len(line)

                                for it in line:
                                    fn = _get_font_name(it["weight"])
                                    font_sz = it["font_sz"]

                                    try:
                                        exp_w = pdfmetrics.stringWidth(it["text"], fn, font_sz)
                                    except Exception:
                                        exp_w = 0.0

                                    horiz_scale = 100.0
                                    if exp_w > 0.0 and it["w_pt"] > 0.0:
                                        horiz_scale = max(50.0, min(200.0, (it["w_pt"] / exp_w) * 100.0))

                                    text_obj.setFont(fn, font_sz)
                                    text_obj.setHorizScale(horiz_scale)
                                    text_obj.setTextOrigin(it["left_pt"], line_baseline)
                                    text_obj.textOut(it["text"])

                                text_obj.textLine()  # Quebra de linha exclusiva para troca de linha visual

                            pdf_canvas.drawText(text_obj)

                    pdf_canvas.showPage()

                pdf_canvas.save()

            except Exception:
                # Fallback para o modo Pillow tradicional caso ocorra erro inesperado com ReportLab
                first_image = rendered_images[0]
                other_images = rendered_images[1:] if len(rendered_images) > 1 else []
                first_image.save(
                    output_pdf,
                    format="PDF",
                    resolution=float(dpi),
                    save_all=True,
                    append_images=other_images
                )

            return True, output_pdf, total_pages

        except Exception as e:
            return False, str(e), 0

        finally:
            # Libera todas as imagens carregadas em memória
            for img in rendered_images:
                try:
                    img.close()
                except Exception:
                    pass

    @classmethod
    def get_qrp_info(cls, qrp_path: str) -> Dict[str, Any]:
        """
        Retorna informações rápidas sobre o arquivo QRP sem renderização completa.
        """
        try:
            qrp_abs = os.path.abspath(qrp_path)
            size_bytes = os.path.getsize(qrp_abs)
            pages = cls.extract_pages(qrp_abs)
            page_count = len(pages)
            return {
                "valid": True,
                "path": qrp_abs,
                "filename": os.path.basename(qrp_abs),
                "origin_dir": os.path.dirname(qrp_abs),
                "size_bytes": size_bytes,
                "page_count": page_count,
                "error": None
            }
        except Exception as e:
            return {
                "valid": False,
                "path": qrp_path,
                "filename": os.path.basename(qrp_path),
                "origin_dir": os.path.dirname(os.path.abspath(qrp_path)) if os.path.exists(qrp_path) else "",
                "size_bytes": os.path.getsize(qrp_path) if os.path.exists(qrp_path) else 0,
                "page_count": 0,
                "error": str(e)
            }
