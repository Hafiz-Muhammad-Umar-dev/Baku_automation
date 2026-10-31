import os
import re
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

# ============================================================
#  CONFIG
# ============================================================
SERPER_API_KEY = "5153246e876a07847c8de6a3d062f1da31ee31a5"   # <-- put your serper.dev key here
SERPER_API_KEY = SERPER_API_KEY if SERPER_API_KEY != "PASTE_YOUR_SERPER_API_KEY_HERE" else os.getenv("SERPER_API_KEY", "")

ONLY_SOCIAL_PLATFORMS = True    # keep only links from the selected social platforms
DEFAULT_PAGES = 2               # Google pages per search (10 results each)

PLATFORM_WORDS = {
    "Facebook": "facebook", "LinkedIn": "linkedin", "Instagram": "instagram",
    "Telegram": "telegram", "Reddit": "reddit", "X / Twitter": "twitter",
    "TikTok": "tiktok", "Threads": "threads",
}
DOMAIN_TO_PLATFORM = {
    "facebook.com": "Facebook", "fb.com": "Facebook", "linkedin.com": "LinkedIn",
    "instagram.com": "Instagram", "threads.com": "Threads", "threads.net": "Threads",
    "t.me": "Telegram", "reddit.com": "Reddit", "x.com": "X / Twitter",
    "twitter.com": "X / Twitter", "tiktok.com": "TikTok",
}
# Property listing portals = sellers/agents, never leads
BLOCKED_DOMAINS = [
    "bina.az", "tap.az", "lalafo", "emlak.az", "yeniemlak.az", "rent.az", "olx.", "domofond",
    "airbnb.", "booking.com", "zillow.", "rightmove.",
]

DEFAULT_SEARCHES = """looking for apartment in Baku
need apartment for rent in Baku
looking to buy apartment in Baku
need house in Baku
ищу квартиру в Баку
сниму квартиру в Баку
куплю квартиру в Баку
Bakıda kirayə mənzil axtarıram
Bakıda ev almaq istəyirəm"""

SEEKER_TERMS = [
    "looking for", "looking to", "need a", "need an", "need apartment", "need flat", "need house",
    "need room", "want to rent", "want to buy", "searching for", "wanted", "anyone know",
    "can anyone recommend", "any recommendations", "help me find",
    "ищу", "сниму", "куплю", "нужна", "нужен", "ищем", "снимем", "подскажите",
    "axtarıram", "axtarıb", "axtarırıq", "lazımdır", "lazimdir", "istəyirəm", "istəyirik", "tövsiyə",
]
STRONG_SELLER_TERMS = [
    "for sale", "for rent", "to let", "available now", "contact us", "call us", "dm for details",
    "сдам", "сдаётся", "сдается", "сдаю", "сдаем", "продам", "продаётся", "продается", "продаю",
    "satılır", "satilir", "kirayə verilir", "kiraye verilir", "kirayəyə verilir", "kirayədir",
    "realtor", "real estate agency", "real estate company", "риелтор", "риэлтор", "агентство",
    "makler", "rieltor", "emlak ofisi",
]
WEAK_SELLER_TERMS = [
    "available", "furnished", "deposit", "per month", "/month", "azn", "₼", "m2", "м2", "sqm", "usd",
]

PHONE_RE = re.compile(
    r"(?:\+?\s?994|\b0)[\s\-\(]*(?:10|12|50|51|55|60|70|77|99)[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
)

# ============================================================
#  HELPERS
# ============================================================
def is_seller_or_agent(text):
    t = text.lower()
    seeker = sum(1 for x in SEEKER_TERMS if x in t)
    strong = sum(1 for x in STRONG_SELLER_TERMS if x in t)
    weak = sum(1 for x in WEAK_SELLER_TERMS if x in t)
    seller_score = strong + (1 if weak >= 2 else 0)
    if seeker == 0 and seller_score >= 1:
        return True
    if seller_score >= seeker + 2:
        return True
    return False

def detect_platform(url):
    host = urlparse(url).netloc.lower().replace("www.", "").replace("m.", "")
    for dom, name in DOMAIN_TO_PLATFORM.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host or "Other"

def is_blocked_url(url):
    u = url.lower()
    return any(b in u for b in BLOCKED_DOMAINS) or "/marketplace/" in u

def detect_language(text):
    if re.search(r"[а-яА-ЯёЁ]", text):
        return "Russian"
    if re.search(r"[əƏğıİöÖşŞüÜçÇ]", text):
        return "Azerbaijani"
    return "English"

def classify_type(text):
    t = text.lower()
    if any(x in t for x in ["rent", "kirayə", "kiraye", "icarə", "аренд", "снять", "сниму"]):
        return "Rent"
    if any(x in t for x in ["buy", "purchase", "almaq", "купить", "куплю", "покупка"]):
        return "Buy"
    return "Other"

def extract_phone(text):
    return ", ".join(sorted({re.sub(r"[^\d+]", "", m.group(0)) for m in PHONE_RE.finditer(text)}))

def search_serper(query, page):
    body = {"q": query, "gl": "az", "num": 10, "page": page}
    if time_tbs:
        body["tbs"] = time_tbs
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Serper HTTP {r.status_code}: {r.text[:150]}")
    return r.json().get("organic", [])

# ============================================================
#  PAGE
# ============================================================
st.set_page_config(page_title="Baku Real Estate Leads", page_icon="🏠", layout="wide")
st.title("🏠 Baku Real Estate Leads")
st.caption("People looking to rent or buy property in Baku, found from public social media posts.")

if "leads" not in st.session_state:
    st.session_state.leads = []

st.sidebar.header("Search")
searches_input = st.sidebar.text_area("Searches (one per line)", value=DEFAULT_SEARCHES, height=220)
platforms = st.sidebar.multiselect(
    "Platforms", list(PLATFORM_WORDS.keys()), default=["Facebook", "LinkedIn", "Instagram", "Telegram"]
)
period = st.sidebar.selectbox("Posted", ["Any time", "Past week", "Past month", "Past year"], index=0)
time_tbs = {"Any time": "", "Past week": "qdr:w", "Past month": "qdr:m", "Past year": "qdr:y"}[period]

searches = [s.strip() for s in searches_input.splitlines() if s.strip()]

if st.button("🔍 Find Leads", type="primary", use_container_width=True):
    if not SERPER_API_KEY:
        st.error("Search service is not configured. Add the Serper API key in main.py.")
    elif not searches or not platforms:
        st.warning("Please enter at least one search and select at least one platform.")
    else:
        queries = [f"{s} {PLATFORM_WORDS[p]}" for s in searches for p in platforms]
        bar = st.progress(0.0, text="Searching...")
        raw, failed = [], 0
        total = len(queries) * DEFAULT_PAGES
        done = 0
        stop = False
        for q in queries:
            if stop:
                break
            for pg in range(1, DEFAULT_PAGES + 1):
                done += 1
                bar.progress(min(done / total, 1.0), text="Searching...")
                try:
                    items = search_serper(q, pg)
                    raw.extend(items)
                    if len(items) < 5:
                        break
                except Exception as e:
                    failed += 1
                    print("Search error:", q, e)          # details go to the terminal only
                    if "401" in str(e) or "403" in str(e):
                        st.error("Search service key is invalid or out of credits.")
                        stop = True
                    break
        bar.empty()

        existing = {l["Link"] for l in st.session_state.leads}
        added = 0
        for it in raw:
            url = it.get("link", "")
            if not url or url in existing or is_blocked_url(url):
                continue
            platform = detect_platform(url)
            if ONLY_SOCIAL_PLATFORMS and platform not in platforms:
                continue
            title, snippet = it.get("title", ""), it.get("snippet", "")
            full = f"{title} {snippet}"
            if is_seller_or_agent(full):
                continue
            st.session_state.leads.append({
                "Platform": platform,
                "Type": classify_type(full),
                "Language": detect_language(full),
                "Post": f"{title} — {snippet}" if snippet else title,
                "Phone": extract_phone(full),
                "Date": it.get("date", ""),
                "Link": url,
            })
            existing.add(url)
            added += 1
        if failed and not added:
            st.warning("Search could not be completed. Please try again.")
        else:
            st.success(f"{added} new leads found.")

# ---------------- RESULTS ----------------
st.divider()
df = pd.DataFrame(st.session_state.leads)

if df.empty:
    st.info("No leads yet. Click “Find Leads” to start.")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Leads", len(df))
    m2.metric("Looking to Rent", int((df["Type"] == "Rent").sum()))
    m3.metric("Looking to Buy", int((df["Type"] == "Buy").sum()))
    m4.metric("With Phone Number", int((df["Phone"] != "").sum()))

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        f_platform = st.multiselect("Platform", sorted(df["Platform"].unique()))
    with c2:
        f_type = st.multiselect("Type", sorted(df["Type"].unique()))
    with c3:
        f_text = st.text_input("Search in posts", placeholder="e.g. 2 rooms, city center...")

    view = df.copy()
    if f_platform:
        view = view[view["Platform"].isin(f_platform)]
    if f_type:
        view = view[view["Type"].isin(f_type)]
    if f_text:
        view = view[view["Post"].str.contains(f_text, case=False, na=False)]

    st.caption(f"Showing {len(view)} leads")
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={"Link": st.column_config.LinkColumn("Post Link", display_text="Open post")},
    )
    st.download_button("📥 Download CSV", data=view.to_csv(index=False).encode("utf-8-sig"),
                       file_name="baku_leads.csv", mime="text/csv")