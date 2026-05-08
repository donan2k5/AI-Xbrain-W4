import re
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# Page margins
section = doc.sections[0]
section.page_width  = Inches(8.5)
section.page_height = Inches(11)
section.left_margin = Inches(1)
section.right_margin = Inches(1)
section.top_margin = Inches(1)
section.bottom_margin = Inches(1)

BRAND    = RGBColor(0x1E, 0x3A, 0x5F)
BLUE     = RGBColor(0x25, 0x63, 0xEB)
PURPLE   = RGBColor(0x7C, 0x3A, 0xED)
GREEN    = RGBColor(0x06, 0x5F, 0x46)
GRAY     = RGBColor(0x37, 0x41, 0x51)
MUTED    = RGBColor(0x6B, 0x72, 0x80)
BLACK    = RGBColor(0x1F, 0x29, 0x37)
WHITE_C  = RGBColor(0xFF, 0xFF, 0xFF)

def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def set_cell_borders(cell, color="CCCCCC"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side in ['top','left','bottom','right']:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '4')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)

def heading(text, level=1):
    p = doc.add_paragraph()
    p.clear()
    run = p.add_run(text)
    run.bold = True
    if level == 1:
        run.font.size = Pt(18)
        run.font.color.rgb = BRAND
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(8)
    elif level == 2:
        run.font.size = Pt(14)
        run.font.color.rgb = BLUE
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)
    else:
        run.font.size = Pt(12)
        run.font.color.rgb = GRAY
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
    run.font.name = 'Arial'
    return p

def body(text, color=None, bold=False, size=11):
    p = doc.add_paragraph()
    p.clear()
    run = p.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color or BLACK
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = Pt(14)
    return p

def bullet(text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.clear()
    p.paragraph_format.left_indent = Inches(0.3 * (level + 1))
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(("  " * level) + "• " + text)
    run.font.name = 'Arial'
    run.font.size = Pt(10.5)
    run.font.color.rgb = BLACK
    return p

def spacer():
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)

def note_box(text, bg="FEF3C7", border_color="F59E0B"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    cell = tbl.cell(0, 0)
    set_cell_bg(cell, bg)
    set_cell_borders(cell, border_color)
    p = cell.paragraphs[0]
    run = p.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x78, 0x35, 0x0F)
    cell._tc.get_or_add_tcPr()
    spacer()

def make_table(headers, rows, col_widths=None, header_bg="1E3A5F"):
    n_cols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=n_cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.style = 'Table Grid'

    # Header row
    hrow = tbl.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        set_cell_bg(cell, header_bg)
        set_cell_borders(cell, "2563EB")
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.name = 'Arial'
        run.font.size = Pt(10)
        run.font.color.rgb = WHITE_C

    # Data rows
    for ri, row in enumerate(rows):
        tr = tbl.rows[ri + 1]
        bg = "F8FAFC" if ri % 2 == 0 else "FFFFFF"
        for ci, cell_text in enumerate(row):
            cell = tr.cells[ci]
            set_cell_bg(cell, bg)
            set_cell_borders(cell, "E5E7EB")
            p = cell.paragraphs[0]
            run = p.add_run(str(cell_text))
            run.font.name = 'Arial'
            run.font.size = Pt(10)
            run.font.color.rgb = BLACK

    if col_widths:
        for i, w in enumerate(col_widths):
            for row in tbl.rows:
                row.cells[i].width = Inches(w)
    spacer()
    return tbl

def code_block(text):
    p = doc.add_paragraph()
    p.clear()
    for line in text.strip().split('\n'):
        run = p.add_run(line + '\n')
        run.font.name = 'Courier New'
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)


# ─── TITLE ───
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("AI-XBrain")
r.bold = True; r.font.size = Pt(32); r.font.color.rgb = BRAND; r.font.name = 'Arial'

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Kiến trúc hệ thống RAG Agent")
r.font.size = Pt(16); r.font.color.rgb = BLUE; r.font.name = 'Arial'

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Tài liệu kỹ thuật — Tháng 5/2026")
r.font.size = Pt(11); r.font.color.rgb = MUTED; r.font.name = 'Arial'
spacer()

# ─── 1. TỔNG QUAN ───
heading("1. Tổng quan hệ thống")
body("AI-XBrain là một RAG Agent (Retrieval-Augmented Generation) xây dựng trên AWS Bedrock, cho phép người dùng truy vấn knowledge base nội bộ bằng ngôn ngữ tự nhiên. Hệ thống kết hợp vector search, cross-encoder reranking, extended thinking và tool use để trả về câu trả lời chính xác kèm trích dẫn nguồn.")
spacer()

make_table(
    ["Component", "Technology"],
    [
        ["Frontend", "React + Vite (TypeScript)"],
        ["Backend", "FastAPI + Python"],
        ["LLM", "Claude Sonnet 4 (Bedrock Converse API)"],
        ["Knowledge Base", "Amazon Bedrock KB (S3 + Titan Embeddings V2 + Hybrid Search)"],
        ["Reranker", "Cohere Rerank v3.5"],
        ["Database", "SQLite (historical data)"],
        ["Monitoring", "FastAPI custom metrics server (port 8001)"],
    ],
    [2.0, 4.5]
)

# ─── DIAGRAM (moved up) ───
heading("2. Sơ đồ kiến trúc tổng thể")
spacer()

code_block("""INDEXING PHASE (Offline)
──────────────────────────────────────────────────────────
Markdown Files → S3 Bucket → Bedrock KB Sync Job
    → Chunking → Titan Embeddings V2 → OpenSearch Vector Store

QUERY PHASE (Real-time, ~10-30s per request)
──────────────────────────────────────────────────────────
Input (câu hỏi ngôn ngữ tự nhiên)
    ↓
Claude Sonnet 4 [THINKING: which tool? which query?]
    ↓
    ├── search_knowledge_base(query)
    │       ↓
    │   Bedrock KB: query → Titan Embed V2
    │       ↓ HYBRID Search (vector + BM25)
    │   top-15 chunks (with vector scores)
    │       ↓
    │   Cohere Rerank v3.5
    │   top-10 chunks (with rerank scores)
    │       ↓ [1]..[10] labels
    │
    ├── fetch_service_metrics(service)  [optional]
    │       ↓ Monitoring API :8001
    │
    └── query_database(sql)  [optional]
            ↓ SQLite DB
    ↓
Claude reads all tool results → synthesize → answer with [n] citations
    ↓
BE: dedup citations + remap [n] → ChatResponse
    ↓
Output: answer + reasoning + citations + trace (rerank scores per chunk)""")

# ─── 3. HAI PHASE ───
heading("3. Hai phase của hệ thống")
body("Hệ thống hoạt động theo hai phase tách biệt hoàn toàn:")
spacer()

make_table(
    ["Phase 1 — Indexing (Offline)", "Phase 2 — Query (Online)"],
    [[
        "Xảy ra một lần khi upload tài liệu mới.\n1. Upload docs → S3 Bucket\n2. Bedrock KB sync job chạy\n3. Chunk documents thành đoạn nhỏ\n4. Titan Embeddings V2 tạo vector\n5. Lưu vào managed vector store",
        "Xảy ra real-time mỗi lần user hỏi.\n1. User nhập câu hỏi → FE → BE\n2. Claude reasoning: cần tool nào?\n3. Câu hỏi → embed → Hybrid Search\n4. Rerank top-15 → top-10 chunks\n5. Claude tổng hợp → trả lời + citation"
    ]],
    [3.25, 3.25],
    header_bg="1E3A5F"
)

# ─── 4. INDEXING ───
doc.add_page_break()
heading("4. Phase 1 — Indexing: Từ tài liệu đến vector store")
body("Đây là quá trình xây dựng knowledge base. Chạy một lần khi có tài liệu mới, không ảnh hưởng đến query performance.")
spacer()

heading("3.1 Upload tài liệu lên S3", 2)
make_table(
    ["Thuộc tính", "Chi tiết"],
    [
        ["Định dạng hỗ trợ", "Markdown (.md), PDF, TXT, HTML, Word"],
        ["S3 Bucket", "Cấu trúc thư mục tự do, Bedrock KB crawl toàn bộ"],
        ["Metadata", "Frontmatter YAML trong mỗi file (title, owner, tags, status)"],
        ["Access", "Bedrock KB cần IAM role có s3:GetObject permission"],
    ],
    [2.0, 4.5]
)

heading("3.2 Bedrock Knowledge Base Sync Pipeline", 2)
make_table(
    ["Bước", "Mô tả", "Service"],
    [
        ["1. Crawl S3", "Đọc toàn bộ files từ S3 bucket theo prefix đã config", "Amazon S3"],
        ["2. Parse & Clean", "Trích xuất text thuần, bỏ qua binary/metadata", "Bedrock Internal"],
        ["3. Chunking", "Chia document thành các chunk theo semantic boundaries. Kích thước và overlap có thể config", "Bedrock Internal"],
        ["4. Embedding", "Mỗi chunk encode thành dense vector 1536 chiều", "Amazon Titan Embeddings V2"],
        ["5. Index & Store", "Vector + text + metadata + S3 URI lưu vào vector store", "OpenSearch Serverless"],
    ],
    [1.5, 3.5, 2.0]
)

note_box("Lưu ý về Chunking: Kích thước chunk ảnh hưởng trực tiếp đến chất lượng retrieval. Chunk quá nhỏ → mất context. Chunk quá lớn → noise. Mỗi chunk lưu kèm: text gốc, S3 URI, document metadata, chunk index.")

# ─── 5. QUERY FLOW ───
doc.add_page_break()
heading("5. Phase 2 — Query: Từ câu hỏi đến câu trả lời")
body("Đây là flow real-time xảy ra mỗi lần user đặt câu hỏi. Toàn bộ quá trình mất 10–30 giây tùy độ phức tạp.")
spacer()

make_table(
    ["Bước", "Mô tả", "Service"],
    [
        ["1. User Input", "User nhập câu hỏi. FE gửi POST /api/chat kèm message, level, question_id", "Frontend (React)"],
        ["2. Agent Start", "BE nhận request, khởi tạo agent loop với system prompt và 3 tool definitions", "FastAPI Backend"],
        ["3. Extended Thinking", "Claude nhận câu hỏi, bật thinking mode (budget_tokens=2000, temp=1). Reasoning: câu hỏi cần tool nào?", "Claude Sonnet 4"],
        ["4. Tool Selection", "Claude quyết định gọi tool phù hợp. Có thể gọi nhiều tool song song trong một lượt", "Claude Tool Use"],
        ["5. KB Retrieval", "Câu hỏi embed bằng Titan V2. Hybrid Search: vector similarity + BM25. Lấy top_k=15 chunks", "Bedrock KB + Titan V2"],
        ["6. Reranking", "15 chunks → Cohere Rerank v3.5 → top_n=10 chunks có relevance score cao nhất", "Cohere Rerank v3.5"],
        ["7. Tool Result", "10 chunks (kèm label [1]..[10]) trả về cho Claude trong context window", "Agent Loop"],
        ["8. Synthesis", "Claude tổng hợp thông tin, cite [n] vào câu trả lời. Có thể gọi thêm tool nếu cần", "Claude Sonnet 4"],
        ["9. Citation Remap", "BE parse answer, remap citation indices về sequential [1][2][3] sau dedup theo document name", "FastAPI Backend"],
        ["10. Display", "FE render answer với inline citations, reasoning panel (thinking), trace panel với rerank scores", "Frontend (React)"],
    ],
    [1.2, 3.8, 1.5]
)

# ─── 6. EMBEDDING ───
doc.add_page_break()
heading("6. Embedding: Câu hỏi thành vector như thế nào")
spacer()

note_box(
    "Câu hỏi có qua reasoning trước khi embed không?\n\nKHÔNG. Câu hỏi gốc được embed trực tiếp mà không qua reformulation. Claude chỉ reasoning về TOOL nào cần gọi và với QUERY TEXT gì — query text đó mới được embed. Trong hầu hết trường hợp, Claude truyền câu hỏi gốc làm query.",
    "D1FAE5", "059669"
)

heading("5.1 Indexing time — Document Embedding", 2)
make_table(
    ["Thuộc tính", "Chi tiết"],
    [
        ["Model", "Amazon Titan Embeddings V2"],
        ["Output dimensions", "1536 chiều (dense vector)"],
        ["Input", "Text của chunk (stripped YAML frontmatter)"],
        ["Storage", "Vector store (OpenSearch Serverless)"],
        ["Khi nào chạy", "Chỉ khi sync KB — không chạy lại mỗi lần query"],
    ],
    [2.0, 4.5]
)

heading("5.2 Query time — Query Embedding", 2)
make_table(
    ["Thuộc tính", "Chi tiết"],
    [
        ["Model", "Amazon Titan Embeddings V2 (cùng model với indexing — bắt buộc)"],
        ["Input", "Query string từ Claude — thường là câu hỏi gốc hoặc sub-query Claude tạo ra"],
        ["Output", "Vector 1536 chiều"],
        ["Search type", "HYBRID: cosine similarity (vector) + BM25 (keyword) — weighted combination"],
        ["Top-K", "15 chunks (RETRIEVAL_TOP_K=15)"],
    ],
    [2.0, 4.5]
)

heading("5.3 Hybrid Search chi tiết", 2)
make_table(
    ["Tiêu chí", "Vector Search (Semantic)", "BM25 (Keyword)"],
    [
        ["Cơ chế", "Cosine similarity giữa query vector và chunk vectors", "Term frequency / inverse document frequency"],
        ["Điểm mạnh", "Hiểu ngữ nghĩa, synonym, paraphrase", "Exact match, tên riêng, thuật ngữ kỹ thuật"],
        ["Điểm yếu", "Yếu với keyword cụ thể (tên API, số version)", "Không hiểu ngữ nghĩa"],
        ["Ví dụ", '"circuit breaker" tìm được "open state failure"', '"PaymentGW" tìm chính xác tên service'],
    ],
    [1.5, 2.75, 2.25]
)

# ─── 6. RERANKING ───
doc.add_page_break()
heading("6. Reranking: Tại sao cần và hoạt động thế nào")
body("Vector search trả về 15 chunks theo semantic similarity — nhưng không phải chunk semantic gần cũng thực sự relevant với query cụ thể. Reranker giải quyết vấn đề này.")
spacer()

make_table(
    ["", "Vector Search Score", "Rerank Score (Cohere)"],
    [
        ["Cơ chế", "Bi-encoder: embed query + embed chunk riêng biệt, tính cosine similarity", "Cross-encoder: nhận cặp (query, chunk) cùng lúc, cho điểm relevance trực tiếp"],
        ["Ưu điểm", "Nhanh, scalable, phù hợp với millions of vectors", "Chính xác hơn nhiều — so sánh trực tiếp query với chunk"],
        ["Nhược điểm", "Không so sánh trực tiếp query với chunk — có thể miss relevant docs", "Chậm hơn, phải chạy O(n) lần với n chunks"],
    ],
    [1.3, 2.85, 2.35]
)

heading("6.1 Tại sao top_k=15 nhưng rerank top_n=10", 2)
body("Vector search lấy pool rộng (15) để không miss các chunk có vector score thấp nhưng thực sự relevant. Reranker lọc chặt còn 10 chunk chất lượng nhất — đây là số chunk Claude nhận vào context.")
spacer()

note_box(
    'Ví dụ thực tế: Query "deployment freeze override process" — incident_response_policy.md có vector score 0.296 (rank #7 trong 15). Sau reranking lên top-3 vì cross-encoder hiểu đây là document quan trọng nhất. Nếu top_k=5, document này bị bỏ qua hoàn toàn.',
    "FEF3C7", "F59E0B"
)

# ─── 7. TOOL ROUTING ───
heading("7. Tool Routing: Claude quyết định tool nào")
body("Claude không phải lúc nào cũng gọi search_knowledge_base. Hệ thống có 3 tools, Claude tự quyết định dựa trên câu hỏi:")
spacer()

make_table(
    ["Tool", "Khi nào dùng"],
    [
        ["search_knowledge_base", "Policies, API specs, team ownership, deployment rules, incident postmortems, security guidelines, SLA definitions — bất kỳ fact đã documented"],
        ["fetch_service_metrics", "Real-time metrics: latency p50/p95/p99, error rate, CPU/memory — dữ liệu live từ monitoring API (port 8001)"],
        ["query_database", "Historical data: monthly costs, SLA targets, daily metric trends — từ SQLite. KHÔNG dùng cho incident-specific questions"],
    ],
    [2.0, 4.5]
)

heading("7.1 Extended Thinking trong Tool Routing", 2)
body("Trước khi gọi tool đầu tiên, Claude có thinking block để reasoning về:")
bullet("Câu hỏi này hỏi về loại thông tin gì?")
bullet("Cần tool nào? Hay cần kết hợp nhiều tool?")
bullet("Query text nào phù hợp nhất để truyền vào search_knowledge_base?")
spacer()

note_box(
    "Giới hạn quan trọng: Thinking xảy ra TRƯỚC khi tool được gọi — tại thời điểm này chưa có chunk nào. Vì vậy thinking không thể reasoning về chunk cụ thể nào được chọn. Đây là sự khác biệt so với Bedrock Agent Core, vốn có mandatory rationale step SAU MỖI tool result.",
    "FEE2E2", "EF4444"
)

# ─── 8. SO SÁNH ───
doc.add_page_break()
heading("8. So sánh với Bedrock Agent Core")
spacer()

make_table(
    ["Tiêu chí", "AI-XBrain (Converse API)", "Bedrock Agent Core"],
    [
        ["Agent loop", "Tự viết trong Python", "AWS quản lý"],
        ["Tools", "Python functions (in-process)", "Lambda functions"],
        ["KB retrieval", "Gọi retrieve() + rerank() thủ công", "Managed, tự động"],
        ["Pre-tool thinking", "✅ Extended thinking", "✅ Rationale"],
        ["Post-tool thinking (interleaved)", "❌ Không có (model hiện tại)", "✅ Mandatory rationale sau mỗi observation"],
        ["Chunk-level trace", "✅ Rerank scores (custom built)", "✅ Native knowledgeBaseLookupOutput"],
        ["Control flow", "✅ Full — custom rerank, threshold, logic", "❌ Limited — AWS orchestration"],
        ["Tools deployment", "✅ Python in-process, flexible", "❌ Lambda functions only"],
    ],
    [2.2, 2.4, 2.4]
)

note_box(
    "Gap duy nhất quan trọng: Interleaved thinking — Bedrock Agent Core force rationale sau mỗi tool result, còn setup hiện tại chỉ có pre-tool thinking. Có thể thu hẹp gap bằng cách upgrade lên Claude Sonnet 4.6 với adaptive thinking mode (interleaved thinking tự động).",
    "EDE9FE", "7C3AED"
)

# ─── 9. CONFIG ───
heading("9. Cấu hình hệ thống")
spacer()

make_table(
    ["Tham số", "Giá trị"],
    [
        ["BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"],
        ["RETRIEVAL_TOP_K", "15 — số chunks lấy từ vector search"],
        ["RERANK_TOP_N", "10 — số chunks giữ lại sau reranking"],
        ["Rerank Model", "cohere.rerank-v3-5:0 (Bedrock Rerank API)"],
        ["Embedding Model", "Amazon Titan Embeddings V2 (1536 dims)"],
        ["Search Type", "HYBRID (vector similarity + BM25)"],
        ["Thinking", "enabled, budget_tokens=2000, temperature=1"],
        ["Max Output Tokens", "6000 (bao gồm thinking + answer)"],
        ["Frontend", "http://0.0.0.0:5173"],
        ["Backend", "http://0.0.0.0:8000 — /api/chat, /api/traces/:id"],
        ["Monitoring API", "http://localhost:8001 — /metrics/:service, /incidents"],
    ],
    [2.5, 4.0]
)

# ─── 10. TRACE ───
heading("10. Observability & Tracing")
body("Mỗi request tạo ra một TraceRecord lưu in-memory (mất khi BE restart). FE dùng trace_id để fetch từ /api/traces/:id.")
spacer()

make_table(
    ["Field", "Nội dung"],
    [
        ["reasoning", "Extended thinking block từ Claude (pre-tool reasoning)"],
        ["tool_calls", "Danh sách tool được gọi: tên, params, kết quả hint"],
        ["retrieval.chunks", "Chunks retrieved: document name, text excerpt, vector score, rerank score"],
        ["citations", "Sources được cite trong answer (sau dedup + remap)"],
        ["latency_ms", "Tổng thời gian từ khi nhận request đến khi trả response"],
        ["trace_id", "UUID cho mỗi request"],
    ],
    [2.0, 4.5]
)

# ─── 11. DIAGRAM ───
doc.add_page_break()
heading("11. Sơ đồ tóm tắt")
spacer()

code_block("""INDEXING PHASE (Offline)
──────────────────────────────────────────────────────────
Markdown Files → S3 Bucket → Bedrock KB Sync Job
    → Chunking → Titan Embeddings V2 → OpenSearch Vector Store

QUERY PHASE (Real-time, ~10-30s per request)
──────────────────────────────────────────────────────────
User Question
    ↓
React FE → POST /api/chat → FastAPI BE
    ↓
Claude Sonnet 4 [THINKING: which tool? which query?]
    ↓
    ├── search_knowledge_base(query)
    │       ↓
    │   Bedrock KB: query → Titan Embed V2
    │       ↓ HYBRID Search (vector + BM25)
    │   top-15 chunks (with vector scores)
    │       ↓
    │   Cohere Rerank v3.5
    │   top-10 chunks (with rerank scores)
    │       ↓ [1]..[10] labels
    │
    ├── fetch_service_metrics(service)  [optional]
    │       ↓ Monitoring API :8001
    │
    └── query_database(sql)  [optional]
            ↓ SQLite DB
    ↓
Claude reads all tool results → synthesize → answer with [n] citations
    ↓
BE: dedup citations + remap [n] → ChatResponse
    ↓
React FE: render answer + reasoning panel + trace panel
         (rerank scores visible per chunk)""")

doc.save("E:\\Project\\Learn-Project\\AI-Engineer\\AI-XBrain\\docs\\AI-XBrain-Architecture.docx")
print("Done: AI-XBrain-Architecture.docx")
