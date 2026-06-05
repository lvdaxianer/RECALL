"""
SEE 时间线页面路由

提供无需前端构建链的检索过程可视化页面。

@author lvdaxianerplus
@date 2026-06-03
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["SEE Timeline"])


@router.get("/see/timeline", response_class=HTMLResponse)
async def get_see_timeline_page():
    """
    返回 SEE 时间线页面

    @returns HTML 页面
    """
    return HTMLResponse(content=_build_timeline_html())


def _build_timeline_html() -> str:
    """构建 SEE Timeline HTML。"""
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SEE Timeline</title>
  <link rel="stylesheet" href="/static/see-timeline.css">
</head>
<body>
  <main class="app-shell">
    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Recall RAG</p>
          <h1>SEE Timeline</h1>
        </div>
        <div class="request-chip" id="request-id">request_id: -</div>
      </header>

      <form id="search-form" class="search-panel" autocomplete="off">
        <label>
          <span>user_id</span>
          <input id="user-id" name="user_id" value="u001">
        </label>
        <label class="query-field">
          <span>query</span>
          <textarea id="query-input" name="query" rows="3">我的小程序上线后白屏了，之前本地开发都正常，分析下</textarea>
        </label>
        <div class="control-row">
          <label>
            <span>type</span>
            <select id="search-type" name="type">
              <option value="all">all</option>
              <option value="skill">skill</option>
              <option value="asset">asset</option>
            </select>
          </label>
          <label>
            <span>topK</span>
            <input id="top-k" name="topK" type="number" min="1" max="100" value="20">
          </label>
          <label class="toggle-row">
            <input id="feature-boost" name="enableFeatureBoost" type="checkbox">
            <span>feature boost</span>
          </label>
          <button type="submit">Run</button>
        </div>
      </form>

      <section class="actions">
        <button id="invalidate-cache" type="button" disabled>撤销本次排序缓存</button>
        <form id="feedback-form" class="feedback-form">
          <select id="miss-reason" name="miss_reason">
            <option value="rerank_error">rerank_error</option>
            <option value="recall_miss">recall_miss</option>
            <option value="intent_error">intent_error</option>
            <option value="generation_error">generation_error</option>
            <option value="stale_knowledge">stale_knowledge</option>
            <option value="unknown">unknown</option>
          </select>
          <button type="submit" disabled id="bad-feedback">Bad feedback</button>
        </form>
      </section>

      <section class="history-panel">
        <div>
          <label>
            <span>session</span>
            <select id="session-select"></select>
          </label>
        </div>
        <div>
          <label>
            <span>run</span>
            <select id="run-select"></select>
          </label>
        </div>
        <button id="load-history" type="button">Load</button>
        <button id="replay-run" type="button">Replay</button>
      </section>

      <section class="timeline" aria-live="polite">
        <article class="timeline-card" data-event="request.created"></article>
        <article class="timeline-card" data-event="query.decomposition"></article>
        <article class="timeline-card" data-event="retrieval.original.completed"></article>
        <article class="timeline-card" data-event="retrieval.optimized.completed"></article>
        <article class="timeline-card" data-event="rerank.completed"></article>
        <article class="timeline-card" data-event="recommendation.completed"></article>
      </section>
    </section>

    <aside class="side-panel">
      <h2>Trace</h2>
      <pre id="event-log"></pre>
      <template id="endpoint-template">
        /api/v1/rag/{user_id}/search/optimize/stream
        /api/v1/rag/cache/rerank/invalidate-by-request/
        /api/v1/rag/{user_id}/feedback/bad-case
        /api/v1/agent/{user_id}/sessions
        /api/v1/agent/{user_id}/sessions/{session_id}/events
      </template>
    </aside>
  </main>
  <script src="/static/see-timeline.js" defer></script>
</body>
</html>
"""
