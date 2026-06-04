import io
import os
import pandas as pd
from pypdf import PdfReader

def parse_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parses a PDF file and returns a list of dictionaries with page text and metadata.
    """
    documents = []
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        num_pages = len(reader.pages)
        
        for page_num in range(num_pages):
            page = reader.pages[page_num]
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": filename,
                        "page": page_num + 1,
                        "total_pages": num_pages,
                        "type": "pdf"
                    }
                })
    except Exception as e:
        raise ValueError(f"Failed to parse PDF file '{filename}': {str(e)}")
        
    return documents

def parse_excel(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parses an Excel file (.xlsx) and returns a list of dictionaries with sheet rows represented as text.
    """
    documents = []
    try:
        excel_file = io.BytesIO(file_bytes)
        # Read all sheets
        xls = pd.ExcelFile(excel_file)
        
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            # Remove completely empty rows/columns
            df = df.dropna(how='all').dropna(axis=1, how='all')
            
            if df.empty:
                continue
                
            # Convert rows to descriptive text
            # Format: "Sheet: {sheet_name} | Row {index} | Column1: Value1 | Column2: Value2 ..."
            rows_text = []
            headers = [str(col).strip() for col in df.columns]
            
            for idx, row in df.iterrows():
                row_parts = []
                for col_name, val in zip(headers, row):
                    if pd.notna(val):
                        # Clean value string representation
                        val_str = str(val).strip()
                        if val_str:
                            row_parts.append(f"{col_name}: {val_str}")
                
                if row_parts:
                    row_num = idx + 2  # 1-indexed, plus 1 for header row typically
                    rows_text.append(f"Row {row_num}: " + " | ".join(row_parts))
            
            # Group rows to avoid too tiny chunks, say 10 rows per block
            group_size = 10
            for i in range(0, len(rows_text), group_size):
                chunk_rows = rows_text[i:i+group_size]
                text_block = f"Excel Sheet: {sheet_name}\n" + "\n".join(chunk_rows)
                
                documents.append({
                    "text": text_block,
                    "metadata": {
                        "source": filename,
                        "sheet": sheet_name,
                        "rows": f"{i+2}-{i+1+len(chunk_rows)}",
                        "type": "xlsx"
                    }
                })
    except Exception as e:
        raise ValueError(f"Failed to parse Excel file '{filename}': {str(e)}")
        
    return documents

def parse_txt(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Parses a plain text file, handling decoding fallbacks.
    """
    text = ""
    encodings = ['utf-8', 'latin-1', 'utf-16', 'cp1252']
    
    for encoding in encodings:
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Could not decode text file '{filename}' with standard encodings.")
        
    text = text.strip()
    if not text:
        return []
        
    return [{
        "text": text,
        "metadata": {
            "source": filename,
            "type": "txt"
        }
    }]

def parse_file(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Dispatches file content to appropriate parser based on extension.
    """
    _, ext = os.path.splitext(filename.lower())
    if ext == '.pdf':
        return parse_pdf(file_bytes, filename)
    elif ext == '.xlsx':
        return parse_excel(file_bytes, filename)
    elif ext in ['.txt', '.text']:
        return parse_txt(file_bytes, filename)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Only .pdf, .xlsx, and .txt are accepted.")
