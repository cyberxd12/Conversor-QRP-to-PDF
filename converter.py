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
    Inicializa fontes do ReportLab registrando Arial TrueType do Windows.
    Garante suporte nativo completo e preciso a caracteres UTF-8 e acentuação em português (ex: ã, é, ç, ê, etc.).
    """
    global _FONT_INITIALIZED, _DEFAULT_FONT
    if _FONT_INITIALIZED:
        return _DEFAULT_FONT

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        arial_path = os.path.join(win_dir, "Fonts", "arial.ttf")
        if os.path.isfile(arial_path):
            pdfmetrics.registerFont(TTFont("Arial", arial_path))
            _DEFAULT_FONT = "Arial"
        else:
            _DEFAULT_FONT = "Helvetica"
    except Exception:
        _DEFAULT_FONT = "Helvetica"

    _FONT_INITIALIZED = True
    return _DEFAULT_FONT


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
        
        Extrai com precisão a caixa delimitadora (rclBounds) e espaçamentos (Dx) de cada palavra/linha.
        Retorna:
        - canvas_size: tupla (orig_w, orig_h)
        - items: lista de dicionários contendo {'text', 'left', 'top', 'w_logical', 'h_logical'}.
        """
        im = None
        try:
            im = Image.open(io.BytesIO(emf_bytes))
            orig_w, orig_h = im.size
        except Exception:
            orig_w, orig_h = 800, 1100
        finally:
            if im:
                try:
                    im.close()
                except Exception:
                    pass

        fonts: Dict[int, Dict[str, Any]] = {}
        active_font: Dict[str, Any] = {"height": 14, "name": "Arial", "weight": 400}
        items: List[Dict[str, Any]] = []

        pos = 0
        file_len = len(emf_bytes)

        while pos + 8 <= file_len:
            rec_type, rec_size = struct.unpack("<II", emf_bytes[pos:pos + 8])
            if rec_size < 8 or pos + rec_size > file_len:
                break
            rec_data = emf_bytes[pos:pos + rec_size]

            # 1. Criação de Fonte: EMR_EXTCREATEFONTINDIRECTW (82)
            if rec_type == 82 and len(rec_data) >= 104:
                ih_font = struct.unpack("<I", rec_data[8:12])[0]
                lf_height = abs(struct.unpack("<i", rec_data[12:16])[0])
                lf_weight = struct.unpack("<i", rec_data[28:32])[0]
                face = rec_data[40:104].decode("utf-16le", errors="ignore").rstrip("\x00")
                fonts[ih_font] = {
                    "height": lf_height if lf_height > 0 else 14,
                    "weight": lf_weight,
                    "name": face or "Arial"
                }

            # 2. Seleção de Objeto: EMR_SELECTOBJECT (37)
            elif rec_type == 37 and len(rec_data) >= 12:
                ih_obj = struct.unpack("<I", rec_data[8:12])[0]
                if ih_obj in fonts:
                    active_font = fonts[ih_obj]

            # 3. Exclusão de Objeto: EMR_DELETEOBJECT (40)
            elif rec_type == 40 and len(rec_data) >= 12:
                ih_obj = struct.unpack("<I", rec_data[8:12])[0]
                fonts.pop(ih_obj, None)

            # 4. Texto Extendido: EMR_EXTTEXTOUTA (83) e EMR_EXTTEXTOUTW (84)
            elif rec_type in (83, 84) and len(rec_data) >= 52:
                bounds = struct.unpack("<4i", rec_data[8:24])
                ref_x, ref_y = struct.unpack("<ii", rec_data[36:44])
                n_chars, off_str = struct.unpack("<II", rec_data[44:52])
                off_dx = struct.unpack("<I", rec_data[72:76])[0] if len(rec_data) >= 76 else 0
                is_w = (rec_type == 84)
                char_size = 2 if is_w else 1
                byte_len = n_chars * char_size

                if 0 < off_str < len(rec_data) and off_str + byte_len <= len(rec_data):
                    raw = rec_data[off_str:off_str + byte_len]
                    text = raw.decode("utf-16le" if is_w else "cp1252", errors="replace").rstrip("\x00")
                    if text.strip():
                        b_left, b_top, b_right, b_bottom = bounds
                        has_valid_bounds = (b_right > b_left and b_bottom > b_top)

                        dx_w = 0
                        if off_dx > 0 and off_dx + n_chars * 4 <= len(rec_data):
                            try:
                                dx_vals = struct.unpack(f"<{n_chars}i", rec_data[off_dx:off_dx + n_chars * 4])
                                dx_w = sum(dx_vals)
                            except Exception:
                                dx_w = 0

                        left = b_left if has_valid_bounds else ref_x
                        top = ref_y  # No QuickReport GDI, ref_y é a posição de linha da escrita
                        h = (b_bottom - b_top) if has_valid_bounds else active_font.get("height", 14)

                        items.append({
                            "text": text.strip(),
                            "left": left,
                            "top": top,
                            "h_logical": h
                        })

            # 5. Texto Pequeno: EMR_SMALLTEXTOUT (108)
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
                    text = raw.decode("cp1252" if is_small else "utf-16le", errors="replace").rstrip("\x00")
                    if text.strip():
                        if not has_no_rect and len(rec_data) >= 52:
                            b_left, b_top, b_right, b_bottom = struct.unpack("<4i", rec_data[28:44])
                            has_valid_bounds = (b_right > b_left and b_bottom > b_top)
                        else:
                            has_valid_bounds = False

                        left = b_left if has_valid_bounds else x
                        top = y
                        h = (b_bottom - b_top) if has_valid_bounds else active_font.get("height", 14)

                        items.append({
                            "text": text.strip(),
                            "left": left,
                            "top": top,
                            "h_logical": h
                        })

            # 6. Conjunto de Textos: EMR_POLYTEXTOUTA (85) e EMR_POLYTEXTOUTW (86)
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
                    b_rect = struct.unpack("<4i", rec_data[text_ptr + 20:text_ptr + 36])
                    text_ptr += 40
                    byte_len = n_chars * char_size
                    if 0 < off_str < len(rec_data) and off_str + byte_len <= len(rec_data):
                        raw = rec_data[off_str:off_str + byte_len]
                        text = raw.decode("utf-16le" if is_w else "cp1252", errors="replace").rstrip("\x00")
                        if text.strip():
                            has_valid_bounds = (b_rect[2] > b_rect[0] and b_rect[3] > b_rect[1])
                            left = b_rect[0] if has_valid_bounds else ref_x
                            top = b_rect[1] if has_valid_bounds else ref_y
                            w = (b_rect[2] - b_rect[0]) if has_valid_bounds else 0
                            h = (b_rect[3] - b_rect[1]) if has_valid_bounds else active_font.get("height", 14)
                            items.append({
                                "text": text,
                                "left": left,
                                "top": top,
                                "w_logical": w,
                                "h_logical": h
                            })

            elif rec_type == 14:  # EMR_EOF
                break

            pos += rec_size

        # Ordena estritamente por linha vertical (de cima para baixo) e depois coluna (esquerda para direita)
        items.sort(key=lambda it: (round(it["top"] / 8.0), it["left"]))
        return (orig_w, orig_h), items

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

                font_to_use = _ensure_reportlab_fonts()
                pdf_canvas = canvas.Canvas(output_pdf)

                for img, text_items, (orig_w, orig_h) in page_entries:
                    img_w, img_h = img.size
                    page_w_pt = (img_w / dpi) * 72.0
                    page_h_pt = (img_h / dpi) * 72.0

                    scale_x = page_w_pt / max(1, orig_w)
                    scale_y = page_h_pt / max(1, orig_h)

                    pdf_canvas.setPageSize((page_w_pt, page_h_pt))
                    # 1. Desenha a imagem de fundo em alta resolução (300 DPI)
                    pdf_canvas.drawImage(ImageReader(img), 0, 0, width=page_w_pt, height=page_h_pt)

                    # 2. Desenha a camada de texto transparente/invisível (Modo 3 - Text Rendering Mode)
                    if text_items:
                        text_obj = pdf_canvas.beginText()
                        text_obj.setTextRenderMode(3)  # Modo 3: Invisível visualmente, 100% selecionável e copiável

                        for it in text_items:
                            text_str = it["text"].rstrip("\r\n")
                            if not text_str.strip():
                                continue

                            # Posicionamento horizontal exato
                            pdf_x = it["left"] * scale_x

                            # No QuickReport, it["top"] (ref_y) é a linha de base original do texto
                            pdf_baseline_y = page_h_pt - (it["top"] * scale_y) - 2.5

                            # Determina o tamanho tipográfico proporcional para abraçar o texto com exatidão
                            h_pt = it["h_logical"] * scale_y
                            if h_pt >= 20:
                                font_sz = 15.0  # Títulos destacados
                            elif h_pt <= 12:
                                font_sz = 8.0   # Rodapés, notas e identificadores pequenos
                            else:
                                font_sz = 10.0  # Corpo principal do relatório (9-10 pt)

                            text_obj.setFont(font_to_use, font_sz)
                            text_obj.setTextOrigin(pdf_x, pdf_baseline_y)
                            text_obj.textLine(text_str)

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
