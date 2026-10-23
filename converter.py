"""
Motor de Conversão de Arquivos QuickReport (.QRP) para PDF.
Extrai páginas EMF (Enhanced Metafile) diretamente do container binário do QuickReport
e renderiza cada página em alta resolução vetorial para gerar arquivos PDF compactos e nítidos.
"""

import os
import io
import struct
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image


class QRPConversionError(Exception):
    """Exceção levantada quando ocorre um erro na conversão do arquivo QRP."""
    pass


class QRPConverter:
    """
    Classe responsável pelo parsing de arquivos .QRP (QuickReport)
    e conversão para PDF com suporte a múltiplas páginas e alta resolução.
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
    def render_emf_to_image(emf_bytes: bytes, dpi: int = 300) -> Image.Image:
        """
        Renderiza um fluxo EMF em uma imagem PIL RGB de alta resolução.
        Calcula o fator de escala com base no DPI selecionado (base 96 DPI padrão do Windows).
        """
        # Abre o cabeçalho WMF/EMF via Pillow
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
        
        Por padrão, salva o PDF na MESMA pasta de origem do arquivo .QRP.
        Exemplo: 'C:/relatorios/janeiro.QRP' -> 'C:/relatorios/janeiro.pdf'
        
        Retorna uma tupla:
        (sucesso: bool, caminho_do_pdf_ou_mensagem_de_erro: str, total_paginas: int)
        """
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

            # Extrai todas as páginas EMF
            pages_data = cls.extract_pages(qrp_abs_path)
            total_pages = len(pages_data)

            rendered_images: List[Image.Image] = []
            for page_bytes in pages_data:
                img = cls.render_emf_to_image(page_bytes, dpi=dpi)
                rendered_images.append(img)

            if not rendered_images:
                raise QRPConversionError("Nenhuma imagem pôde ser gerada das páginas do relatório.")

            # Garante que a pasta de destino exista
            os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

            # Salva como PDF de página única ou múltiplas páginas
            first_image = rendered_images[0]
            other_images = rendered_images[1:] if len(rendered_images) > 1 else []

            first_image.save(
                output_pdf,
                format="PDF",
                resolution=float(dpi),
                save_all=True,
                append_images=other_images
            )

            # Fecha as imagens da memória
            for img in rendered_images:
                img.close()

            return True, output_pdf, total_pages

        except Exception as e:
            return False, str(e), 0

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
