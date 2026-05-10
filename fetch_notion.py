import os
import re
import requests
from datetime import datetime, timezone, timedelta

NOTION_TOKEN     = os.environ['NOTION_TOKEN']
PROJECT_STATE_ID = '32d31e4fdf10808fbc52f7d6061da723'
PJ_STATUS_DB_ID  = '9d74cf694098491c8527deb5fafa98d6'
PIPELINE_DB_ID   = 'a25b228ca90e41e587a48d2627256262'
JST              = timezone(timedelta(hours=9))

HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

# ── Notion API helpers ──────────────────────────────────────────

def get_blocks(block_id):
    blocks, cursor = [], None
    while True:
        params = {'page_size': 100}
        if cursor:
            params['start_cursor'] = cursor
        r = requests.get(f'https://api.notion.com/v1/blocks/{block_id}/children',
                         headers=HEADERS, params=params)
        data = r.json()
        if r.status_code != 200:
            print(f'[WARN] blocks {block_id}: {data}')
            break
        blocks.extend(data.get('results', []))
        if data.get('has_more'):
            cursor = data['next_cursor']
        else:
            break
    return blocks

def query_database(db_id):
    r = requests.post(f'https://api.notion.com/v1/databases/{db_id}/query',
                      headers=HEADERS, json={'page_size': 100})
    data = r.json()
    if r.status_code != 200:
        print(f'[WARN] db {db_id}: {data}')
        return []
    return data.get('results', [])

def plain(rt_list):
    return ''.join(x.get('plain_text', '') for x in rt_list)

def to_html(rt_list):
    out = ''
    for rt in rt_list:
        t = (rt.get('plain_text', '')
             .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        a = rt.get('annotations', {})
        if a.get('bold'):   t = f'<strong>{t}</strong>'
        if a.get('italic'): t = f'<em>{t}</em>'
        if a.get('code'):   t = f'<code>{t}</code>'
        if rt.get('href'):  t = f'<a href="{rt["href"]}" target="_blank">{t}</a>'
        out += t
    return out

def prop_val(prop):
    pt = prop.get('type', '')
    if pt == 'title':       return plain(prop['title'])
    if pt == 'rich_text':   return plain(prop['rich_text'])
    if pt == 'select':      return (prop['select'] or {}).get('name', '')
    if pt == 'status':      return (prop['status'] or {}).get('name', '')
    if pt == 'multi_select':return ', '.join(s['name'] for s in prop.get('multi_select', []))
    if pt == 'date':        d = prop.get('date'); return d['start'] if d else ''
    if pt == 'number':      n = prop.get('number'); return n if n is not None else None
    if pt == 'checkbox':    return prop.get('checkbox', False)
    if pt == 'url':         return prop.get('url', '')
    return ''

# ── Block → HTML ────────────────────────────────────────────────

def blocks_to_html(blocks, pj_tag=False):
    html, i = '', 0
    while i < len(blocks):
        b = blocks[i]; bt = b['type']
        if bt == 'paragraph':
            t = to_html(b['paragraph']['rich_text'])
            if t:
                tag_html = detect_pj_tag(t) if pj_tag else t
                html += f'<p>{tag_html}</p>'
        elif bt in ('heading_1', 'heading_2', 'heading_3'):
            lv = bt[-1]
            t = to_html(b[bt]['rich_text'])
            html += f'<h{lv}>{t}</h{lv}>'
        elif bt == 'bulleted_list_item':
            items = []
            while i < len(blocks) and blocks[i]['type'] == 'bulleted_list_item':
                t = to_html(blocks[i]['bulleted_list_item']['rich_text'])
                tag_html = detect_pj_tag(t) if pj_tag else t
                items.append(f'<li>{tag_html}</li>')
                i += 1
            html += '<ul>' + ''.join(items) + '</ul>'
            continue
        elif bt == 'numbered_list_item':
            items = []
            while i < len(blocks) and blocks[i]['type'] == 'numbered_list_item':
                t = to_html(blocks[i]['numbered_list_item']['rich_text'])
                tag_html = detect_pj_tag(t) if pj_tag else t
                items.append(f'<li>{tag_html}</li>')
                i += 1
            html += '<ol>' + ''.join(items) + '</ol>'
            continue
        elif bt == 'table':
            rows = get_blocks(b['id'])
            has_h = b['table'].get('has_column_header', False)
            html += '<table>'
            for j, row in enumerate(rows):
                cells = row['table_row']['cells']
                tag = 'th' if (j == 0 and has_h) else 'td'
                html += '<tr>' + ''.join(f'<{tag}>{to_html(c)}</{tag}>' for c in cells) + '</tr>'
            html += '</table>'
        elif bt == 'callout':
            t = to_html(b['callout']['rich_text'])
            icon = (b['callout'].get('icon') or {})
            emoji = icon.get('emoji', '💡') if icon.get('type') == 'emoji' else '💡'
            html += f'<div class="callout">{emoji} {t}</div>'
        elif bt == 'quote':
            t = to_html(b['quote']['rich_text'])
            html += f'<blockquote>{t}</blockquote>'
        elif bt == 'divider':
            html += '<hr>'
        i += 1
    return html

def detect_pj_tag(text):
    """先頭の①②③等を検出してバッジ化"""
    m = re.match(r'^([①②③④⑤⑥横])', text)
    if m:
        tag = m.group(1)
        colors = {'①': 'tag-meta', '②': 'tag-dir', '③': 'tag-sns',
                  '④': 'tag-over', '⑤': 'tag-dev', '横': 'tag-cross'}
        cls = colors.get(tag, 'tag-meta')
        rest = text[len(tag):]
        return f'<span class="pj-badge {cls}">{tag}</span>{rest}'
    return text

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

# ── Deadline color ───────────────────────────────────────────────

def deadline_class(date_str):
    if not date_str:
        return ''
    try:
        today = datetime.now(JST).date()
        d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
        diff = (d - today).days
        if diff < 0:
            return 'dl-overdue'
        elif diff <= 7:
            return 'dl-week'
        elif diff <= 31:
            return 'dl-month'
    except Exception:
        pass
    return ''

def render_deadline(blocks):
    """期限テーブルにPJタグと色分けを適用"""
    html, i = '', 0
    while i < len(blocks):
        b = blocks[i]; bt = b['type']
        if bt == 'table':
            rows = get_blocks(b['id'])
            has_h = b['table'].get('has_column_header', False)
            html += '<table class="deadline-table">'
            for j, row in enumerate(rows):
                cells = row['table_row']['cells']
                if j == 0 and has_h:
                    html += '<thead><tr>' + ''.join(f'<th>{to_html(c)}</th>' for c in cells) + '</tr></thead><tbody>'
                else:
                    date_text = plain(cells[0]) if cells else ''
                    cls = deadline_class(date_text)
                    html += f'<tr class="{cls}">'
                    for ci, c in enumerate(cells):
                        t = to_html(c)
                        if ci == 1:
                            t = detect_pj_tag(t)
                        html += f'<td>{t}</td>'
                    html += '</tr>'
            html += '</tbody></table>'
        elif bt == 'bulleted_list_item':
            items = []
            while i < len(blocks) and blocks[i]['type'] == 'bulleted_list_item':
                t = to_html(blocks[i]['bulleted_list_item']['rich_text'])
                items.append(f'<li>{detect_pj_tag(t)}</li>')
                i += 1
            html += '<ul>' + ''.join(items) + '</ul>'
            continue
        else:
            html += blocks_to_html([b])
        i += 1
    return html

# ── PJ Status cards ─────────────────────────────────────────────

STATUS_COLOR = {
    '🟢実行モード': 'status-green',
    '🔄リセット中': 'status-yellow',
    '🟡準備中':     'status-orange',
    '🔴停止中':     'status-red',
    '⚫完了':        'status-gray',
}

def render_pj_cards(records):
    if not records:
        return '<p class="empty">データなし</p>'
    # 並び順でソート
    def sort_key(r):
        n = r['properties'].get('並び順', {})
        v = prop_val(n)
        return v if v is not None else 99
    records = sorted(records, key=sort_key)

    cards = ''
    for r in records:
        p = r['properties']
        name      = prop_val(p.get('PJ名', {})) or '—'
        status    = prop_val(p.get('状態', {})) or ''
        metrics   = prop_val(p.get('主要メトリクス', {})) or ''
        next_step = prop_val(p.get('次フェーズ・次にやること', {})) or ''
        phase     = prop_val(p.get('現フェーズ', {})) or ''
        risk      = prop_val(p.get('課題・リスク', {})) or ''
        link      = prop_val(p.get('詳細リンク', {})) or ''
        rev_act   = prop_val(p.get('月収益_実績', {}))
        rev_tgt   = prop_val(p.get('月収益_目標', {}))
        ns_name   = prop_val(p.get('NS指標_名称', {})) or ''
        ns_act    = prop_val(p.get('NS指標_実績', {}))

        status_cls = STATUS_COLOR.get(status, 'status-gray')
        link_html  = f'<a href="{link}" target="_blank" class="detail-link">詳細 →</a>' if link else ''

        # 月収益バー
        rev_html = ''
        if rev_act is not None and rev_tgt:
            pct = min(int(rev_act / rev_tgt * 100), 100)
            rev_html = f'''
            <div class="kpi-row">
              <span class="kpi-label">月収益</span>
              <span class="kpi-val">¥{int(rev_act):,}</span>
              <span class="kpi-target"> / 目標 ¥{int(rev_tgt):,}</span>
            </div>
            <div class="prog-bar"><div class="prog-fill" style="width:{pct}%"></div></div>'''
        elif rev_act is not None:
            rev_html = f'<div class="kpi-row"><span class="kpi-label">月収益</span><span class="kpi-val">¥{int(rev_act):,}</span></div>'

        # NS指標
        ns_html = ''
        if ns_name:
            ns_val = f'{int(ns_act):,}' if ns_act is not None else '—'
            ns_html = f'<div class="kpi-row"><span class="kpi-label">{ns_name}</span><span class="kpi-val">{ns_val}</span></div>'

        def row(label, val):
            if not val: return ''
            # 改行文字を<br>に変換
            val = val.replace('\n', '<br>')
            return f'<div class="pj-row"><span class="row-label">{label}</span><span class="row-val">{val}</span></div>'

        cards += f'''
        <div class="pj-card">
          <div class="pj-card-head">
            <div class="pj-name">{name}</div>
            <div class="pj-right">
              <span class="status-badge {status_cls}">{status}</span>
              {link_html}
            </div>
          </div>
          {rev_html}
          {ns_html}
          {row("主要メトリクス", metrics)}
          {row("次にやること", next_step)}
          {row("現フェーズ", phase)}
          {row("課題・リスク", risk)}
        </div>'''
    return cards

# ── Pipeline ────────────────────────────────────────────────────

def render_pipeline(records):
    if not records:
        return '<p class="empty">データなし</p>'

    active, applying = [], []
    for r in records:
        p = r['properties']
        status = ''
        for k, v in p.items():
            if v.get('type') == 'status' or 'ステータス' in k:
                status = prop_val(v)
                break
        title = next((prop_val(v) for v in p.values() if v.get('type') == 'title'), '(無題)')
        reward = prop_val(p.get('契約金額(税込)', {})) or prop_val(p.get('報酬条件', {})) or ''
        platform = prop_val(p.get('契約プラットフォーム', {})) or prop_val(p.get('プラットフォーム', {})) or ''
        item = (title, status, reward, platform)
        if any(kw in status for kw in ['受注', '採用', '稼働', '契約', '検収']):
            active.append(item)
        else:
            applying.append(item)

    def card(title, status, reward, platform):
        info = ' · '.join(x for x in [platform, reward] if x)
        return f'''<div class="pipeline-card">
          <div class="pl-status">{status}</div>
          <div class="pl-title">{title}</div>
          {"<div class='pl-info'>" + info + "</div>" if info else ""}
        </div>'''

    html = ''
    if active:
        html += '<div class="pl-section-label">受注済み · 稼働中</div>'
        html += '<div class="pipeline-grid">' + ''.join(card(*i) for i in active) + '</div>'
    if applying:
        html += '<div class="pl-section-label" style="margin-top:16px">応募中 · 選考中</div>'
        html += '<div class="pipeline-grid">' + ''.join(card(*i) for i in applying) + '</div>'
    return html

# ── KPI summary cards ────────────────────────────────────────────

def render_kpi_summary(records):
    """上部のKPIサマリーカード群"""
    def sort_key(r):
        n = r['properties'].get('並び順', {})
        v = prop_val(n)
        return v if v is not None else 99
    records = sorted(records, key=sort_key)

    cards = ''
    total_rev = 0
    for r in records:
        p = r['properties']
        name    = prop_val(p.get('PJ名', {})) or '—'
        rev_act = prop_val(p.get('月収益_実績', {}))
        rev_tgt = prop_val(p.get('月収益_目標', {}))
        ns_name = prop_val(p.get('NS指標_名称', {})) or ''
        ns_act  = prop_val(p.get('NS指標_実績', {}))
        status  = prop_val(p.get('状態', {})) or ''

        if rev_act is not None:
            total_rev += rev_act

        if rev_act is None and not ns_name:
            continue  # 数値なし・NS指標なしはスキップ

        pct_html = ''
        if rev_act is not None and rev_tgt:
            pct = min(int(rev_act / rev_tgt * 100), 100)
            pct_html = f'<div class="kpi-pct">{pct}%</div><div class="prog-bar"><div class="prog-fill" style="width:{pct}%"></div></div>'

        rev_disp = f'¥{int(rev_act):,}' if rev_act is not None else '—'
        ns_disp  = f'{int(ns_act):,}' if ns_act is not None else '—'

        cards += f'''<div class="kpi-card">
          <div class="kpi-card-name">{name}</div>
          {"<div class='kpi-big'>" + rev_disp + "</div>" if rev_act is not None else ""}
          {"<div class='kpi-sub'>" + f"目標 ¥{int(rev_tgt):,}" + "</div>" if rev_tgt else ""}
          {pct_html}
          {"<div class='kpi-ns'><span class='kpi-ns-label'>" + ns_name + "</span><span class='kpi-ns-val'>" + ns_disp + "</span></div>" if ns_name else ""}
        </div>'''

    # 全PJ合算
    if total_rev > 0:
        cards = f'''<div class="kpi-card kpi-total">
          <div class="kpi-card-name">全PJ 月収益合計</div>
          <div class="kpi-big">¥{int(total_rev):,}</div>
        </div>''' + cards

    return cards or '<p class="empty">まだ数値が入力されていません</p>'

# ── Chart data ───────────────────────────────────────────────────

def build_chart_data(records):
    def sort_key(r):
        n = r['properties'].get('並び順', {})
        v = prop_val(n)
        return v if v is not None else 99
    records = sorted(records, key=sort_key)
    labels, actuals, targets = [], [], []
    for r in records:
        p = r['properties']
        name    = prop_val(p.get('PJ名', {})) or '—'
        rev_act = prop_val(p.get('月収益_実績', {}))
        rev_tgt = prop_val(p.get('月収益_目標', {}))
        if rev_act is not None or rev_tgt is not None:
            labels.append(name)
            actuals.append(int(rev_act) if rev_act is not None else 0)
            targets.append(int(rev_tgt) if rev_tgt is not None else 0)
    return labels, actuals, targets

# ── Main HTML builder ────────────────────────────────────────────

def build(all_blocks, pj_records, pipeline_records):
    top5_html    = blocks_to_html(get_section(all_blocks, 'TOP5'))
    watch_blocks = get_section(all_blocks, '監視')
    watch_html   = blocks_to_html(watch_blocks, pj_tag=True)
    dl_blocks    = get_section(all_blocks, '期限')
    deadline_html= render_deadline(dl_blocks)
    kpi_html     = render_kpi_summary(pj_records)
    pj_html      = render_pj_cards(pj_records)
    pipe_html    = render_pipeline(pipeline_records)

    labels, actuals, targets = build_chart_data(pj_records)
    import json
    chart_json = json.dumps({'labels': labels, 'actuals': actuals, 'targets': targets})

    now = datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hiro PROJECT Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg:        #f2f4f7;
  --surface:   #ffffff;
  --surface2:  #f7f8fa;
  --border:    #dde1e9;
  --border2:   #c5cad6;
  --blue:      #005bac;
  --blue-light:#deeaf8;
  --blue-dark: #004080;
  --orange:    #c45d00;
  --orange-bg: #fdebd8;
  --teal:      #006e73;
  --teal-bg:   #d4f0f1;
  --green:     #1a6b3a;
  --green-bg:  #d4edde;
  --red:       #b91c1c;
  --red-bg:    #fee2e2;
  --yellow:    #854d0e;
  --yellow-bg: #fef9c3;
  --gray:      #4b5563;
  --text:      #111827;
  --text2:     #374151;
  --muted:     #6b7280;
  --tag-bg:    #e5e7eb;
  --prog-bg:   #e5e7eb;
  --prog-fill: #005bac;
}}
*{{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background:var(--bg); color:var(--text);
  font-family:'Noto Sans JP',sans-serif; font-size:15px; line-height:1.7;
}}

/* ── Header ── */
header {{
  background:var(--blue); color:#fff;
  padding:14px 28px; display:flex; align-items:center;
  justify-content:space-between; position:sticky; top:0; z-index:99;
  box-shadow:0 2px 8px rgba(0,0,0,.2);
}}
.logo {{ font-family:'IBM Plex Mono',monospace; font-size:13px; font-weight:600; letter-spacing:.1em; }}
.meta {{ font-family:'IBM Plex Mono',monospace; font-size:11px; opacity:.8; }}

/* ── Nav ── */
nav {{
  background:var(--blue-dark); padding:0 28px;
  display:flex; gap:0; overflow-x:auto;
}}
nav a {{
  color:rgba(255,255,255,.8); text-decoration:none;
  font-size:12px; font-weight:500; padding:10px 16px;
  white-space:nowrap; border-bottom:2px solid transparent;
  transition:.15s;
}}
nav a:hover {{ color:#fff; border-color:#fff; }}

/* ── Layout ── */
.grid {{
  display:grid; grid-template-columns:1fr 1fr;
  gap:18px; padding:22px 26px; max-width:1440px; margin:0 auto;
}}
.card {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:22px 24px;
  box-shadow:0 1px 4px rgba(0,0,0,.06);
}}
.card.full {{ grid-column:1/-1; }}
.card-title {{
  font-size:11px; font-weight:700; color:var(--muted);
  letter-spacing:.14em; text-transform:uppercase;
  margin-bottom:16px; padding-bottom:12px;
  border-bottom:2px solid var(--border);
}}

/* ── Typography ── */
p {{ color:var(--text2); margin-bottom:8px; font-size:15px; }}
h1,h2,h3 {{ color:var(--text); margin:12px 0 6px; font-size:15px; font-weight:700; }}
ol,ul {{ padding-left:20px; }}
ol li,ul li {{ margin-bottom:8px; color:var(--text2); font-size:15px; }}
ol li strong,ul li strong {{ color:var(--text); font-weight:700; }}
a {{ color:var(--blue); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
code {{
  background:var(--tag-bg); padding:2px 6px; border-radius:4px;
  font-family:'IBM Plex Mono',monospace; font-size:12px;
}}
hr {{ border:none; border-top:1px solid var(--border); margin:12px 0; }}
blockquote {{
  border-left:3px solid var(--border2); padding:6px 12px;
  color:var(--muted); font-size:14px; margin:8px 0;
  background:var(--surface2); border-radius:0 6px 6px 0;
}}
.callout {{
  background:var(--blue-light); border-left:4px solid var(--blue);
  padding:10px 14px; border-radius:0 8px 8px 0;
  margin:8px 0; color:var(--text2); font-size:14px;
}}
.empty {{ color:var(--muted); font-size:14px; }}

/* ── Table ── */
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
thead {{ background:var(--surface2); }}
th {{
  padding:10px 12px; text-align:left; font-weight:700;
  font-size:12px; color:var(--text); border-bottom:2px solid var(--border);
  white-space:nowrap;
}}
td {{
  padding:10px 12px; border-bottom:1px solid var(--border);
  color:var(--text2); vertical-align:top; font-size:14px;
}}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:var(--surface2); }}

/* ── Deadline colors ── */
.dl-overdue td:first-child {{ color:var(--red); font-weight:700; }}
.dl-overdue {{ background:var(--red-bg); }}
.dl-week td:first-child {{ color:var(--orange); font-weight:700; }}
.dl-week {{ background:var(--orange-bg); }}
.dl-month td:first-child {{ color:var(--yellow); font-weight:700; }}
.dl-month {{ background:var(--yellow-bg); }}

/* ── PJ Badge ── */
.pj-badge {{
  display:inline-block; font-size:11px; font-weight:700;
  padding:1px 7px; border-radius:20px; margin-right:5px;
  vertical-align:middle;
}}
.tag-meta  {{ background:#dbeafe; color:#1e40af; }}
.tag-dir   {{ background:#dcfce7; color:#166534; }}
.tag-sns   {{ background:#fce7f3; color:#9d174d; }}
.tag-over  {{ background:#fed7aa; color:#9a3412; }}
.tag-dev   {{ background:#ede9fe; color:#5b21b6; }}
.tag-cross {{ background:#e5e7eb; color:#374151; }}

/* ── KPI Summary ── */
.kpi-row-container {{
  display:flex; flex-wrap:wrap; gap:14px; margin-bottom:4px;
}}
.kpi-card {{
  background:var(--surface2); border:1px solid var(--border);
  border-radius:10px; padding:18px 20px; min-width:200px; flex:1;
}}
.kpi-total {{
  border-color:var(--blue); background:var(--blue-light);
}}
.kpi-card-name {{
  font-size:12px; font-weight:700; color:var(--muted);
  letter-spacing:.06em; margin-bottom:8px;
}}
.kpi-big {{
  font-family:'IBM Plex Mono',monospace; font-size:28px;
  font-weight:600; color:var(--text); line-height:1.2;
}}
.kpi-total .kpi-big {{ color:var(--blue-dark); }}
.kpi-sub {{ font-size:12px; color:var(--muted); margin-top:2px; }}
.kpi-pct {{
  font-size:13px; font-weight:700; color:var(--blue);
  margin-top:8px;
}}
.kpi-ns {{
  margin-top:10px; display:flex; align-items:baseline; gap:8px;
}}
.kpi-ns-label {{ font-size:12px; color:var(--muted); }}
.kpi-ns-val {{
  font-family:'IBM Plex Mono',monospace; font-size:18px;
  font-weight:600; color:var(--text);
}}

/* ── Progress bar ── */
.prog-bar {{
  background:var(--prog-bg); border-radius:4px;
  height:6px; margin-top:6px; overflow:hidden;
}}
.prog-fill {{
  background:var(--prog-fill); height:100%; border-radius:4px;
  transition:.3s ease;
}}

/* ── PJ Cards ── */
.pj-card {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:18px 20px; margin-bottom:14px;
}}
.pj-card:last-child {{ margin-bottom:0; }}
.pj-card-head {{
  display:flex; align-items:flex-start; justify-content:space-between;
  margin-bottom:12px; gap:12px;
}}
.pj-name {{
  font-size:17px; font-weight:700; color:var(--text);
  white-space:nowrap;
}}
.pj-right {{ display:flex; align-items:center; gap:10px; flex-shrink:0; }}
.status-badge {{
  font-size:12px; font-weight:700; padding:3px 10px;
  border-radius:20px; white-space:nowrap;
}}
.status-green  {{ background:var(--green-bg);  color:var(--green); }}
.status-yellow {{ background:var(--yellow-bg); color:var(--yellow); }}
.status-orange {{ background:var(--orange-bg); color:var(--orange); }}
.status-red    {{ background:var(--red-bg);    color:var(--red); }}
.status-gray   {{ background:var(--tag-bg);    color:var(--gray); }}
.detail-link {{ font-size:12px; color:var(--blue); white-space:nowrap; }}

.kpi-row {{
  display:flex; align-items:baseline; gap:6px; margin-top:8px;
}}
.kpi-label {{ font-size:12px; color:var(--muted); }}
.kpi-val   {{ font-family:'IBM Plex Mono',monospace; font-size:16px; font-weight:600; color:var(--text); }}
.kpi-target{{ font-size:12px; color:var(--muted); }}

.pj-row {{
  display:grid; grid-template-columns:110px 1fr;
  gap:8px; padding:8px 0; border-top:1px solid var(--border);
  font-size:14px;
}}
.row-label {{ color:var(--muted); font-size:13px; font-weight:500; padding-top:1px; }}
.row-val   {{ color:var(--text2); white-space:pre-wrap; word-break:break-word; }}

/* ── Pipeline ── */
.pl-section-label {{
  font-size:12px; font-weight:700; color:var(--muted);
  letter-spacing:.08em; text-transform:uppercase; margin-bottom:10px;
}}
.pipeline-grid {{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr));
  gap:12px;
}}
.pipeline-card {{
  background:var(--surface2); border:1px solid var(--border);
  border-radius:8px; padding:14px 16px;
}}
.pl-status {{
  font-size:11px; font-weight:700; color:var(--orange);
  background:var(--orange-bg); display:inline-block;
  padding:2px 8px; border-radius:20px; margin-bottom:7px;
}}
.pl-title {{ font-size:14px; font-weight:700; color:var(--text); line-height:1.45; }}
.pl-info  {{ font-size:12px; color:var(--muted); margin-top:5px; }}

/* ── Chart ── */
.chart-wrap {{ position:relative; height:220px; }}

/* ── Deadline table ── */
.deadline-table {{ table-layout:auto; }}
.deadline-table td {{ word-break:break-word; }}
.deadline-table td:first-child {{ white-space:nowrap; min-width:70px; }}

/* ── Responsive ── */
@media(max-width:768px){{
  .grid {{ grid-template-columns:1fr; padding:12px; gap:12px; }}
  .card.full {{ grid-column:1; }}
  body {{ font-size:14px; }}
  .pj-name {{ font-size:15px; white-space:normal; }}
  .kpi-big {{ font-size:22px; }}
}}
</style>
</head>
<body>

<header>
  <div class="logo">HIRO / PROJECT DASHBOARD</div>
  <div class="meta">最終更新: {now}</div>
</header>

<nav>
  <a href="#kpi">KPI</a>
  <a href="#top5">TOP5</a>
  <a href="#watch">監視</a>
  <a href="#deadline">期限</a>
  <a href="#pjstatus">全PJ</a>
  <a href="#pipeline">案件</a>
</nav>

<div class="grid">

  <!-- KPI Summary -->
  <div class="card full" id="kpi">
    <div class="card-title">📈 KPI サマリー</div>
    <div class="kpi-row-container">{kpi_html}</div>
  </div>

  <!-- Chart -->
  <div class="card full" id="chart">
    <div class="card-title">📊 月収益グラフ（実績 vs 目標）</div>
    <div class="chart-wrap"><canvas id="revChart"></canvas></div>
  </div>

  <!-- TOP5 -->
  <div class="card" id="top5">
    <div class="card-title">🎯 今日 / 今週 TOP5</div>
    {top5_html or '<p class="empty">データなし</p>'}
  </div>

  <!-- 監視 -->
  <div class="card" id="watch">
    <div class="card-title">⚠️ 監視・連絡待ち</div>
    {watch_html or '<p class="empty">データなし</p>'}
  </div>

  <!-- 期限 -->
  <div class="card full" id="deadline">
    <div class="card-title">📅 期限あり項目
      <span style="font-size:11px;font-weight:400;margin-left:10px;">
        <span style="color:#b91c1c">■</span>過去  
        <span style="color:#c45d00">■</span>今週  
        <span style="color:#854d0e">■</span>今月
      </span>
    </div>
    {deadline_html or '<p class="empty">データなし</p>'}
  </div>

  <!-- 全PJ -->
  <div class="card full" id="pjstatus">
    <div class="card-title">📋 全PJステータス</div>
    {pj_html}
  </div>

  <!-- 案件パイプライン -->
  <div class="card full" id="pipeline">
    <div class="card-title">② 案件パイプライン</div>
    {pipe_html}
  </div>

</div>

<script>
(function(){{
  var d = {chart_json};
  if(!d.labels.length) return;
  var ctx = document.getElementById('revChart').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: d.labels,
      datasets: [
        {{
          label: '実績 (¥)',
          data: d.actuals,
          backgroundColor: 'rgba(0,91,172,0.75)',
          borderRadius: 5,
        }},
        {{
          label: '目標 (¥)',
          data: d.targets,
          backgroundColor: 'rgba(196,93,0,0.35)',
          borderColor: 'rgba(196,93,0,0.8)',
          borderWidth: 2,
          borderRadius: 5,
          type: 'bar',
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ position:'top', labels:{{ font:{{size:13}}, color:'#374151' }} }},
        tooltip: {{
          callbacks: {{
            label: function(ctx){{
              return ctx.dataset.label + ': ¥' + ctx.parsed.y.toLocaleString();
            }}
          }}
        }}
      }},
      scales: {{
        y: {{
          beginAtZero: true,
          ticks: {{
            callback: function(v){{ return '¥' + v.toLocaleString(); }},
            color: '#6b7280', font:{{size:12}}
          }},
          grid: {{ color:'#dde1e9' }}
        }},
        x: {{
          ticks: {{ color:'#374151', font:{{size:13}} }},
          grid: {{ display:false }}
        }}
      }}
    }}
  }});
}})();
</script>

</body>
</html>'''

# ── Main ────────────────────────────────────────────────────────

def main():
    print('Fetching PROJECT_STATE...')
    blocks = get_blocks(PROJECT_STATE_ID)
    print(f'  → {len(blocks)} blocks')

    print('Querying PJ Status DB...')
    pj = query_database(PJ_STATUS_DB_ID)
    print(f'  → {len(pj)} records')

    print('Querying Pipeline DB...')
    pipeline = query_database(PIPELINE_DB_ID)
    print(f'  → {len(pipeline)} records')

    print('Building HTML...')
    html = build(blocks, pj, pipeline)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Done → index.html ({len(html):,} bytes)')

if __name__ == '__main__':
    main()
