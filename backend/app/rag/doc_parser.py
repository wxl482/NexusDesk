import io
import csv
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def parse_csv_to_markdown(content_bytes: bytes) -> str:
    """将 CSV / TSV 文件解析为格式化 Markdown 表格，支持逗号/制表符/分号及多编码探测"""
    for enc in ["utf-8", "gbk", "gb18030", "gb2312", "utf-16"]:
        try:
            text = content_bytes.decode(enc)
            break
        except Exception:
            continue
    else:
        text = content_bytes.decode("utf-8", errors="replace")

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    # 自动探测分隔符：制表符 \t、分号 ; 还是逗号 ,
    first_line = lines[0]
    tab_count = first_line.count("\t")
    semi_count = first_line.count(";")
    comma_count = first_line.count(",")
    if tab_count > comma_count and tab_count > semi_count:
        delimiter = "\t"
    elif semi_count > comma_count and semi_count > tab_count:
        delimiter = ";"
    else:
        delimiter = ","

    reader = csv.reader(lines, delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ""

    md_lines = []
    headers = [col.strip().replace("\n", " ") for col in rows[0]]
    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for row in rows[1:]:
        padded_row = row + [""] * (len(headers) - len(row))
        clean_cols = [col.strip().replace("\n", " ").replace("|", "\\|") for col in padded_row[:len(headers)]]
        md_lines.append("| " + " | ".join(clean_cols) + " |")

    return "\n".join(md_lines)


def parse_excel_to_markdown(content_bytes: bytes) -> str:
    """将 Excel (.xlsx, .xlsm) 工作簿的所有 Sheet 解析为清晰的 Markdown 结构化表格"""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
    except Exception as e:
        err_str = str(e).lower()
        if "does not support the old .xls" in err_str or "not a zip file" in err_str:
            raise ValueError("当前支持现代 Excel 格式 (.xlsx / .xlsm)。检测到此文件可能是旧版 Excel 97-2003 (.xls) 格式，请在 Excel/WPS 中另存为 .xlsx 或 .csv 后上传。")
        raise ValueError(f"打开 Excel 文件失败: {str(e)}")

    sheets_output = []

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        # 过滤全空行
        valid_rows = []
        for r in rows:
            if any(cell is not None and str(cell).strip() != "" for cell in r):
                valid_rows.append([str(c).strip().replace("\n", " ").replace("|", "\\|") if c is not None else "" for c in r])

        if not valid_rows:
            continue

        # 找出最大列数
        max_cols = max(len(r) for r in valid_rows)
        header = valid_rows[0] + [""] * (max_cols - len(valid_rows[0]))
        # 兜底：若标题全空，使用默认列名
        header = [col if col else f"列{i+1}" for i, col in enumerate(header)]

        sheet_md = [f"### 工作表: {sheet_name}\n"]
        sheet_md.append("| " + " | ".join(header) + " |")
        sheet_md.append("| " + " | ".join(["---"] * max_cols) + " |")

        for row in valid_rows[1:]:
            padded = row + [""] * (max_cols - len(row))
            sheet_md.append("| " + " | ".join(padded) + " |")

        sheets_output.append("\n".join(sheet_md))

    return "\n\n".join(sheets_output)


def parse_docx_to_markdown(content_bytes: bytes) -> str:
    """将 Word (.docx) 文档解析为保留标题、段落与结构化表格的 Markdown 文本"""
    import docx

    try:
        doc = docx.Document(io.BytesIO(content_bytes))
    except Exception as e:
        err_str = str(e).lower()
        if "not a zip file" in err_str or "badzipfile" in err_str:
            raise ValueError("当前支持现代 Word 文档 (.docx) 格式。检测到此文件可能是旧版 Word 97-2003 (.doc) 格式，请在 Word/WPS 中另存为 .docx 后上传。")
        raise ValueError(f"打开 Word 文档失败: {str(e)}")

    parts = []

    # 提取段落内容
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style_name = p.style.name.lower() if p.style and p.style.name else ""
        if "heading 1" in style_name:
            parts.append(f"# {text}")
        elif "heading 2" in style_name:
            parts.append(f"## {text}")
        elif "heading 3" in style_name:
            parts.append(f"### {text}")
        else:
            parts.append(text)

    # 提取所有表格内容并转为 Markdown 表格
    if doc.tables:
        for idx, table in enumerate(doc.tables, 1):
            table_md = [f"\n#### [表格 {idx}]"]
            rows = table.rows
            if not rows:
                continue
            headers = [cell.text.strip().replace("\n", " ").replace("|", "\\|") for cell in rows[0].cells]
            table_md.append("| " + " | ".join(headers) + " |")
            table_md.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows[1:]:
                row_cells = [cell.text.strip().replace("\n", " ").replace("|", "\\|") for cell in row.cells]
                table_md.append("| " + " | ".join(row_cells) + " |")
            parts.append("\n".join(table_md))

    return "\n\n".join(parts)


def parse_pdf_to_markdown(content_bytes: bytes) -> str:
    """
    深度提取 PDF 页面文字，支持密码解密校验与页面布局提取
    """
    import pypdf

    try:
        reader = pypdf.PdfReader(io.BytesIO(content_bytes), strict=False)
    except Exception as e:
        raise ValueError(f"PDF 文件损坏或格式非法: {str(e)}")

    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
            if decrypted == 0:
                raise ValueError("PDF 文档已被密码加密保护，暂不支持直接解析受保护的文件。")
        except Exception as e:
            if "加密" in str(e):
                raise
            raise ValueError("PDF 文档已被密码加密，需要解密授权。")

    if len(reader.pages) == 0:
        raise ValueError("PDF 文档为空，未包含任何有效页面。")

    pages_text = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
            if not t.strip():
                # 尝试 layout 模式提取
                try:
                    t = page.extract_text(extraction_mode="layout") or ""
                except Exception:
                    pass
            if t.strip():
                pages_text.append(f"--- [PDF 第 {i+1} 页] ---\n{t.strip()}")
        except Exception:
            pass

    if not pages_text:
        raise ValueError(
            f"该 PDF 文档共 {len(reader.pages)} 页，但未提取到任何可选中的文本内容。"
            "该文件通常为图片扫描件或未嵌入标准文字图层的纯图 PDF。系统目前支持标准文字图层 PDF，扫描版建议使用 OCR 识别后上传。"
        )

    return "\n\n".join(pages_text)


def parse_document(content_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    通用多格式文档解析器：
    支持 PDF, Word (.docx), Excel (.xlsx/.xlsm), CSV/TSV, Markdown, 纯文本, 常见代码与配置文件
    """
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    doc_type = ext or "text"

    try:
        if ext == "pdf":
            text = parse_pdf_to_markdown(content_bytes)
        elif ext in ["docx", "doc"]:
            text = parse_docx_to_markdown(content_bytes)
        elif ext in ["xlsx", "xlsm", "xls"]:
            text = parse_excel_to_markdown(content_bytes)
        elif ext in ["csv", "tsv"]:
            text = parse_csv_to_markdown(content_bytes)
        else:
            # 文本、Markdown、代码文件多编码探测解码
            for enc in ["utf-8", "gbk", "gb18030", "gb2312", "utf-16"]:
                try:
                    text = content_bytes.decode(enc)
                    break
                except Exception:
                    continue
            else:
                text = content_bytes.decode("utf-8", errors="replace")

        if not text or not text.strip():
            return {
                "success": False,
                "filename": filename,
                "doc_type": doc_type,
                "error": "文档内容为空或未能提取到有效正文文本。",
                "text": "",
                "size": len(content_bytes),
            }

        return {
            "success": True,
            "filename": filename,
            "doc_type": doc_type,
            "text": text.strip(),
            "size": len(content_bytes),
        }
    except Exception as e:
        logger.error(f"[DocParser] 解析文件 {filename} 失败: {e}", exc_info=True)
        return {
            "success": False,
            "filename": filename,
            "doc_type": doc_type,
            "error": str(e),
            "text": "",
            "size": len(content_bytes),
        }
