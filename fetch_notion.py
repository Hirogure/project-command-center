import os
import requests
from datetime import datetime, timezone

NOTION_TOKEN = os.environ['NOTION_TOKEN']
PROJECT_STATE_ID = '32d31e4fdf10808fbc52f7d6061da723'
PJ_STATUS_DB_ID  = '9d74cf694098491c8527deb5fafa98d6'
PIPELINE_DB_ID   = 'a25b228ca90e41e587a48d2627256262'

HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

# ──────────────────────────────────────────
# Notion API helpers
# ──────────────────────────────────────────

def get_blocks(block_id):
    blocks, cursor = [], None
    while True:
        params = {'page_size': 100}
        if cursor:
            params['start_cursor'] = cursor
        r = requests.get(
            f'https://api.notion.com/v1/blocks/{block_id}/children',
            headers=HEADERS, params=params
        )
        data = r.json()
        blocks.extend(data.get('results', []))
        if data.get('has_more'):
            cursor = data['next_cursor']
        else:
            break
    return blocks

def query_database(db_id):
    r = requests.post(
        f'https://api.notion.com/v1/databases/{db_id}/query',
        headers=HEADERS, json={'page_size': 100}
    )
    return r.json().get('results', [])

def plain(rich_text_list):
    return ''.join(rt.get('plain_text', '') for rt in rich_text_list)

def to_html(rich_text_list):
    out = ''
    for rt in rich_text_list:
        t = rt.get('plain_text', '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        a = rt.get('annotations', {})
        if a.get('bold'):    t = f'<strong>{t}</strong>'
        if a.get('italic'):  t = f'<em>{t}</em>'
        if a.get('code'):    t = f'<code>{t}</code>'
        if rt.get('href'):   t = f'<a href="{rt["href"]}" target="_blank">{t}</a>'
        out += t
    return out

def prop_val(prop):
    pt = prop.get('type','')
    if pt == 'title':       return plain(prop['title'])
    if pt == 'rich_text':   return plain(prop['rich_text'])
    if pt == 'select':      return (prop['select'] or {}).get('name','')
    if pt == 'status':      return (prop['status'] or {}).get('name','')
    if pt == 'multi_select':return ', '.join(s['name'] for s in prop.get('multi_select',[]))
    if pt == 'date':        return (prop['date'] or {}).get('start','') if prop.get('date') else ''
    if pt == 'number':      n=prop.get('number'); return str(n) if n is not None else ''
    if pt == 'checkbox':    return '✅' if prop.get('checkbox') else '☐'
    if pt == 'url':         u=prop.get('url'); return f'<a href="{u}" target="_blank">リンク</a>' if u else ''
    if pt == 'formula':
        f=prop.get('formula',{}); ft=f.get('type','')
        if ft=='string': return f.get('string','')
        if ft=='number': return str(f.get('number',''))
    return ''

# ──────────────────────────────────────────
# Block → HTML converter
# ──────────────────────────────────────────

def blocks_to_html(blocks):
    html, i = '', 0
    while i < len(blocks):
        b = blocks[i]; bt = b['type']

        if bt == 'paragraph':
            t = to_html(b['paragraph']['rich_text'])
            if t: html += f'<p>{t}</p>'

        elif bt in ('heading_1','heading_2','heading_3'):
            lv = bt[-1]
            t = to_html(b[bt]['rich_text'])
            html += f'<h{lv}>{t}</h{lv}>'

        elif bt == 'bulleted_list_item':
            items = []
            while i < len(blocks) and blocks[i]['type'] == 'bulleted_list_item':
                items.append(f'<li>{to_html(blocks[i]["bulleted_list_item"]["rich_text"])}</li>')
                i += 1
            html += '<ul>' + ''.join(items) + '</ul>'
            continue

        elif bt == 'numbered_list_item':
            items = []
            while i < len(blocks) and blocks[i]['type'] == 'numbered_list_item':
                items.append(f'<li>{to_html(blocks[i]["numbered_list_item"]["rich_text"])}</li>')
                i += 1
            html += '<ol>' + ''.join(items) + '</ol>'
            continue

        elif bt == 'table':
            rows = get_blocks(b['id'])
            has_header = b['table'].get('has_column_header', False)
            html += '<table>'
            for j, row in enumerate(rows):
                cells = row['table_row']['cells']
                tag = 'th' if (j == 0 and has_header) else 'td'
                html += '<tr>' + ''.join(f'<{tag}>{to_html(c)}</{tag}>' for c in cells) + '</tr>'
            html += '</table>'

        elif bt == 'callout':
            t = to_html(b['callout']['rich_text'])
            icon = b['callout'].get('icon') or {}
            emoji = icon.get('emoji','') if icon.get('type')=='emoji' else '💡'
            html += f'<div class="callout">{emoji} {t}</div>'

        elif bt == 'quote':
            t = to_html(b['quote']['rich_text'])
            html += f'<blockquote>{t}</blockquote>'

        elif bt == 'divider':
            html += '<hr>'

        elif bt == 'child_database':
            pass  # 別途クエリで取得

        i += 1
    return html

# ──────────────────────────────────────────
# Section extractor
# ──────────────────────────────────────────

def get_section(blocks, keyword):
    in_sec, result = False, []
    for b in blocks:
        bt = b['type']
        if bt == 'heading_2':
            txt = plain(b['heading_2']['rich_text'])
            if keyword in txt:
                in_sec = True
                continue
            elif in_sec:
                break
        elif in_sec:
            result.append(b)
    return result

# ──────────────────────────────────────────
# DB renderers
# ──────────────────────────────────────────

def render_pj_db(records):
    if not records:
        return '<p class="empty">データなし</p>'
    
    # 全レコードのプロパティキーを収集
    all_keys = []
    for r in records:
        for k in r['properties']:
            if k not in all_keys:
                all_keys.append(k)
    
    # タイトル系を先頭に
    title_keys = [k for k in all_keys if records[0]['properties'][k].get('type') == 'title']
    other_keys = [k for k in all_keys if k not in title_keys]
    keys = title_keys + other_keys
    
    html = '<table><thead><tr>' + ''.join(f'<th>{k}</th>' for k in keys) + '</tr></thead><tbody>'
    for r in records:
        props = r['properties']
        row = ''
        for k in keys:
            v = prop_val(props.get(k, {'type': 'rich_text', 'rich_text': []}))
            row += f'<td>{v}</td>'
        html += f'<tr>{row}</tr>'
    html += '</tbody></table>'
    return html

def render_pipeline(records):
    if not records:
        return '<p class="empty">データなし</p>'
    html = '<div class="pipeline-grid">'
    for r in records:
        props = r['properties']
        title = next((prop_val(v) for v in props.values() if v.get('type')=='title'), '(無題)')
        status = ''
        for k, v in props.items():
            if v.get('type') == 'status' or 'ステータス' in k or k.lower() in ('status','state'):
                status = prop_val(v)
                break
        html += f'''<div class="pipeline-card">
            <div class="card-badge">{status}</div>
            <div class="pipeline-title">{title}</div>
        </div>'''
    html += '</div>'
    return html

# ──────────────────────────────────────────
# HTML builder
# ──────────────────────────────────────────

def build(all_blocks, pj_records, pipeline_records):
    top5_html    = blocks_to_html(get_section(all_blocks, 'TOP5'))
    watch_html   = blocks_to_html(get_section(all_blocks, '監視'))
    deadline_html= blocks_to_html(get_section(all_blocks, '期限'))
    pj_html      = render_pj_db(pj_records)
    pipe_html    = render_pipeline(pipeline_records)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hiro / Project Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:      #0b0e15;
  --s1:      #131720;
  --s2:      #1a2030;
  --border:  #252d3d;
  --accent:  #4f9cf9;
  --purple:  #a78bfa;
  --warn:    #f59e0b;
  --danger:  #ef4444;
  --ok:      #22c55e;
  --text:    #dde3ee;
  --muted:   #5a6a82;
  --dim:     #8a9ab5;
}}
*{{ margin:0; padding:0; box-sizing:border-box; }}
body{{
  background:var(--bg); color:var(--text);
  font-family:'Noto Sans JP',sans-serif; font-size:13px; line-height:1.65;
}}
header{{
  background:var(--s1); border-bottom:1px solid var(--border);
  padding:14px 24px; display:flex; align-items:center;
  justify-content:space-between; position:sticky; top:0; z-index:99;
}}
.logo{{
  font-family:'JetBrains Mono',monospace; font-size:12px;
  font-weight:600; color:var(--accent); letter-spacing:.12em;
}}
.meta{{
  font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted);
}}
.grid{{
  display:grid; grid-template-columns:1fr 1fr;
  gap:14px; padding:18px 22px; max-width:1440px; margin:0 auto;
}}
.card{{
  background:var(--s1); border:1px solid var(--border);
  border-radius:10px; padding:18px; overflow:hidden;
}}
.card.full{{ grid-column:1/-1; }}
.card-title{{
  font-family:'JetBrains Mono',monospace; font-size:10.5px;
  font-weight:600; color:var(--muted); letter-spacing:.14em;
  text-transform:uppercase; margin-bottom:14px;
  padding-bottom:10px; border-bottom:1px solid var(--border);
}}
/* typography */
p{{ color:var(--dim); margin-bottom:6px; }}
h1,h2,h3{{ color:var(--text); margin:10px 0 6px; font-size:14px; }}
ol,ul{{ padding-left:18px; }}
ol li,ul li{{ margin-bottom:6px; color:var(--dim); }}
ol li strong,ul li strong{{ color:var(--text); }}
a{{ color:var(--accent); text-decoration:none; }}
a:hover{{ text-decoration:underline; }}
code{{
  background:var(--s2); padding:1px 5px; border-radius:3px;
  font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--purple);
}}
hr{{ border:none; border-top:1px solid var(--border); margin:10px 0; }}
blockquote{{
  border-left:2px solid var(--border); padding-left:10px;
  color:var(--muted); font-size:12px; margin:6px 0;
}}
.callout{{
  background:var(--s2); border-left:3px solid var(--purple);
  padding:8px 12px; border-radius:0 6px 6px 0;
  margin:6px 0; color:var(--dim); font-size:12.5px;
}}
/* table */
table{{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th{{
  background:var(--s2); color:var(--muted); padding:7px 10px;
  text-align:left; font-weight:500; font-size:11px; white-space:nowrap;
}}
td{{
  padding:7px 10px; border-bottom:1px solid var(--border);
  color:var(--dim); vertical-align:top;
}}
tr:last-child td{{ border-bottom:none; }}
tr:hover td{{ background:rgba(255,255,255,.02); }}
/* pipeline */
.pipeline-grid{{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px;
}}
.pipeline-card{{
  background:var(--s2); border:1px solid var(--border);
  border-radius:7px; padding:12px 14px;
}}
.card-badge{{
  font-size:10px; color:var(--muted); margin-bottom:5px;
  font-family:'JetBrains Mono',monospace; letter-spacing:.06em;
}}
.pipeline-title{{ font-size:13px; font-weight:500; color:var(--text); }}
.empty{{ color:var(--muted); font-size:12px; }}
@media(max-width:700px){{
  .grid{{ grid-template-columns:1fr; padding:10px; }}
  .card.full{{ grid-column:1; }}
}}
</style>
</head>
<body>
<header>
  <div class="logo">⬡ HIRO / PROJECT DASHBOARD</div>
  <div class="meta">最終更新: {now}</div>
</header>

<div class="grid">

  <div class="card">
    <div class="card-title">🎯 今日 / 今週 TOP5</div>
    {top5_html or '<p class="empty">データなし</p>'}
  </div>

  <div class="card">
    <div class="card-title">⚠️ 監視 · 連絡待ち</div>
    {watch_html or '<p class="empty">データなし</p>'}
  </div>

  <div class="card full">
    <div class="card-title">📅 期限あり項目</div>
    {deadline_html or '<p class="empty">データなし</p>'}
  </div>

  <div class="card full">
    <div class="card-title">📊 全PJステータス</div>
    {pj_html}
  </div>

  <div class="card full">
    <div class="card-title">② 案件パイプライン</div>
    {pipe_html}
  </div>

</div>
</body>
</html>'''

# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

def main():
    print('Fetching PROJECT_STATE...')
    blocks = get_blocks(PROJECT_STATE_ID)

    print('Querying PJ Status DB...')
    pj = query_database(PJ_STATUS_DB_ID)

    print('Querying Pipeline DB...')
    pipeline = query_database(PIPELINE_DB_ID)

    print('Building HTML...')
    html = build(blocks, pj, pipeline)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Done → index.html')

if __name__ == '__main__':
    main()
