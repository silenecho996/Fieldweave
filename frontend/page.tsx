import { Button } from "./src/ui/button"
import { Input } from "./src/ui/input"
import { Label } from "./src/ui/label"
import { SidebarContent, SidebarGroupContent } from "./src/ui/sidebar"
import { Textarea } from "./src/ui/textarea"

function FolderIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4.5l2 2H19A1.5 1.5 0 0 1 20.5 9v8A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17Z"/></svg>
}

export function Workbench({ brandDefinitions }: { brandDefinitions: string }) {
  return (
    <>
      <svg className="svg-library" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"
        dangerouslySetInnerHTML={{ __html: brandDefinitions }} />
      <a className="skip-link" href="#question">跳到提问</a>
      <div id="shell" className="shell">
        <nav id="tool-rail" className="tool-rail" aria-label="工作台工具">
          <Button variant="ghost" id="open-nav" className="rail-button" type="button" aria-label="切换侧栏" title="切换侧栏" aria-controls="sidebar" aria-expanded="false">
            <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M9 5v14"/></svg>
          </Button>
          <div className="rail-tools">
            <Button variant="ghost" id="go-home" className="rail-button" type="button" aria-label="Home 首页" title="Home · 首页" disabled>
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 10.6 12 4l8 6.6V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z"/></svg>
            </Button>
            <Button variant="ghost" id="show-literature" className="rail-button" type="button" aria-label="文献与数据" aria-haspopup="dialog" title="文献与数据" disabled>
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 19V5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1 0-4h13M8 7h7m-7 4h7"/></svg>
            </Button>
            <Button variant="ghost" id="show-files" className="rail-button" type="button" aria-label="查看文件" aria-haspopup="dialog" title="查看文件" disabled>
              <FolderIcon />
              <span id="file-count" className="file-count" aria-hidden="true" hidden></span>
            </Button>
          </div>
        </nav>
        <Button variant="ghost" id="nav-backdrop" className="nav-backdrop" type="button" aria-hidden="true" tabIndex={-1}></Button>
        <aside id="sidebar" className="sidebar" aria-label="项目和聊天">
          <div className="brand-row">
            <svg className="brand-lockup" role="img" aria-label="Fieldweave"><use href="#fieldweave-lockup"/></svg>
            <Button variant="ghost" id="open-search" className="search-toggle" type="button" aria-label="搜索聊天" aria-expanded="false" aria-controls="search-panel" title="搜索聊天" disabled>
              <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></svg>
            </Button>
            <Button variant="ghost" id="close-nav" className="icon-button close-nav" type="button" aria-label="收起侧栏">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </div>
          <Button variant="secondary" id="new-chat" className="new-chat" type="button" disabled>
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5M10 14l.7-3.3 6.8-6.8a1.7 1.7 0 0 1 2.4 2.4l-6.8 6.8L10 14Z"/></svg>
            新聊天
          </Button>
          <SidebarContent className="sidebar-content">
            <nav id="pinned-section" className="sidebar-group pinned-section" aria-labelledby="pinned-heading" hidden>
              <div className="sidebar-section-heading">
                <button id="toggle-pinned" className="section-toggle" type="button" aria-expanded="true" aria-controls="pinned">
                  <svg className="section-chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                  <span id="pinned-heading" className="section-title">置顶</span>
                </button>
              </div>
              <SidebarGroupContent id="pinned" className="pinned" />
            </nav>
            <nav id="projects-section" className="sidebar-group project-section" aria-labelledby="projects-heading">
              <div className="sidebar-section-heading">
                <button id="toggle-projects" className="section-toggle" type="button" aria-expanded="true" aria-controls="projects">
                  <svg className="section-chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                  <span id="projects-heading" className="section-title">项目</span>
                </button>
                <div className="section-actions">
                  <Button variant="ghost" id="new-project" className="sidebar-action" type="button" aria-haspopup="dialog" disabled>新建项目</Button>
                </div>
              </div>
              <SidebarGroupContent id="projects" className="projects" />
            </nav>
            <nav id="chats-section" className="sidebar-group history-section" aria-labelledby="chats-heading" hidden>
              <div className="sidebar-section-heading">
                <button id="toggle-chats" className="section-toggle" type="button" aria-expanded="true" aria-controls="chats">
                  <svg className="section-chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                  <span id="chats-heading" className="section-title">聊天</span>
                </button>
              </div>
              <SidebarGroupContent id="chats" className="history" />
            </nav>
          </SidebarContent>
          <nav id="sidebar-tools" className="sidebar-tools" aria-labelledby="tools-heading">
            <h2 id="tools-heading" className="tools-title">工具</h2>
            <div className="tool-list">
              <Button variant="ghost" id="chat-actions" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m14 6 4 4M5 19l4.2-.8L19 8.4a2.4 2.4 0 0 0-3.4-3.4L5.8 14.8 5 19Z"/></svg>
                编辑或移动聊天
              </Button>
              <Button variant="ghost" id="rail-settings" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>
                API 设置
              </Button>
              <Button variant="ghost" id="show-compare" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="16" rx="1"/><rect x="13" y="4" width="7" height="16" rx="1"/></svg>
                方法对比
              </Button>
              <Button variant="ghost" id="show-alignment" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h10a3 3 0 0 1 0 6H9"/><path d="M20 17H10a3 3 0 0 1 0-6h5"/><path d="m11 4 3 3-3 3M13 14l-3 3 3 3"/></svg>
                跨学科对齐
              </Button>
              <Button variant="ghost" id="show-method-docs" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></svg>
                方法文档
              </Button>
              <Button variant="ghost" id="show-bulk-import" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10"/><path d="m17 15 3 3-3 3"/></svg>
                批量入库
              </Button>
              <Button variant="ghost" id="export-chat" className="tool-row" type="button" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M12 12v5"/><path d="m9.5 14.5 2.5 2.5 2.5-2.5"/></svg>
                导出对话为 Markdown
              </Button>
              <Button variant="ghost" id="show-candidates" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h2M10 6h10M4 12h2M10 12h10M4 18h2M10 18h10"/><path d="m3.5 6 1 1 2-2"/></svg>
                待核对条目
              </Button>
              <Button variant="ghost" id="show-knowledge" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 4h13a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M5 17h15"/></svg>
                知识库
              </Button>
              <Button variant="ghost" id="show-trash" className="tool-row" type="button" aria-haspopup="dialog" disabled>
                <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/></svg>
                回收站
              </Button>
              <a id="export-workspace" className="tool-row" href="/api/workspace/export" download>
                <svg aria-hidden="true" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v14c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/></svg>
                导出工作台
              </a>
            </div>
          </nav>
        </aside>

        <main id="workspace" className="workspace">
          <header className="topbar">
            <div className="topbar-leading">
              <div id="thread-meta" className="thread-meta" aria-label="当前对话" hidden>
                <div id="thread-project" className="thread-project" hidden>
                  <FolderIcon />
                  <span id="project-label" className="project-label"></span>
                </div>
                <p id="chat-title" className="chat-title">研究对话</p>
              </div>
            </div>
          </header>

          <div id="thread-scroll" className="thread-scroll">
            <div id="welcome" className="welcome content-width">
              <div className="welcome-content">
                <header className="welcome-heading">
                  <span className="welcome-brand brand-tile"><svg className="brand-mark" aria-hidden="true"><use href="#fieldweave-mark"/></svg></span>
                  <h1>今天要研究什么</h1>
                </header>
                <section id="examples" className="examples" aria-labelledby="examples-heading" hidden>
                  <div className="examples-header">
                    <h2 id="examples-heading">从示例开始</h2>
                    <details id="case-picker" className="topbar-disclosure case-picker" name="topbar-popups">
                      <summary id="case-heading" className="topbar-control">
                        <span id="case-scope" className="case-scope">正在读取案例</span>
                        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                      </summary>
                      <div className="scope-popover topbar-popover">
                        <nav id="cases" className="cases" aria-label="切换示例主题"></nav>
                      </div>
                    </details>
                  </div>
                  <fieldset id="example-list" className="example-list" aria-labelledby="examples-heading" disabled></fieldset>
                </section>
              </div>
            </div>
            <section id="transcript" className="transcript content-width" aria-label="对话内容" hidden></section>
          </div>
          <p id="turn-updates" className="sr-only" role="status"></p>

          <div id="composer-slot">
            <div id="composer-dock" className="dock">
              <div className="content-width">
                <div id="connection-note" className="connection-note" hidden>
                  <p id="page-message" className="notice" role="status"></p>
                  <Button variant="outline" id="reload-cases" className="secondary-button" type="button">重新读取案例</Button>
                </div>
                <p id="workspace-note" className="workspace-note" role="status" hidden></p>
                <form id="question-form" className="composer">
                  <div id="attached-files" className="attached-files" aria-label="聊天文件" hidden></div>
                  <Label className="sr-only" htmlFor="question">你的研究问题</Label>
                  <Textarea id="question" className="border-0 shadow-none focus-visible:ring-0" name="question" maxLength={600} rows={1} required
                    aria-describedby="composer-hint"
                    placeholder="和Fieldweave一起工作" />
                  <div className="composer-controls">
                    <Button variant="ghost" id="attach-file" className="attach-button" type="button" aria-label="添加文件" title="添加文件" disabled>
                      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                    </Button>
                    <div className="composer-actions">
                      <details id="model-picker" className="model-picker" name="topbar-popups">
                        <summary id="model-heading" className="model-trigger" aria-label="选择模型" aria-disabled="true">
                          <span id="active-model" className="active-model">本地知识库</span>
                          <span id="active-model-short" className="active-model active-model-short" aria-hidden="true">本地</span>
                          <span id="active-effort" className="active-effort" hidden></span>
                          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                        </summary>
                        <div className="model-menu">
                          <div className="model-field">
                            <Label htmlFor="quick-model">模型</Label>
                            <select id="quick-model" disabled>
                              <option value="local">本地知识库</option>
                            </select>
                          </div>
                          <div id="quick-effort-field" className="model-field" hidden>
                            <Label htmlFor="quick-effort">思考强度</Label>
                            <select id="quick-effort" disabled></select>
                          </div>
                          <p id="model-menu-status" className="model-menu-status" role="status"></p>
                          <Button variant="ghost" id="show-settings" className="model-settings-button" type="button" aria-haspopup="dialog">API 设置</Button>
                        </div>
                      </details>
                      <Button variant="ghost" id="send" className="send-button" type="submit" aria-label="发送" title="发送" disabled>
                        <svg className="send-arrow" aria-hidden="true" viewBox="0 0 24 24"><path d="M12 19V5m-6 6 6-6 6 6"/></svg>
                      </Button>
                    </div>
                  </div>
                </form>
                <input id="upload-input" type="file" accept=".pdf,.docx,.csv,.tsv,.txt,.md,.png,.jpeg,.jpg,.webp" multiple hidden />
                <div id="composer-hint" className="composer-hint">
                  <span className="composer-drop-hint" aria-hidden="true">松开以添加到当前对话</span>
                  <span className="keyboard-hint">Enter 发送 · Shift + Enter 换行</span>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
      <div id="search-overlay" className="search-overlay" hidden>
        <section id="search-sheet" className="search-sheet" role="dialog" aria-modal="true" aria-labelledby="search-title">
          <header className="search-head">
            <svg className="search-head-icon" aria-hidden="true" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></svg>
            <h2 id="search-title" className="sr-only">搜索 Fieldweave</h2>
            <Input id="chat-search" className="search-input" type="search" placeholder="搜索 Fieldweave" aria-label="搜索聊天、文件和操作" autoComplete="off" disabled />
            <Button variant="ghost" id="close-search" className="search-close" type="button" aria-label="关闭搜索" title="关闭搜索 (Esc)">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </header>
          <div id="search-body" className="search-body">
            <section id="search-actions-section" className="search-section" data-group="actions" hidden>
              <h3>快捷操作</h3>
              <div id="search-actions"></div>
            </section>
            <section id="search-chats-section" className="search-section" data-group="chats" hidden>
              <h3>聊天</h3>
              <div id="search-chats"></div>
            </section>
            <section id="search-files-section" className="search-section" data-group="files" hidden>
              <h3>最近文件</h3>
              <div id="search-files"></div>
            </section>
            <section id="search-text-section" className="search-section" data-group="text" hidden>
              <h3>文本</h3>
              <div id="search-text"></div>
            </section>
            <p id="search-empty" className="search-empty" hidden>没有找到相关内容</p>
          </div>
          <nav id="search-tabs" className="search-tabs" aria-label="搜索范围">
            <button type="button" data-filter="all" aria-pressed="true">全部</button>
            <button type="button" data-filter="actions" aria-pressed="false">操作</button>
            <button type="button" data-filter="chats" aria-pressed="false">聊天</button>
            <button type="button" data-filter="files" aria-pressed="false">文件</button>
            <button type="button" data-filter="text" aria-pressed="false">文本</button>
          </nav>
        </section>
      </div>
      <dialog id="editor-dialog" className="workbench-dialog editor-dialog" aria-labelledby="editor-title">
        <form id="editor-form" method="dialog">
          <h2 id="editor-title">编辑</h2>
          <div className="editor-fields">
            <div>
              <Label id="name-label" htmlFor="editor-name">名称</Label>
              <Input id="editor-name" type="text" autoComplete="off" maxLength={100} required autoFocus />
            </div>
            <div id="editor-description-group" hidden>
              <Label htmlFor="editor-description">项目说明</Label>
              <Textarea id="editor-description" rows={3} maxLength={600} />
            </div>
            <div id="editor-project-group" hidden>
              <Label htmlFor="editor-project">移动到项目</Label>
              <select id="editor-project"></select>
            </div>
          </div>
          <p id="editor-error" className="notice" role="status" hidden></p>
          <div className="dialog-actions">
            <Button variant="outline" id="editor-cancel" className="secondary-button" type="button">取消</Button>
            <Button variant="default" id="editor-save" className="primary-button" type="submit">保存</Button>
          </div>
        </form>
      </dialog>
      <dialog id="files-dialog" className="workbench-dialog files-dialog" aria-labelledby="files-dialog-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="files-dialog-title">文件资料</h2>
            <p id="file-list-hint" className="file-list-hint"></p>
          </div>
          <div className="file-dialog-actions">
            <Button variant="default" id="file-manager-upload" className="primary-button" type="button">上传文件</Button>
            <Button variant="outline" id="files-close" className="utility-button icon-only" type="button" aria-label="关闭文件资料" title="关闭文件资料">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </div>
        </header>
        <div className="files-dialog-content">
          <div id="file-list" className="file-list" aria-label="文件列表"></div>
          <section className="file-preview-area" aria-labelledby="file-preview-title">
            <h3 id="file-preview-title">文件预览</h3>
            <div id="file-preview" className="file-preview">
              <p className="file-empty">选择一个文件即可查看预览</p>
            </div>
          </section>
        </div>
      </dialog>
      <dialog id="literature-dialog" className="workbench-dialog literature-dialog" aria-labelledby="literature-title">
        <header className="dialog-header">
          <h2 id="literature-title">文献与数据</h2>
          <Button variant="outline" id="literature-close" className="utility-button icon-only" type="button" aria-label="关闭文献和数据">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <div className="literature-tools">
          <fieldset id="literature-kinds" className="literature-kinds">
            <legend className="sr-only">采集类型</legend>
            <div className="mode-options">
              <Label><input type="radio" name="literature-kind" value="article" defaultChecked /><span>论文</span></Label>
              <Label><input type="radio" name="literature-kind" value="dataset" /><span>公开数据集</span></Label>
            </div>
          </fieldset>
          <form id="literature-form" className="literature-form">
            <div><Label htmlFor="literature-case">研究案例</Label><select id="literature-case" /></div>
            <div><Label htmlFor="literature-query">英文检索词</Label><Input id="literature-query" maxLength={180} autoComplete="off" /></div>
            <div><Label htmlFor="literature-limit">数量</Label><Input id="literature-limit" type="number" min={1} max={10} defaultValue={6} required /></div>
            <Button variant="default" id="collect-literature" className="primary-button" type="submit" disabled>采集并入库</Button>
          </form>
          <div className="literature-status">
            <p id="literature-message" role="status"></p>
            <div className="literature-status-actions">
              <Button variant="outline" id="generate-candidates" className="secondary-button" type="button" disabled>批量生成候选</Button>
              <Button variant="outline" id="expand-literature" className="secondary-button" type="button" disabled>批量扩展</Button>
              <a id="literature-export" className="file-action" hidden>导出原始记录</a>
            </div>
          </div>
        </div>
        <div className="literature-grid">
          <div id="literature-list" className="literature-list" aria-label="已入库文献"></div>
          <section id="literature-detail" className="literature-detail" aria-label="文献详情">
            <p className="file-empty">选择一篇文献查看详情</p>
          </section>
        </div>
      </dialog>
      <dialog id="candidates-dialog" className="workbench-dialog candidates-dialog" aria-labelledby="candidates-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="candidates-title">待核对条目</h2>
            <p id="candidates-hint" className="file-list-hint">审核通过后合并到工作台知识库覆盖层</p>
          </div>
          <div className="file-dialog-actions">
            <Button variant="default" id="merge-candidates" className="primary-button" type="button" disabled>合并已通过</Button>
            <Button variant="outline" id="candidate-versions-toggle" className="secondary-button" type="button">版本记录</Button>
            <a id="candidates-export" className="file-action" href="/api/workspace/candidates/export" download>导出 JSON</a>
            <Button variant="outline" id="candidates-close" className="utility-button icon-only" type="button" aria-label="关闭待核对条目">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </div>
        </header>
        <div id="candidates-list" className="candidates-list" aria-label="待核对条目列表"></div>
        <section id="candidate-versions" className="candidate-versions" hidden>
          <div className="candidate-versions-head">
            <h3>知识库版本</h3>
            <Button variant="outline" id="versions-back" className="secondary-button" type="button">返回候选</Button>
          </div>
          <p id="versions-meta" className="file-meta"></p>
          <div id="versions-list"></div>
        </section>
      </dialog>
      <dialog id="knowledge-dialog" className="workbench-dialog knowledge-dialog" aria-labelledby="knowledge-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="knowledge-title">知识库</h2>
            <p id="knowledge-meta" className="file-list-hint">原始知识库 + 工作台覆盖层</p>
          </div>
          <Button variant="outline" id="knowledge-close" className="utility-button icon-only" type="button" aria-label="关闭知识库">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <div className="knowledge-tools">
          <div><Label htmlFor="knowledge-case">案例</Label><select id="knowledge-case"></select></div>
          <div><Label htmlFor="knowledge-filter">筛选</Label><Input id="knowledge-filter" maxLength={80} autoComplete="off" placeholder="按编号、方法或概念筛选" /></div>
          <Label className="knowledge-toggle"><input id="knowledge-show-inactive" type="checkbox" />显示停用</Label>
        </div>
        <div id="knowledge-coverage" className="coverage-summary" aria-live="polite"></div>
        <div id="knowledge-list" className="knowledge-list" aria-label="知识库条目"></div>
      </dialog>
      <dialog id="knowledge-entry-dialog" className="workbench-dialog editor-dialog knowledge-entry-dialog" aria-labelledby="knowledge-entry-title">
        <form id="knowledge-entry-form">
          <h2 id="knowledge-entry-title">编辑知识条目</h2>
          <p id="knowledge-entry-source" className="file-meta"></p>
          <div className="editor-fields">
            <div><Label htmlFor="knowledge-entry-scenario">研究场景</Label><Textarea id="knowledge-entry-scenario" rows={2} maxLength={600} required /></div>
            <div><Label htmlFor="knowledge-entry-concept">关联概念</Label><Input id="knowledge-entry-concept" maxLength={300} autoComplete="off" /></div>
            <div><Label htmlFor="knowledge-entry-method">方法名称</Label><Input id="knowledge-entry-method" maxLength={300} autoComplete="off" required /></div>
            <div><Label htmlFor="knowledge-entry-rationale">推荐理由</Label><Textarea id="knowledge-entry-rationale" rows={3} maxLength={1200} /></div>
            <div><Label htmlFor="knowledge-entry-conditions">适用条件</Label><Textarea id="knowledge-entry-conditions" rows={2} maxLength={600} /></div>
            <div><Label htmlFor="knowledge-entry-limitations">局限</Label><Textarea id="knowledge-entry-limitations" rows={2} maxLength={600} /></div>
            <div><Label htmlFor="knowledge-entry-evidence">证据</Label><Textarea id="knowledge-entry-evidence" rows={3} maxLength={3000} /></div>
          </div>
          <p id="knowledge-entry-error" className="notice" role="status" hidden></p>
          <div className="dialog-actions">
            <Button variant="outline" id="knowledge-entry-cancel" className="secondary-button" type="button">取消</Button>
            <Button variant="default" className="primary-button" type="submit">保存</Button>
          </div>
        </form>
      </dialog>
      <dialog id="trash-dialog" className="workbench-dialog trash-dialog" aria-labelledby="trash-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="trash-title">回收站</h2>
            <p id="trash-hint" className="file-list-hint">删除的聊天和项目会保留在这里</p>
          </div>
          <Button variant="outline" id="trash-close" className="utility-button icon-only" type="button" aria-label="关闭回收站">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <div id="trash-list" className="trash-list"></div>
      </dialog>
      <dialog id="project-dialog" className="workbench-dialog project-dialog" aria-labelledby="project-dialog-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="project-dialog-title">项目概览</h2>
            <p id="project-dialog-meta" className="file-list-hint"></p>
          </div>
          <div className="file-dialog-actions">
            <Button variant="outline" id="project-report" className="secondary-button" type="button">导出报告</Button>
            <Button variant="default" id="project-dialog-new-chat" className="primary-button" type="button">新建聊天</Button>
            <Button variant="outline" id="project-dialog-close" className="utility-button icon-only" type="button" aria-label="关闭项目概览">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </div>
        </header>
        <div className="project-dashboard">
          <div id="project-stats" className="project-stats"></div>
          <div className="project-dashboard-grid">
            <section className="project-panel" aria-labelledby="project-chats-heading">
              <h3 id="project-chats-heading">最近聊天</h3>
              <div id="project-recent-chats"></div>
            </section>
            <section className="project-panel" aria-labelledby="project-files-heading">
              <h3 id="project-files-heading">项目资料</h3>
              <div id="project-recent-files"></div>
            </section>
            <section className="project-panel" aria-labelledby="project-candidates-heading">
              <h3 id="project-candidates-heading">待核对条目</h3>
              <div id="project-candidates"></div>
            </section>
            <section className="project-panel" aria-labelledby="project-cases-heading">
              <h3 id="project-cases-heading">涉及案例</h3>
              <div id="project-cases"></div>
            </section>
          </div>
          <section className="project-panel project-coverage-panel" aria-labelledby="project-coverage-heading">
            <h3 id="project-coverage-heading">知识覆盖</h3>
            <div id="project-coverage" className="coverage-summary"></div>
          </section>
        </div>
      </dialog>
      <dialog id="compare-dialog" className="workbench-dialog compare-dialog" aria-labelledby="compare-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="compare-title">方法对比</h2>
            <p id="compare-meta" className="file-list-hint">选择 2 至 5 个方法生成对比表和综述大纲</p>
          </div>
          <div className="file-dialog-actions">
            <Button variant="default" id="compare-export" className="primary-button" type="button" disabled>导出 Markdown</Button>
            <Button variant="outline" id="compare-close" className="utility-button icon-only" type="button" aria-label="关闭方法对比">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </Button>
          </div>
        </header>
        <div className="compare-tools">
          <div><Label htmlFor="compare-case">研究案例</Label><select id="compare-case"></select></div>
          <div><Label htmlFor="compare-filter">筛选方法</Label><Input id="compare-filter" maxLength={80} autoComplete="off" placeholder="按方法、概念或场景筛选" /></div>
        </div>
        <div className="compare-grid">
          <div id="compare-list" className="compare-list" aria-label="知识库方法列表"></div>
          <div className="compare-preview">
            <div id="compare-table" className="compare-table-wrap"></div>
            <div id="compare-outline" className="compare-outline" aria-live="polite"></div>
          </div>
        </div>
      </dialog>
      <dialog id="method-docs-dialog" className="workbench-dialog method-docs-dialog" aria-labelledby="method-docs-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="method-docs-title">方法文档</h2>
            <p className="file-list-hint">仅采集白名单站点，遵守 robots.txt 和访问间隔</p>
          </div>
          <Button variant="outline" id="method-docs-close" className="utility-button icon-only" type="button" aria-label="关闭方法文档">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <div className="method-docs-tools">
          <div><Label htmlFor="method-docs-source">文档来源</Label><select id="method-docs-source"></select></div>
          <div><Label htmlFor="method-docs-case">研究案例</Label><select id="method-docs-case"></select></div>
          <Button variant="default" id="collect-method-docs" className="primary-button" type="button">采集方法文档</Button>
        </div>
        <p id="method-docs-message" className="method-docs-message" role="status"></p>
        <div className="method-docs-grid">
          <div id="method-docs-list" className="method-docs-list" aria-label="已采集方法文档"></div>
          <section id="method-docs-detail" className="method-docs-detail" aria-live="polite">
            <p className="file-empty">选择一份方法文档查看正文</p>
          </section>
        </div>
      </dialog>
      <dialog id="bulk-import-dialog" className="workbench-dialog bulk-import-dialog" aria-labelledby="bulk-import-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="bulk-import-title">批量入库</h2>
            <p className="file-list-hint">原始数据 → 生成候选 → 人工审核 → 合并知识库</p>
          </div>
          <Button variant="outline" id="bulk-import-close" className="utility-button icon-only" type="button" aria-label="关闭批量入库">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <div className="bulk-import-tools">
          <div><Label htmlFor="bulk-import-case">研究案例</Label><select id="bulk-import-case"></select></div>
          <div><Label htmlFor="bulk-import-type">原始数据类型</Label><select id="bulk-import-type">
            <option value="document">方法文档</option>
            <option value="article">文献</option>
          </select></div>
          <Button variant="outline" id="bulk-import-select-all" className="secondary-button" type="button">全选</Button>
          <Button variant="default" id="bulk-import-generate" className="primary-button" type="button" disabled>生成候选条目</Button>
        </div>
        <p id="bulk-import-message" className="bulk-import-message" role="status"></p>
        <div className="bulk-import-grid">
          <div id="bulk-import-list" className="bulk-import-list" aria-label="原始数据列表"></div>
          <aside className="bulk-import-aside" aria-labelledby="bulk-import-flow-heading">
            <h3 id="bulk-import-flow-heading">入库流程</h3>
            <ol>
              <li>选择案例和原始数据类型</li>
              <li>勾选需要处理的记录</li>
              <li>生成候选条目，等待人工审核</li>
              <li>审核通过后合并进工作台知识库</li>
            </ol>
            <Button variant="outline" id="bulk-import-open-candidates" className="secondary-button" type="button">打开待核对条目</Button>
          </aside>
        </div>
      </dialog>
      <dialog id="alignment-dialog" className="workbench-dialog alignment-dialog" aria-labelledby="alignment-title">
        <header className="dialog-header">
          <div className="file-dialog-heading">
            <h2 id="alignment-title">跨学科对齐</h2>
            <p id="alignment-meta" className="file-list-hint">比较源学科与目标学科的术语、方法和观点</p>
          </div>
          <Button variant="outline" id="alignment-close" className="utility-button icon-only" type="button" aria-label="关闭跨学科对齐">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <form id="alignment-form" className="alignment-tools">
          <div><Label htmlFor="alignment-source">源学科</Label><select id="alignment-source"></select></div>
          <div><Label htmlFor="alignment-target">目标学科</Label><select id="alignment-target"></select></div>
          <div><Label htmlFor="alignment-task">分析类型</Label><select id="alignment-task">
            <option value="term">术语对齐</option>
            <option value="compare">观点对照</option>
          </select></div>
          <div className="alignment-input-field">
            <Label htmlFor="alignment-text">术语、研究问题或观点</Label>
            <Input id="alignment-text" maxLength={1200} autoComplete="off" placeholder="例如：病灶分割 / 传播风险如何影响决策" required />
          </div>
          <Button variant="default" id="alignment-analyze" className="primary-button" type="submit" disabled>开始分析</Button>
        </form>
        <div className="alignment-grid">
          <aside className="alignment-history-panel" aria-labelledby="alignment-history-heading">
            <h3 id="alignment-history-heading">最近记录</h3>
            <div id="alignment-history" className="alignment-history"></div>
          </aside>
          <section id="alignment-result" className="alignment-result" aria-live="polite">
            <p className="file-empty">选择源学科和目标学科，然后输入要比较的术语或研究问题。</p>
          </section>
        </div>
      </dialog>
      <dialog id="candidate-dialog" className="workbench-dialog editor-dialog candidate-dialog" aria-labelledby="candidate-title">
        <form id="candidate-form">
          <h2 id="candidate-title">加入待核对条目</h2>
          <p id="candidate-source" className="file-meta"></p>
          <div className="editor-fields">
            <div><Label htmlFor="candidate-scenario">研究场景</Label><Textarea id="candidate-scenario" rows={2} maxLength={600} required /></div>
            <div><Label htmlFor="candidate-concept">关联概念</Label><Input id="candidate-concept" maxLength={300} autoComplete="off" /></div>
            <div><Label htmlFor="candidate-method">方法名称</Label><Input id="candidate-method" maxLength={300} autoComplete="off" required /></div>
            <div><Label htmlFor="candidate-rationale">推荐理由</Label><Textarea id="candidate-rationale" rows={3} maxLength={1200} /></div>
            <div><Label htmlFor="candidate-conditions">适用条件</Label><Textarea id="candidate-conditions" rows={2} maxLength={600} /></div>
            <div><Label htmlFor="candidate-limitations">局限</Label><Textarea id="candidate-limitations" rows={2} maxLength={600} /></div>
            <div><Label htmlFor="candidate-evidence">证据</Label><Textarea id="candidate-evidence" rows={3} maxLength={3000} /></div>
            <div><Label htmlFor="candidate-notes">备注</Label><Textarea id="candidate-notes" rows={2} maxLength={800} /></div>
          </div>
          <p id="candidate-error" className="notice" role="status" hidden></p>
          <div className="dialog-actions">
            <Button variant="outline" id="candidate-cancel" className="secondary-button" type="button">取消</Button>
            <Button variant="default" className="primary-button" type="submit">保存到待核对</Button>
          </div>
        </form>
      </dialog>
      <dialog id="settings-dialog" className="workbench-dialog settings-dialog" aria-labelledby="settings-title">
        <header className="dialog-header">
          <h2 id="settings-title">API 设置</h2>
          <Button variant="outline" id="settings-close" className="utility-button icon-only" type="button" aria-label="关闭 API 设置">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </Button>
        </header>
        <form id="settings-form" className="settings-form">
          <fieldset id="settings-fields" disabled>
            <div className="editor-fields">
              <div>
                <Label htmlFor="settings-provider">供应商</Label>
                <select id="settings-provider"></select>
              </div>
              <div id="settings-address-field" hidden>
                <Label htmlFor="settings-address">Base URL</Label>
                <Input id="settings-address" type="url" maxLength={300} placeholder="https://api.example.com/v1" spellCheck={false} aria-describedby="settings-address-note" />
                <p id="settings-address-note" className="file-meta">使用公开的 HTTPS 地址，测试时会发送一条简短消息</p>
              </div>
              <div>
                <Label htmlFor="settings-model">模型 ID</Label>
                <Input id="settings-model" list="settings-model-list" type="text" maxLength={120} autoComplete="off" spellCheck={false} />
                <datalist id="settings-model-list"></datalist>
              </div>
              <div>
                <Label htmlFor="settings-key">API Key</Label>
                <Input id="settings-key" type="password" autoComplete="new-password" maxLength={1000} spellCheck={false} aria-describedby="settings-key-note" />
                <p className="file-meta" id="settings-key-note">网页填写的密钥只保留到本地服务重启</p>
              </div>
              <div id="settings-effort-field">
                <Label htmlFor="settings-effort">思考强度</Label>
                <select id="settings-effort"></select>
                <p className="file-meta">可用档位取决于具体模型</p>
              </div>
            </div>
            <p className="file-meta settings-privacy">问答时会向所选供应商发送问题和命中的知识库条目</p>
            <p id="settings-message" className="settings-message" role="status"></p>
            <div className="dialog-actions">
              <Button variant="ghost" id="settings-clear" className="settings-clear" type="button" hidden>移除密钥</Button>
              <Button variant="outline" id="settings-test" className="secondary-button" type="button">测试连接</Button>
              <Button variant="default" className="primary-button" type="submit">保存并使用</Button>
            </div>
          </fieldset>
        </form>
      </dialog>
      <template id="shadcn-normal-button"><Button variant="ghost" size="sm" type="button" /></template>
      <template id="project-icons">
        <svg className="project-chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg>
        <FolderIcon />
        <span className="project-name"></span>
      </template>
      <template id="reply-mark">
        <svg aria-hidden="true"><use href="#fieldweave-mark"/></svg>
      </template>
    </>
  )
}
