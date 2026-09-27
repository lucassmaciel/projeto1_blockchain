# diploma.py
# Gera o PDF do diploma a partir dos dados do formulário.
# O PDF NÃO vai para a blockchain: só o hash SHA-256 dele é registrado pelo contrato.
# `invariant=1` torna a geração determinística (mesmos dados -> mesmos bytes -> mesmo hash).
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


def gerar_diploma_pdf(nome, curso, carga_horaria, data_conclusao, codigo, instituicao):
    """Devolve os bytes do PDF do diploma."""
    if isinstance(data_conclusao, str):
        data_conclusao = date.fromisoformat(data_conclusao)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4), invariant=1)
    c.setTitle(f"Diploma {codigo}")
    w, h = landscape(A4)
    azul = colors.HexColor("#1f4e79")

    c.setStrokeColor(azul); c.setLineWidth(6); c.rect(25, 25, w - 50, h - 50)
    c.setLineWidth(1.5); c.rect(38, 38, w - 76, h - 76)

    c.setFillColor(azul); c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 100, "UNIVERSIDADE DO ESTADO DO AMAZONAS")
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 122, instituicao)

    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(w / 2, h - 190, "DIPLOMA")
    c.setFont("Helvetica", 15)
    c.drawCentredString(w / 2, h - 250, "Conferimos a")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w / 2, h - 285, nome)
    c.setFont("Helvetica", 15)
    c.drawCentredString(w / 2, h - 325, f"o grau de Bacharel em {curso},")
    c.drawCentredString(w / 2, h - 348, f"com carga horária total de {carga_horaria} horas, "
                                        f"concluído em {data_conclusao.strftime('%d/%m/%Y')}.")

    c.setFont("Helvetica", 10); c.setFillColor(colors.HexColor("#555555"))
    c.drawString(60, 70, f"Código de verificação: {codigo}")
    c.drawString(60, 56, "Autenticidade verificável na blockchain CertChain UEA (hash SHA-256 deste arquivo).")
    c.drawRightString(w - 60, 70, "Documento de demonstração — sem validade real")
    c.save()
    return buffer.getvalue()
