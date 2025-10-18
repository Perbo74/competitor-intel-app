import json, pytz, pandas as pd, streamlit as st
from datetime import datetime
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------- Basic config ----------
st.set_page_config(page_title="Competitor Intelligence", layout="wide")
TZ = pytz.timezone(st.secrets.get("general", {}).get("timezone", "Europe/Berlin"))

# ---------- Google clients (Service Account) ----------
def get_sa_creds():
    sa_json = st.secrets.get("google", {}).get("service_account_json")
    if not sa_json:
        st.stop()
    return service_account.Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

@st.cache_resource
def get_gspread_client():
    creds = get_sa_creds()
    return gspread.authorize(creds)

@st.cache_resource
def get_drive_service():
    creds = get_sa_creds()
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def ensure_sheets(sh):
    needed = ["competitors","files","financial_runs","financial_metrics","news"]
    existing = [w.title for w in sh.worksheets()]
    for name in needed:
        if name not in existing:
            sh.add_worksheet(title=name, rows=100, cols=26)

def read_sheet(gc, sheet_id, name):
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(name)
    return ws.get_all_records()

def upsert_sheet(gc, sheet_id, name, rows):
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(name)
    if not rows:
        return
    headers = list(rows[0].keys())
    data = [headers] + [[r.get(h, "") for h in headers] for r in rows]
    ws.update('A1', data)

# ---------- UI pages ----------
def page_competitors(gc, sheet_id):
    st.header("Competitors")
    sh = gc.open_by_key(sheet_id)
    ensure_sheets(sh)
    rows = read_sheet(gc, sheet_id, "competitors")
    df = pd.DataFrame(rows)
    st.subheader("Database")
    st.dataframe(df if not df.empty else pd.DataFrame({"info":["No rows yet"]}))

    st.subheader("Add / Edit")
    with st.form("comp_form", clear_on_submit=True):
        name = st.text_input("Name")
        website = st.text_input("Website")
        ir_url = st.text_input("IR URL")
        news_rss = st.text_input("News RSS (optional)")
        linkedin_url = st.text_input("LinkedIn (optional)")
        tickers = st.text_input("Tickers (comma-separated)")
        currency = st.text_input("Currency (e.g., EUR)")
        fiscal_notes = st.text_input("Fiscal calendar notes")
        drive_folder_id = st.text_input("Drive folder ID (optional now)")
        tags = st.text_input("Tags (comma-separated)")
        submitted = st.form_submit_button("Save")
        if submitted:
            new = {
                "id": (name.lower().replace(" ","-") if name else ""),
                "name": name, "website": website, "ir_url": ir_url, "news_rss": news_rss,
                "linkedin_url": linkedin_url, "tickers": tickers, "currency": currency,
                "fiscal_calendar_notes": fiscal_notes, "drive_folder_id": drive_folder_id,
                "tags": tags, "active(bool)": True, "created_at": "", "updated_at": ""
            }
            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True) if not df.empty else pd.DataFrame([new])
            upsert_sheet(gc, sheet_id, "competitors", df.to_dict(orient="records"))
            st.success("Saved!")

def page_library(drive_service, top_folder_id):
    st.header("Library (Google Drive)")
    if not top_folder_id:
        st.info("Set google.drive_top_folder_id in secrets and share that folder with your Service Account.")
        return
    q = f"'{top_folder_id}' in parents and trashed=false"
    resp = drive_service.files().list(q=q, fields="files(id,name,mimeType,webViewLink)").execute()
    items = resp.get("files", [])
    if not items:
        st.write("No items yet. Create a subfolder per competitor and drop files there.")
    for it in items:
        st.write(f"- [{it['name']}]({it.get('webViewLink')}) — {it['mimeType']}")

def page_automations():
    st.header("Automations (coming in Phase 2)")
    st.write("Here you’ll later have buttons to trigger:")
    st.markdown("- Financials: Discover→Download\n- Financials: Parse→Summarize\n- Biweekly News\n- Deck Builder")
    st.info("We’ll add an OpenAI Agent + a simple scheduler in Phase 2.")

def page_reports(gc, sheet_id):
    st.header("Reports")
    try:
        fm = pd.DataFrame(read_sheet(gc, sheet_id, "financial_metrics"))
    except Exception:
        fm = pd.DataFrame()
    try:
        news = pd.DataFrame(read_sheet(gc, sheet_id, "news"))
    except Exception:
        news = pd.DataFrame()
    st.subheader("Financial metrics")
    st.dataframe(fm if not fm.empty else pd.DataFrame({"info":["No data yet"]}))
    st.subheader("News")
    st.dataframe(news if not news.empty else pd.DataFrame({"info":["No data yet"]}))

# ---------- App frame ----------
def main():
    st.sidebar.title("Competitor Intelligence")
    st.sidebar.caption(f"Local time: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}")
    tz_info = st.secrets.get('general', {}).get('timezone', 'Europe/Berlin')
    st.sidebar.write(f"Timezone: {tz_info}")

    sheet_id = st.secrets.get("google", {}).get("sheet_id", "")
    drive_top_folder_id = st.secrets.get("google", {}).get("drive_top_folder_id", "")

    page = st.sidebar.radio("Navigate", ["Competitors", "Library", "Automations", "Reports"])

    gc = get_gspread_client()
    drive_service = get_drive_service()

    if page == "Competitors":
        page_competitors(gc, sheet_id)
    elif page == "Library":
        page_library(drive_service, drive_top_folder_id)
    elif page == "Automations":
        page_automations()
    else:
        page_reports(gc, sheet_id)

    st.sidebar.markdown("---")
    st.sidebar.write(f"Google Sheet ID: {sheet_id or 'unset'}")
    st.sidebar.write(f"Drive folder: {drive_top_folder_id or 'unset'}")

if __name__ == "__main__":
    main()
