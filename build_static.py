#!/usr/bin/env python3
"""
Build a static site from extracted appropriations data.
Generates JSON data files and an HTML page for GitHub Pages.
"""

import json
import os
import re
from collections import defaultdict
from report_finder import KNOWN_REPORTS, get_congress_number

EXTRACTED_DIR = "extracted"
OUTPUT_DIR = "docs"

# Common agency abbreviation mappings for search
ABBREVIATIONS = {
    "FBI": "Federal Bureau of Investigation",
    "NIH": "National Institutes of Health",
    "CDC": "Centers for Disease Control",
    "EPA": "Environmental Protection Agency",
    "DOD": "Department of Defense",
    "DOJ": "Department of Justice",
    "FEMA": "Federal Emergency Management Agency",
    "NASA": "National Aeronautics and Space Administration",
    "NSF": "National Science Foundation",
    "NOAA": "National Oceanic and Atmospheric",
    "FAA": "Federal Aviation Administration",
    "FCC": "Federal Communications Commission",
    "SEC": "Securities and Exchange Commission",
    "FDA": "Food and Drug Administration",
    "IRS": "Internal Revenue Service",
    "ATF": "Bureau of Alcohol, Tobacco, Firearms",
    "DEA": "Drug Enforcement Administration",
    "USDA": "Department of Agriculture",
    "HHS": "Health and Human Services",
    "HUD": "Housing and Urban Development",
    "DOE": "Department of Energy",
    "DOI": "Department of the Interior",
    "DOT": "Department of Transportation",
    "DOS": "Department of State",
    "DHS": "Department of Homeland Security",
    "VA": "Department of Veterans Affairs",
    "GPO": "Government Publishing Office",
    "GAO": "Government Accountability Office",
    "CBO": "Congressional Budget Office",
    "LOC": "Library of Congress",
    "AOC": "Architect of the Capitol",
    "USCP": "Capitol Police",
    "CRS": "Congressional Research Service",
    "NIST": "National Institute of Standards",
    "USGS": "Geological Survey",
    "BLM": "Bureau of Land Management",
    "NPS": "National Park Service",
    "USFS": "Forest Service",
    "NRCS": "Natural Resources Conservation",
    "FSA": "Farm Service Agency",
    "SNAP": "Supplemental Nutrition",
    "WIC": "Women, Infants, and Children",
    "CHIP": "Children's Health Insurance",
    "SSA": "Social Security Administration",
    "OSHA": "Occupational Safety and Health",
    "TSA": "Transportation Security Administration",
    "CBP": "Customs and Border Protection",
    "ICE": "Immigration and Customs Enforcement",
    "USCIS": "Citizenship and Immigration",
    "FHWA": "Federal Highway Administration",
    "FRA": "Federal Railroad Administration",
    "FTA": "Federal Transit Administration",
    "USACE": "Army Corps of Engineers",
    "SBA": "Small Business Administration",
}


def get_pdf_url(subcommittee, fiscal_year, source_type):
    """Get the congress.gov URL for the source PDF."""
    key = (fiscal_year, subcommittee)
    if key not in KNOWN_REPORTS:
        return None
    reports = KNOWN_REPORTS[key]
    report_num = reports.get(source_type)
    if not report_num:
        return None

    congress = get_congress_number(fiscal_year)
    prefix = "hrpt" if source_type == "house" else "srpt"
    return f"https://www.congress.gov/{congress}/crpt/{prefix}{report_num}/CRPT-{congress}{prefix}{report_num}.pdf"


def get_report_number(subcommittee, fiscal_year, source_type):
    """Get the report number string (e.g., 'H. Rept. 119-178')."""
    key = (fiscal_year, subcommittee)
    if key not in KNOWN_REPORTS:
        return None
    reports = KNOWN_REPORTS[key]
    report_num = reports.get(source_type)
    if not report_num:
        return None

    congress = get_congress_number(fiscal_year)
    prefix = "H. Rept." if source_type == "house" else "S. Rept."
    return f"{prefix} {congress}-{report_num}"


def build():
    os.makedirs(os.path.join(OUTPUT_DIR, "data"), exist_ok=True)

    all_data = []
    for filename in sorted(os.listdir(EXTRACTED_DIR)):
        if filename.endswith('.json') and not filename.startswith('debug'):
            filepath = os.path.join(EXTRACTED_DIR, filename)
            with open(filepath) as f:
                data = json.load(f)

            # Enrich with source PDF info
            meta = data['metadata']
            pdf_url = get_pdf_url(meta['subcommittee'], meta['fiscal_year'], meta['source_type'])
            report_num = get_report_number(meta['subcommittee'], meta['fiscal_year'], meta['source_type'])
            if pdf_url:
                meta['pdf_url'] = pdf_url
            if report_num:
                meta['report_number'] = report_num

            all_data.append(data)

    # Build summary
    summary = defaultdict(lambda: defaultdict(list))
    total_items = 0
    for d in all_data:
        meta = d['metadata']
        num = len(d.get('line_items', []))
        total_items += num
        summary[meta['subcommittee']][meta['fiscal_year']].append({
            'source_type': meta['source_type'],
            'num_items': num,
            'columns': d.get('columns', []),
            'report_number': meta.get('report_number', ''),
            'pdf_url': meta.get('pdf_url', ''),
        })

    with open(os.path.join(OUTPUT_DIR, "data", "summary.json"), 'w') as f:
        json.dump(dict(summary), f)

    # Write individual data files
    for d in all_data:
        meta = d['metadata']
        safe_sub = re.sub(r'[^a-z0-9]+', '_', meta['subcommittee'].lower()).strip('_')
        filename = f"{safe_sub}_{meta['fiscal_year'].lower()}_{meta['source_type']}.json"
        with open(os.path.join(OUTPUT_DIR, "data", filename), 'w') as f:
            json.dump(d, f)

    # Data index
    index = {}
    for d in all_data:
        meta = d['metadata']
        sub = meta['subcommittee']
        if sub not in index:
            index[sub] = []
        safe_sub = re.sub(r'[^a-z0-9]+', '_', sub.lower()).strip('_')
        filename = f"{safe_sub}_{meta['fiscal_year'].lower()}_{meta['source_type']}.json"
        index[sub].append({
            'fiscal_year': meta['fiscal_year'],
            'source_type': meta['source_type'],
            'filename': filename,
            'num_items': len(d.get('line_items', [])),
            'report_number': meta.get('report_number', ''),
            'pdf_url': meta.get('pdf_url', ''),
        })

    with open(os.path.join(OUTPUT_DIR, "data", "index.json"), 'w') as f:
        json.dump(index, f)

    # Abbreviations for search
    with open(os.path.join(OUTPUT_DIR, "data", "abbreviations.json"), 'w') as f:
        json.dump(ABBREVIATIONS, f)

    # Build HTML
    build_html(OUTPUT_DIR, summary, total_items, len(all_data))

    subs = len(summary)
    years = len(set(fy for fys in summary.values() for fy in fys))
    print(f"Built static site in {OUTPUT_DIR}/")
    print(f"  {subs} subcommittees, {len(all_data)} reports, {total_items:,} line items, {years} fiscal years")


def build_html(output_dir, summary, total_items, total_reports):
    years = sorted(set(fy for fys in summary.values() for fy in fys), reverse=True)

    cards_html = ""
    for sub in sorted(summary.keys()):
        fys = summary[sub]
        badges = ""
        for fy in sorted(fys.keys(), reverse=True):
            for src in fys[fy]:
                cls = src['source_type']
                label = f"{fy} {src['source_type'][0].upper()}"
                badges += f'<span class="badge {cls}">{label}</span>'
        cards_html += f'''
        <div class="scd" onclick="openSub('{sub}')">
            <h3>{sub}</h3>
            <div class="mr">{badges}</div>
        </div>'''

    # The full HTML with all improvements from DC feedback
    with open(os.path.join(output_dir, "index.html"), 'w') as f:
        f.write(generate_html(cards_html, total_items, total_reports, len(summary), len(years)))


def generate_html(cards_html, total_items, total_reports, num_subs, num_years):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Appropriations Line Items Explorer</title>
<meta name="description" content="Browse Congressional appropriations spending data by line item. Extracted from committee report PDFs covering all 12 appropriations subcommittees.">
<style>
:root{{--navy:#1a2744;--blue:#2a5298;--lb:#3d7edb;--pb:#e8f0fe;--bg:#f5f7fa;--card:#fff;--bdr:#dce3ed;--txt:#2c3e50;--txtl:#7f8c9b;--grn:#27ae60;--red:#c0392b;--sh:0 1px 4px rgba(0,0,0,.08);--shm:0 4px 12px rgba(0,0,0,.1)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--txt);line-height:1.6}}
header{{background:linear-gradient(135deg,var(--navy),var(--blue));color:#fff;padding:1.1rem 2rem;box-shadow:0 2px 8px rgba(0,0,0,.2);position:sticky;top:0;z-index:100}}
.hi{{max-width:1500px;margin:0 auto;display:flex;align-items:center;justify-content:space-between}}
header h1{{font-size:1.25rem;font-weight:600}}
.sub{{font-size:.8rem;opacity:.7;margin-top:.1rem}}
.hs{{display:flex;align-items:center;background:rgba(255,255,255,.15);border-radius:6px;padding:.35rem .75rem}}
.hs input{{background:0 0;border:0;color:#fff;font-size:.85rem;width:280px;outline:0}}
.hs input::placeholder{{color:rgba(255,255,255,.5)}}
.ct{{max-width:1500px;margin:0 auto;padding:1.25rem 1.5rem}}
.sr{{display:flex;gap:.75rem;margin-bottom:1rem;flex-wrap:wrap}}
.sc{{background:var(--card);border-radius:8px;padding:.75rem 1rem;flex:1;min-width:150px;box-shadow:var(--sh);display:flex;align-items:center;gap:.75rem}}
.si{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}}
.si.bl{{background:var(--pb)}}.si.gn{{background:#e8f5e9}}.si.gd{{background:#fff8e1}}.si.rd{{background:#fce4ec}}
.sl{{font-size:.68rem;color:var(--txtl);text-transform:uppercase;letter-spacing:.5px}}
.sv{{font-size:1.4rem;font-weight:700;color:var(--navy);line-height:1.2}}
.sd{{position:fixed;top:55px;right:20px;width:500px;max-height:420px;overflow-y:auto;background:#fff;border-radius:8px;box-shadow:var(--shm);z-index:200;display:none}}
.sd.act{{display:block}}
.sri{{padding:.55rem 1rem;border-bottom:1px solid var(--bdr);cursor:pointer;font-size:.82rem}}
.sri:hover{{background:#f8fafc}}
.srn{{font-weight:500}}.srm{{font-size:.72rem;color:var(--txtl)}}.sra{{font-weight:600;color:var(--navy)}}
.st{{font-size:.95rem;font-weight:600;margin-bottom:.75rem;color:var(--navy)}}
.sg{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.7rem;margin-bottom:1.5rem}}
.scd{{background:var(--card);border-radius:8px;padding:.9rem;box-shadow:var(--sh);cursor:pointer;transition:transform .12s,box-shadow .12s;border-left:3px solid var(--blue)}}
.scd:hover{{transform:translateY(-1px);box-shadow:var(--shm)}}
.scd h3{{font-size:.87rem;margin-bottom:.35rem;color:var(--navy)}}
.mr{{display:flex;flex-wrap:wrap;gap:.25rem}}
.bd{{display:inline-block;padding:.08rem .4rem;border-radius:10px;font-size:.62rem;font-weight:500}}
.bd.house{{background:#e3f2fd;color:#1565c0}}.bd.senate{{background:#fce4ec;color:#c62828}}.bd.conference{{background:#e8f5e9;color:#2e7d32}}
.vw{{background:var(--card);border-radius:8px;box-shadow:var(--shm);margin-bottom:1.5rem;display:none;overflow:hidden}}
.vw.act{{display:block}}
.vh{{padding:.7rem 1.2rem;background:var(--navy);color:#fff;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}}
.vh h2{{font-size:.95rem;font-weight:600}}
.vh .rpt{{font-size:.72rem;opacity:.7}}
.vh .rpt a{{color:#8bb8ff;text-decoration:none}}
.vh .rpt a:hover{{text-decoration:underline}}
.vc{{display:flex;gap:.4rem;align-items:center}}
.btn{{padding:.28rem .65rem;border-radius:5px;border:1px solid rgba(255,255,255,.3);background:0 0;color:#fff;cursor:pointer;font-size:.75rem;transition:background .15s}}
.btn:hover{{background:rgba(255,255,255,.15)}}
.bcl{{background:0 0;border:0;color:#fff;font-size:1.3rem;cursor:pointer;opacity:.7;line-height:1}}
.bcl:hover{{opacity:1}}
.tb{{display:flex;background:#f0f4f8;border-bottom:1px solid var(--bdr);overflow-x:auto}}
.t{{padding:.45rem .9rem;cursor:pointer;font-size:.78rem;font-weight:500;color:var(--txtl);white-space:nowrap;border-bottom:2px solid transparent;transition:all .15s}}
.t:hover{{color:var(--txt)}}.t.act{{color:var(--blue);border-bottom-color:var(--blue);background:#fff}}
.tw{{overflow-x:auto;max-height:70vh;overflow-y:auto}}
.dt{{width:100%;border-collapse:collapse;font-size:.78rem}}
.dt th{{background:var(--navy);color:#fff;padding:.45rem .65rem;text-align:right;white-space:nowrap;position:sticky;top:0;z-index:10;font-size:.72rem}}
.dt th:first-child{{text-align:left;min-width:280px;position:sticky;left:0;z-index:11}}
.dt td{{padding:.28rem .65rem;border-bottom:1px solid #eef1f5;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.dt td:first-child{{text-align:left;position:sticky;left:0;background:inherit;z-index:5}}
.dt tr:hover td{{background:#f0f5ff!important}}
.dt tr.lv0{{font-weight:700}}.dt tr.lv0 td{{background:#edf2f7;border-top:2px solid var(--bdr)}}
.dt tr.lv1{{font-weight:600}}.dt tr.lv1 td{{background:#f5f8fb}}
.dt tr.hl td{{background:#fff3cd!important}}
.in0{{padding-left:.7rem!important}}.in1{{padding-left:1.5rem!important}}.in2{{padding-left:2.3rem!important}}.in3{{padding-left:3.1rem!important}}
.neg{{color:var(--red)}}
footer{{text-align:center;padding:1.5rem;color:var(--txtl);font-size:.72rem;border-top:1px solid var(--bdr);margin-top:2rem}}
footer a{{color:var(--blue);text-decoration:none}}
.ab{{background:var(--card);border-radius:8px;padding:1.1rem 1.2rem;box-shadow:var(--sh);margin-bottom:1rem;font-size:.82rem;line-height:1.65;border-left:3px solid var(--blue)}}
.ab h3{{font-size:.9rem;margin-bottom:.4rem;color:var(--navy)}}
.ab ul{{margin:.4rem 0;padding-left:1.4rem}}.ab li{{margin-bottom:.2rem}}
@media(max-width:768px){{.hs input{{width:150px}}.sg{{grid-template-columns:1fr}}.sr{{flex-direction:column}}.sd{{width:calc(100vw - 20px);right:10px}}}}
</style>
</head>
<body>
<header><div class="hi"><div><h1>Appropriations Line Items Explorer</h1><div class="sub">Congressional spending data extracted from committee reports</div></div>
<div class="hs"><span style="opacity:.5;margin-right:.5rem">&#128269;</span><input type="text" id="gs" placeholder="Search line items (try FBI, NASA, Capitol Police...)" oninput="doSearch(this.value)"></div></div></header>
<div class="sd" id="sd"></div>
<div class="ct">
<div class="ab"><h3>About This Tool</h3>
<p>This tool extracts line-item spending data from the <strong>Comparative Statement of New Budget Authority</strong>
tables published in Congressional appropriations committee reports. Data is automatically extracted from
<a href="https://www.congress.gov/crs-appropriations-status-table">committee report PDFs on congress.gov</a>.</p>
<ul>
<li>Click a subcommittee to view its line items, with tabs for each fiscal year and chamber</li>
<li>Search across all reports by program name or common abbreviations (FBI, NASA, EPA, etc.)</li>
<li>Export any table as CSV for spreadsheet analysis</li>
<li>Click the report number link to view the original source PDF</li>
</ul>
<p>Amounts are in <strong>thousands of dollars</strong>.</p></div>
<div class="sr">
<div class="sc"><div class="si bl">&#127963;</div><div><div class="sl">Subcommittees</div><div class="sv">{num_subs}</div></div></div>
<div class="sc"><div class="si gn">&#128196;</div><div><div class="sl">Reports</div><div class="sv">{total_reports}</div></div></div>
<div class="sc"><div class="si gd">&#128200;</div><div><div class="sl">Line Items</div><div class="sv">{total_items:,}</div></div></div>
<div class="sc"><div class="si rd">&#128197;</div><div><div class="sl">Fiscal Years</div><div class="sv">{num_years}</div></div></div>
</div>
<div class="vw" id="vw">
<div class="vh"><div><h2 id="vt"></h2><div class="rpt" id="vrpt"></div></div>
<div class="vc"><button class="btn" onclick="exportCSV()">&#8615; Export CSV</button><button class="bcl" onclick="closeV()">&times;</button></div></div>
<div class="tb" id="tabs"></div>
<div class="tw"><table class="dt"><thead id="th"></thead><tbody id="tbody"></tbody></table></div>
</div>
<div class="st">Appropriations Subcommittees</div>
<div class="sg">{cards_html}</div>
<footer>Data from <a href="https://www.congress.gov/crs-appropriations-status-table" target="_blank">congress.gov</a> committee reports. Amounts in thousands of dollars. Extracted using Claude AI from PDF tables.</footer>
</div>
<script>
let cD=null,cS=null,dI=null,aSD=[],abbr={{}};
fetch('data/index.json').then(r=>r.json()).then(i=>{{dI=i;
const ps=[];for(const[s,fs] of Object.entries(i))for(const f of fs)ps.push(fetch('data/'+f.filename).then(r=>r.json()));
Promise.all(ps).then(d=>{{aSD=d}});}});
fetch('data/abbreviations.json').then(r=>r.json()).then(a=>{{abbr=a}}).catch(()=>{{}});

function openSub(n){{if(!dI||!dI[n])return;cS=n;
const v=document.getElementById('vw');v.classList.add('act');
document.getElementById('vt').textContent=n;
document.getElementById('tbody').innerHTML='<tr><td colspan="10" style="text-align:center;padding:2rem;color:#999">Loading...</td></tr>';
document.getElementById('th').innerHTML='';document.getElementById('tabs').innerHTML='';
document.getElementById('vrpt').innerHTML='';
const fs=[...dI[n]].sort((a,b)=>b.fiscal_year.localeCompare(a.fiscal_year)||a.source_type.localeCompare(b.source_type));
Promise.all(fs.map(f=>fetch('data/'+f.filename).then(r=>r.json()))).then(ds=>{{
const tabs=document.getElementById('tabs');tabs.innerHTML='';
ds.forEach((d,i)=>{{const t=document.createElement('div');
t.className='t'+(i===0?' act':'');
const s=d.metadata.source_type;
t.textContent=d.metadata.fiscal_year+' '+s.charAt(0).toUpperCase()+s.slice(1);
t.onclick=()=>{{document.querySelectorAll('.t').forEach(x=>x.classList.remove('act'));t.classList.add('act');renderT(d);}};
tabs.appendChild(t);}});renderT(ds[0]);}});
v.scrollIntoView({{behavior:'smooth',block:'start'}})}}

function renderT(d){{cD=d;
const h=document.getElementById('th'),b=document.getElementById('tbody');
// Show report info
const m=d.metadata;
let rptHtml='';
if(m.report_number){{rptHtml=m.report_number;if(m.pdf_url)rptHtml='<a href="'+m.pdf_url+'" target="_blank">'+m.report_number+' &#8599;</a>';}}
if(m.table_pages)rptHtml+=' (Table: pp. '+m.table_pages.join(', ')+')';
document.getElementById('vrpt').innerHTML=rptHtml;
let hr='<tr><th>Line Item</th>';for(const c of d.columns)hr+='<th>'+esc(c)+'</th>';hr+='</tr>';h.innerHTML=hr;
let br='';for(const it of d.line_items){{const lv=it.level||0;
br+='<tr class="lv'+lv+'" data-name="'+esc(it.name).toLowerCase()+'"><td class="in'+lv+'">'+esc(it.name)+'</td>';
for(const a of it.amounts){{if(a===null||a===undefined)br+='<td></td>';else br+='<td class="'+(a<0?'neg':'')+'">'+fmt(a)+'</td>';}}
br+='</tr>';}}b.innerHTML=br;}}

function fmt(n){{if(n===null||n===undefined)return'';if(n===0)return'---';const a=Math.abs(n);return n<0?'('+a.toLocaleString()+')':a.toLocaleString()}}
function esc(t){{const d=document.createElement('div');d.textContent=t;return d.innerHTML}}
function closeV(){{document.getElementById('vw').classList.remove('act')}}
function exportCSV(){{if(!cD)return;let c='Line Item,Level,'+cD.columns.join(',')+String.fromCharCode(10);
for(const it of cD.line_items){{const ind='  '.repeat(it.level||0);
let r='"'+ind+it.name.replace(/"/g,'""')+'",'+(it.level||0);
for(const a of it.amounts)r+=','+(a!==null&&a!==undefined?a:'');c+=r+String.fromCharCode(10);}}
const bl=new Blob([c],{{type:'text/csv'}});const u=URL.createObjectURL(bl);const a=document.createElement('a');
a.href=u;a.download=cD.metadata.subcommittee.replace(/ /g,'_')+'_'+cD.metadata.fiscal_year+'_'+cD.metadata.source_type+'.csv';
a.click();URL.revokeObjectURL(u)}}

let sT=null;
function doSearch(q){{clearTimeout(sT);const dr=document.getElementById('sd');
if(q.length<2){{dr.classList.remove('act');return;}}
sT=setTimeout(()=>{{
let ql=q.toLowerCase();
// Check abbreviations
let expanded=null;
for(const[ab,full] of Object.entries(abbr)){{if(ab.toLowerCase()===ql){{expanded=full.toLowerCase();break;}}}}
const results=[];
for(const d of aSD){{const m=d.metadata;const cols=d.columns||[];
let ri=2;for(let i=0;i<cols.length;i++){{const cl=cols[i].toLowerCase();if((cl.includes('bill')||cl.includes('recommend'))&&!cl.includes('vs')){{ri=i;break;}}}}
for(const it of d.line_items||[]){{if(!it.name)continue;const nl=it.name.toLowerCase();
if(nl.includes(ql)||(expanded&&nl.includes(expanded))){{
const amt=it.amounts&&ri<it.amounts.length?it.amounts[ri]:null;
results.push({{name:it.name,sub:m.subcommittee,fy:m.fiscal_year,src:m.source_type,amt}});
if(results.length>=40)break;}}}}if(results.length>=40)break;}}
if(!results.length)dr.innerHTML='<div class="sri"><span class="srm">No results'+(expanded?' (searched: '+q.toUpperCase()+' = '+expanded+')':'')+'</span></div>';
else{{let h='';if(expanded)h+='<div class="sri" style="background:#f8f8f0"><span class="srm">Showing results for <b>'+q.toUpperCase()+'</b> ('+expanded+')</span></div>';
for(const r of results){{const aS=r.amt!==null?'$'+fmt(r.amt)+'K':'';
h+='<div class="sri" onclick="openSubAndHL(\\''+esc(r.sub)+'\\',\\''+esc(r.name.replace(/'/g,"\\\\'"))+'\\')"><div class="srn">'+esc(r.name)+'</div><div class="srm">'+r.sub+' | '+r.fy+' '+r.src+(aS?' | <span class="sra">'+aS+'</span>':'')+'</div></div>';}}
dr.innerHTML=h;}}dr.classList.add('act');}},300)}}

function openSubAndHL(sub,name){{
document.getElementById('sd').classList.remove('act');
openSub(sub);
// After data loads, scroll to and highlight the matching row
setTimeout(()=>{{
const rows=document.querySelectorAll('#tbody tr');
const nl=name.toLowerCase();
for(const row of rows){{
if(row.dataset.name&&row.dataset.name.includes(nl.substring(0,30))){{
row.classList.add('hl');row.scrollIntoView({{behavior:'smooth',block:'center'}});
setTimeout(()=>row.classList.remove('hl'),3000);break;}}}}
}},800);}}

document.addEventListener('click',e=>{{if(!e.target.closest('.hs')&&!e.target.closest('.sd'))document.getElementById('sd').classList.remove('act')}});
</script>
</body>
</html>'''


if __name__ == "__main__":
    build()
