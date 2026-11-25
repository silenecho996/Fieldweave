# 架构说明

## 总览

```text
浏览器
  │ HTTP 127.0.0.1:8765
  ▼
src/app.py
  ├─ /api/ask
  ├─ /api/alignment
  ├─ /api/literature
  ├─ /api/workspace
  └─ /api/settings/model
        │
        ├─ search.py / knowledge.py
        ├─ model_providers.py
        ├─ literature.py
        └─ workspace_store.py
              ├─ data/knowledge-base.sqlite3（只读）
              └─ data/workspace.sqlite3（可写）
```

## 模块职责

| 模块 | 职责 |
|---|---|
| `src/app.py` | HTTP 服务、路由、问答编排、对齐接口和启动入口 |
| `src/ask.py` | 命令行问答和本地检索调用 |
| `src/search.py` | 中文分词、同义词扩展、BM25 风格排序 |
| `src/knowledge.py` | 案例预设、概念映射、覆盖任务和证据结构 |
| `src/knowledge_config.json` | 案例、映射、覆盖任务和论文链接配置 |
| `src/model_providers.py` | DeepSeek、OpenAI、Claude、Gemini 和兼容接口 |
| `src/literature.py` | Europe PMC、Crossref、OpenAlex、arXiv 和 Zenodo 采集 |
| `src/method_docs.py` | 白名单方法文档采集、正文提取和 robots.txt 检查 |
| `src/method_docs_config.json` | 方法文档白名单、种子页面和抓取限制 |
| `src/workspace_store.py` | 项目、聊天、附件、候选条目、对齐记录、方法文档和版本 |
| `src/client/app*.js` | 浏览器交互脚本，由 Python 服务直接提供 |
| `src/client/app-bulk-import.js` | 原始数据批量生成候选条目的前端流程 |
| `frontend/` | React 模板、Tailwind 主题和 shadcn/ui 组件 |
| `dist/` | 构建后的 `index.html` 和 `styles.css` |

## 数据流

### 普通问答

1. 浏览器提交 `POST /api/ask`
2. `app.py` 判断案例和检索模式
3. `search.py` 从本地知识库检索条目
4. 未配置模型时直接返回本地结果
5. 配置模型时把问题、有限前文和命中条目交给模型
6. 校验模型引用的条目编号，返回回答、结果和来源

### 跨学科对齐

1. 浏览器提交 `POST /api/alignment`
2. `app.py` 读取源案例和目标案例条目
3. `model_providers.py` 请求模型生成严格 JSON
4. 过滤模型中不存在的条目编号
5. 保存到 `alignments` 表，状态为「待确认」
6. 用户采纳、驳回或人工修订后保存最终结果

### 文献采集

1. 浏览器提交采集或批量扩展请求
2. `literature.py` 请求公开来源
3. 统一转换为文章或数据集记录
4. 去重后写入 `data/workspace.sqlite3`
5. 可从论文生成候选条目，审核后合并进知识库覆盖层

### 方法文档采集

1. 浏览器提交白名单来源和案例
2. `method_docs.py` 读取配置中的种子页面
3. 检查 robots.txt、域名、路径前缀和访问间隔
4. 抓取 HTML，提取标题、正文和允许范围内的链接
5. 保存到 `method_documents` 表，并把新增、更新和错误写入 `method_doc_runs`
6. 可从文档或批量入库页面生成候选条目，审核后合并进知识库覆盖层

## 数据库

| 文件 | 用途 |
|---|---|
| `data/knowledge-base.sqlite3` | 只读示例知识库，包含案例、条目和覆盖配置所需数据 |
| `data/workspace.sqlite3` | 可写工作台，包含项目、聊天、文件、候选、对齐、方法文档、采集记录和版本 |

`data/workspace.sqlite3` 首次启动时自动创建，已被 Git 忽略

服务启动时会用 SQLite 备份 API 把工作台复制到 `data/.backups/`，默认保留最近 10 份

## 前端构建

`src/client/*.js` 是直接运行的普通脚本，不参与 Node 构建

只有修改 `frontend/` 时才需要执行：

```bash
cd frontend
npm ci
npm run build
```

构建输出写入 `dist/index.html` 和 `dist/styles.css`

## 平台入口

| 平台 | 启动 | 测试 |
|---|---|---|
| Windows | `Start.cmd` | `Test.cmd` |
| macOS | `Start.command` | `Test.command` |
