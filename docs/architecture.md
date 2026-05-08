# AI-XBrain — Kiến trúc hệ thống RAG Agent

**Tài liệu kỹ thuật — Tháng 5/2026**

---

## 1. Tổng quan hệ thống

AI-XBrain là một RAG Agent (Retrieval-Augmented Generation) xây dựng trên AWS Bedrock, cho phép người dùng truy vấn knowledge base nội bộ bằng ngôn ngữ tự nhiên. Hệ thống kết hợp vector search, cross-encoder reranking, extended thinking và tool use để trả về câu trả lời chính xác kèm trích dẫn nguồn.

**Stack công nghệ:**

| Component      | Technology                                                   |
| -------------- | ------------------------------------------------------------ |
| Frontend       | React + Vite (TypeScript)                                    |
| Backend        | FastAPI + Python                                             |
| LLM            | Claude Sonnet 4 (Bedrock Converse API)                       |
| Knowledge Base | Amazon Bedrock KB (S3 + Titan Embeddings V2 + Hybrid Search) |
| Reranker       | Cohere Rerank v3.5                                           |
| Database       | SQLite (historical data)                                     |
| Monitoring     | FastAPI custom metrics server (port 8001)                    |

---

## 2. Sơ đồ kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────┐
│              INDEXING PHASE  —  Offline                 │
└─────────────────────────────────────────────────────────┘

 Markdown Files  →  S3 Bucket  →  Bedrock KB Sync Job
                                          │
                                    ┌─────┴──────────┐
                                    │  1. Chunking   │
                                    │  2. Titan V2   │
                                    │    (1536 dims) │
                                    └─────┬──────────┘
                                          │
                                          ▼
                                  OpenSearch Vector Store
                                  (vectors + metadata)

┌─────────────────────────────────────────────────────────┐
│           QUERY PHASE  —  Real-time (~10–30s)           │
└─────────────────────────────────────────────────────────┘

                       INPUT
               (câu hỏi tự nhiên)
                        │
                        ▼
           ┌────────────────────────┐
           │     Claude Sonnet 4    │
           │  [ THINKING ]          │
           │  • chọn tool nào?      │
           │  • query text gì?      │
           └───────────┬────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌────────────┐ ┌────────────┐
│  search_kb   │ │  fetch_    │ │  query_db  │
│  (query)     │ │  metrics   │ │  (sql)     │
├──────────────┤ │ [optional] │ │ [optional] │
│ Bedrock KB   │ ├────────────┤ ├────────────┤
│ → Titan V2   │ │ Monitor    │ │ SQLite DB  │
│ → HYBRID Srch│ │ API :8001  │ │ historical │
│   top-15     │ └─────┬──────┘ └─────┬──────┘
│ → Cohere Rnk │       │              │
│   top-10 [n] │       │              │
└──────┬───────┘       │              │
       │               │              │
       └───────────────┴──────────────┘
                       │
                       ▼
           ┌────────────────────────┐
           │     Claude Sonnet 4    │
           │  synthesize + cite [n] │
           └───────────┬────────────┘
                       │
                       ▼
           ┌────────────────────────┐
           │    FastAPI Backend     │
           │  dedup + remap [n]     │
           └───────────┬────────────┘
                       │
                       ▼
              ┌────────────────┐
              │    OUTPUT      │
              ├────────────────┤
              │ answer         │
              │ reasoning      │
              │ citations      │
              │ trace + scores │
              └────────────────┘
```

---

## 3. Hai phase của hệ thống

Hệ thống hoạt động theo hai phase tách biệt hoàn toàn:

### Phase 1 — Indexing (Offline)

Xảy ra một lần khi upload tài liệu mới, không ảnh hưởng đến query performance:

1. Upload docs → S3 Bucket
2. Bedrock KB sync job chạy
3. Chunk documents thành đoạn nhỏ
4. Titan Embeddings V2 tạo vector cho từng chunk
5. Lưu vào managed vector store (OpenSearch Serverless)

### Phase 2 — Query (Online)

Xảy ra real-time mỗi lần user hỏi:

1. Input (câu hỏi ngôn ngữ tự nhiên)
2. Claude reasoning: cần tool nào?
3. Câu hỏi → embed → vector search + BM25
4. Rerank top-15 → top-10 chunks
5. Claude tổng hợp → trả lời + citation

---

## 4. Phase 1 — Indexing: Từ tài liệu đến vector store

### 4.1 Upload tài liệu lên S3

Tất cả tài liệu nội bộ (Markdown files) được lưu trong S3 bucket — đây là nguồn dữ liệu duy nhất cho Knowledge Base.

| Thuộc tính       | Chi tiết                                                     |
| ---------------- | ------------------------------------------------------------ |
| Định dạng hỗ trợ | Markdown (.md), PDF, TXT, HTML, Word                         |
| S3 Bucket        | Cấu trúc thư mục tự do, Bedrock KB crawl toàn bộ             |
| Metadata         | Frontmatter YAML trong mỗi file (title, owner, tags, status) |
| Access           | Bedrock KB cần IAM role có s3:GetObject permission           |

### 4.2 Bedrock Knowledge Base Sync Pipeline

Sau khi upload, trigger sync job từ Bedrock console hoặc API:

| Bước             | Mô tả                                                      | Service                    |
| ---------------- | ---------------------------------------------------------- | -------------------------- |
| 1. Crawl S3      | Đọc toàn bộ files từ S3 bucket theo prefix đã config       | Amazon S3                  |
| 2. Parse & Clean | Trích xuất text thuần, bỏ qua binary/metadata              | Bedrock Internal           |
| 3. Chunking      | Chia document thành các chunk nhỏ theo semantic boundaries | Bedrock Internal           |
| 4. Embedding     | Mỗi chunk được encode thành dense vector 1536 chiều        | Amazon Titan Embeddings V2 |
| 5. Index & Store | Vector + text + metadata + S3 URI lưu vào vector store     | OpenSearch Serverless      |

> **Lưu ý về Chunking:** Kích thước chunk ảnh hưởng trực tiếp đến chất lượng retrieval. Chunk quá nhỏ → mất context. Chunk quá lớn → noise. Mỗi chunk lưu kèm: text gốc, S3 URI, document metadata, chunk index.

---

## 5. Phase 2 — Query: Từ câu hỏi đến câu trả lời

### 5.1 Flow tổng thể

| Bước                 | Mô tả                                                                                                         | Service            |
| -------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------ |
| 1. Input             | Câu hỏi ngôn ngữ tự nhiên được gửi vào hệ thống                                                               | -                  |
| 2. Agent Start       | BE nhận request, khởi tạo agent loop với system prompt và tool definitions                                    | FastAPI Backend    |
| 3. Extended Thinking | Claude nhận câu hỏi, bật thinking mode. Model reasoning: câu hỏi cần tool nào? KB search hay metrics hay SQL? | Claude Sonnet 4    |
| 4. Tool Selection    | Claude quyết định gọi tool phù hợp. Có thể gọi nhiều tool trong một lượt                                      | Claude Tool Use    |
| 5. KB Retrieval      | Câu hỏi được embed bằng Titan V2. Hybrid Search: vector + BM25. Lấy top_k=15 chunks                           | Bedrock KB         |
| 6. Reranking         | 15 chunks → Cohere Rerank v3.5 → top_n=10 chunks có relevance score cao nhất                                  | Cohere Rerank v3.5 |
| 7. Tool Result       | 10 chunks (kèm label [1]..[10]) trả về cho Claude                                                             | Agent Loop         |
| 8. Synthesis         | Claude tổng hợp, cite [n] vào câu trả lời. Có thể gọi thêm tool nếu cần                                       | Claude Sonnet 4    |
| 9. Citation Remap    | BE parse answer, remap citation indices về sequential [1][2][3] sau dedup theo document                       | FastAPI Backend    |
| 10. Output           | Answer + reasoning + citations + trace với rerank scores per chunk                                            | -                  |

---

## 6. Embedding: Câu hỏi thành vector như thế nào

> **Câu hỏi có qua reasoning trước khi embed không?**
>
> **KHÔNG.** Câu hỏi gốc được embed trực tiếp mà không qua reformulation. Claude chỉ reasoning về TOOL nào cần gọi và với QUERY TEXT gì — query text đó mới được embed. Trong hầu hết trường hợp, Claude truyền câu hỏi gốc làm query.

### 6.1 Indexing time — Document Embedding

| Thuộc tính        | Chi tiết                                       |
| ----------------- | ---------------------------------------------- |
| Model             | Amazon Titan Embeddings V2                     |
| Output dimensions | 1536 chiều (dense vector)                      |
| Input             | Text của chunk (stripped YAML frontmatter)     |
| Storage           | Vector store (OpenSearch Serverless)           |
| Khi nào chạy      | Chỉ khi sync KB — không chạy lại mỗi lần query |

### 6.2 Query time — Query Embedding

| Thuộc tính  | Chi tiết                                                                    |
| ----------- | --------------------------------------------------------------------------- |
| Model       | Amazon Titan Embeddings V2 (cùng model với indexing — bắt buộc)             |
| Input       | Query string từ Claude — thường là câu hỏi gốc hoặc sub-query Claude tạo ra |
| Output      | Vector 1536 chiều                                                           |
| Search type | HYBRID: cosine similarity (vector) + BM25 (keyword)                         |
| Top-K       | 15 chunks (RETRIEVAL_TOP_K=15)                                              |

### 6.3 Hybrid Search chi tiết

| Tiêu chí  | Vector Search (Semantic)                             | BM25 (Keyword)                              |
| --------- | ---------------------------------------------------- | ------------------------------------------- |
| Cơ chế    | Cosine similarity giữa query vector và chunk vectors | Term frequency / inverse document frequency |
| Điểm mạnh | Hiểu ngữ nghĩa, synonym, paraphrase                  | Exact match, tên riêng, thuật ngữ kỹ thuật  |
| Điểm yếu  | Yếu với keyword cụ thể (tên API, số version)         | Không hiểu ngữ nghĩa                        |
| Ví dụ     | "circuit breaker" tìm được "open state failure"      | "PaymentGW" tìm chính xác tên service       |

---

## 7. Reranking: Tại sao cần và hoạt động thế nào

Vector search trả về 15 chunks theo semantic similarity — nhưng không phải chunk semantic gần cũng thực sự relevant với query cụ thể. Reranker giải quyết vấn đề này.

|            | Vector Search Score                                                      | Rerank Score (Cohere)                                                         |
| ---------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| Cơ chế     | Bi-encoder: embed query + embed chunk riêng biệt, tính cosine similarity | Cross-encoder: nhận cặp (query, chunk) cùng lúc, cho điểm relevance trực tiếp |
| Ưu điểm    | Nhanh, scalable                                                          | Chính xác hơn nhiều                                                           |
| Nhược điểm | Không so sánh trực tiếp query với chunk                                  | Chậm hơn, O(n) với n chunks                                                   |

### 7.1 Tại sao top_k=15 nhưng rerank top_n=10

Vector search lấy pool rộng (15) để không miss các chunk có vector score thấp nhưng thực sự relevant. Reranker lọc chặt còn 10 chunk chất lượng nhất — đây là số chunk Claude nhận vào context.

> **Ví dụ thực tế:** Query "deployment freeze override process" — `incident_response_policy.md` có vector score 0.296 (rank #7 trong 15). Sau reranking lên top-3 vì cross-encoder hiểu đây là document quan trọng nhất. Nếu top_k=5, document này đã bị bỏ qua hoàn toàn.

---

## 8. Tool Routing: Claude quyết định tool nào

Claude không phải lúc nào cũng gọi `search_knowledge_base`. Hệ thống có 3 tools:

| Tool                    | Khi nào dùng                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `search_knowledge_base` | Policies, API specs, team ownership, deployment rules, incident postmortems, security guidelines, SLA definitions        |
| `fetch_service_metrics` | Real-time metrics: latency p50/p95/p99, error rate, CPU/memory — dữ liệu live từ monitoring API                          |
| `query_database`        | Historical data: monthly costs, SLA targets, daily metric trends — từ SQLite. KHÔNG dùng cho incident-specific questions |

### 8.1 Extended Thinking trong Tool Routing

Trước khi gọi tool đầu tiên, Claude có thinking block (budget_tokens=2000, temperature=1) để reasoning về:

- Câu hỏi này hỏi về loại thông tin gì?
- Cần tool nào? Hay cần kết hợp nhiều tool?
- Query text nào phù hợp nhất để truyền vào `search_knowledge_base`?

> **Giới hạn quan trọng:** Thinking xảy ra TRƯỚC khi tool được gọi — tại thời điểm này chưa có chunk nào. Vì vậy thinking không thể reasoning về chunk cụ thể nào được chọn. Đây là sự khác biệt so với Bedrock Agent Core, vốn có mandatory rationale step SAU MỖI tool result (interleaved reasoning).

---

## 9. Citation & Response Generation

### 9.1 Citation Remapping

Nếu agent gọi `search_knowledge_base` nhiều lần, citation counter tăng liên tục (lần 1: [1]-[10], lần 2: [11]-[20]). BE tự động remap về sequential sau khi dedup theo document name:

1. Tìm tất cả [n] trong answer theo thứ tự xuất hiện
2. Dedup theo document: nếu [1] và [10] cùng file, chỉ giữ 1 citation entry
3. Remap inline citations: [1][10][11][15] → [1][1][2][3] trong answer text
4. Sources panel hiển thị [1], [2], [3] khớp hoàn toàn với inline citations

---

## 10. So sánh với Bedrock Agent Core

| Tiêu chí                         | AI-XBrain (Converse API)                       | Bedrock Agent Core                         |
| -------------------------------- | ---------------------------------------------- | ------------------------------------------ |
| Agent loop                       | Tự viết trong Python                           | AWS quản lý                                |
| Tools                            | Python functions                               | Lambda functions                           |
| KB retrieval                     | Gọi retrieve() + rerank() thủ công             | Managed, tự động                           |
| Pre-tool thinking                | ✅ Extended thinking                           | ✅ Rationale                               |
| Post-tool thinking (interleaved) | ❌ Không có (model hiện tại)                   | ✅ Mandatory rationale sau mỗi observation |
| Chunk-level trace                | ✅ Rerank scores (custom built)                | ✅ Native knowledgeBaseLookupOutput        |
| Control                          | ✅ Full — custom rerank, threshold, tool logic | ❌ Limited — AWS orchestration             |
| Tools deployment                 | ✅ Python in-process                           | ❌ Lambda only                             |

> **Gap duy nhất quan trọng:** Interleaved thinking — Bedrock Agent Core force rationale sau mỗi tool result, còn setup hiện tại chỉ có pre-tool thinking. Có thể thu hẹp gap bằng cách upgrade lên Claude Sonnet 4.6 với adaptive thinking mode.

---

## 11. Cấu hình hệ thống

| Tham số           | Giá trị                                    |
| ----------------- | ------------------------------------------ |
| BEDROCK_MODEL_ID  | us.anthropic.claude-sonnet-4-20250514-v1:0 |
| RETRIEVAL_TOP_K   | 15 (vector search pool)                    |
| RERANK_TOP_N      | 10 (chunks đưa vào context)                |
| Rerank Model      | cohere.rerank-v3-5:0                       |
| Embedding Model   | Amazon Titan Embeddings V2 (1536 dims)     |
| Search Type       | HYBRID (vector + BM25)                     |
| Thinking          | enabled, budget_tokens=2000, temperature=1 |
| Max Output Tokens | 6000                                       |
| Frontend          | http://0.0.0.0:5173                        |
| Backend           | http://0.0.0.0:8000                        |
| Monitoring API    | http://localhost:8001                      |

---

## 12. Observability & Tracing

Mỗi request tạo ra một TraceRecord lưu in-memory:

| Field              | Nội dung                                                                  |
| ------------------ | ------------------------------------------------------------------------- |
| `reasoning`        | Extended thinking block từ Claude (pre-tool reasoning)                    |
| `tool_calls`       | Danh sách tool được gọi: tên, params, kết quả hint                        |
| `retrieval.chunks` | Chunks retrieved: document name, text excerpt, vector score, rerank score |
| `citations`        | Sources được cite trong answer (sau dedup + remap)                        |
| `latency_ms`       | Tổng thời gian từ khi nhận request đến khi trả response                   |
| `trace_id`         | UUID cho mỗi request                                                      |

> **Rerank score trong trace:** So sánh vector score và rerank score giải thích tại sao một chunk được chọn dù vector score thấp. Reranker đánh giá relevance trực tiếp theo query, không chỉ theo semantic similarity.
