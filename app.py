import hmac
import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq

st.set_page_config(page_title="Business Assistant", page_icon="📊", layout="wide")

st.title("📊 Small Business Assistant")
st.caption("Upload your sales file and get instant insights.")
def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None


def check_password():
    if st.session_state.get("authed"):
        return True
    correct = get_secret("APP_PASSWORD")
    if not correct:
        st.error("No app password set. Add APP_PASSWORD to secrets.toml.")
        return False
    pwd = st.text_input("Password", type="password")
    if st.button("Log in"):
        if hmac.compare_digest(pwd, correct):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False

if not check_password():
    st.stop()

# ---- Sidebar ----
# ---- Sidebar ----
with st.sidebar:
    st.header("Setup")
    uploaded = st.file_uploader("Sales file", type=["csv", "xlsx"])
    api_key = get_secret("GROQ_API_KEY")
    if not api_key:
        api_key = st.text_input("Groq API key", type="password")

if not uploaded:
    st.info("👈 Upload a sales file in the sidebar to begin. "
            "Columns needed: date, product, quantity, amount, customer.")
    st.stop()

st.info(f"📁 Analyzing file: {uploaded.name}")

st.info(f"📁 Analyzing file: {uploaded.name}")

# ---- Load and clean ----
if uploaded.name.endswith(".csv"):
    df = pd.read_csv(uploaded)
else:
    df = pd.read_excel(uploaded)
cols = list(df.columns)
with st.sidebar:
    st.subheader("Match your columns")
    date_col = st.selectbox("Date column", cols)
    amount_col = st.selectbox("Sales amount column", cols)
    product_col = st.selectbox("Product column", cols)
    customer_col = st.selectbox("Customer column (optional)", ["(none)"] + cols)

picked = [date_col, amount_col, product_col]
names = ["date", "amount", "product"]
if customer_col != "(none)":
    picked.append(customer_col)
    names.append("customer")

if len(set(picked)) < len(picked):
    st.warning("Pick a different column for each box in the sidebar.")
    st.stop()

df = df[picked].copy()
df.columns = names

df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["amount"] = pd.to_numeric(
    df["amount"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
    errors="coerce",
)
df = df.dropna(subset=["date", "amount"])

if df.empty:
    st.error("No valid rows found. Check that the date and amount columns are right.")
    st.stop()
# ---- Calculations ----
total_revenue = df["amount"].sum()
total_orders = len(df)
avg_order = df["amount"].mean()

df["month"] = df["date"].dt.to_period("M")
monthly = df.groupby("month")["amount"].sum()
monthly_df = monthly.reset_index()
monthly_df["month"] = monthly_df["month"].astype(str)

full = monthly.copy()
first_date, last_date = df["date"].min(), df["date"].max()
if first_date.day > 1:
    full = full.drop(first_date.to_period("M"), errors="ignore")
if last_date.day < last_date.days_in_month:
    full = full.drop(last_date.to_period("M"), errors="ignore")

has_comparison = len(full) >= 2 and full.iloc[-2] > 0
comparison_text = "Not enough full months of data to compare."

if has_comparison:
    latest_month, prev_month = full.index[-1], full.index[-2]
    latest, prev = full.iloc[-1], full.iloc[-2]
    change = (latest - prev) / prev * 100

    both = df[df["month"].isin([prev_month, latest_month])]
    pm = both.pivot_table(index="product", columns="month",
                          values="amount", aggfunc="sum", fill_value=0)
    pm["change"] = pm[latest_month] - pm[prev_month]
    biggest_gain = pm["change"].idxmax()
    biggest_drop = pm["change"].idxmin()

    comparison_text = (
        f"Latest full month {latest_month}: {latest:.2f}. "
        f"Previous full month {prev_month}: {prev:.2f}. "
        f"Change: {change:+.1f}%. "
        f"Biggest product gain: {biggest_gain} ({pm['change'].max():.0f}). "
        f"Biggest product drop: {biggest_drop} ({pm['change'].min():.0f}). "
        "Partial months at the start and end are excluded."
    )

top_products = (df.groupby("product")["amount"].sum()
                .sort_values(ascending=False).head(5))

customers_text = "No customer column"
top_customers = None
if "customer" in df.columns:
    top_customers = (df.groupby("customer")["amount"].sum()
                     .sort_values(ascending=False).head(5))
    customers_text = top_customers.to_string()

summary = f"""
Total revenue: {total_revenue:.2f}
Orders: {total_orders}
Average order: {avg_order:.2f}
Date range: {first_date.date()} to {last_date.date()}

Month comparison:
{comparison_text}

Revenue by month (first and last may be partial):
{monthly.to_string()}

Top products by revenue:
{top_products.to_string()}

Top customers by revenue:
{customers_text}
"""

# ---- Tabs ----
tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 Overview", "🏆 Products & Customers", "💬 Ask AI", "🗂 Data"]
)

with tab1:
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.metric("Total revenue", f"${total_revenue:,.0f}")
    with c2:
        with st.container(border=True):
            st.metric("Orders", total_orders)
    with c3:
        with st.container(border=True):
            st.metric("Average order", f"${avg_order:,.2f}")

    st.subheader("Revenue by month")
    fig = px.bar(monthly_df, x="month", y="amount",
                 labels={"month": "Month", "amount": "Revenue"})
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Month vs month")
    if has_comparison:
        with st.container(border=True):
            st.metric(f"{latest_month} revenue", f"${latest:,.0f}",
                      f"{change:+.1f}% vs {prev_month}")
            if change <= -20:
                st.error("Alert: revenue dropped 20% or more.")
            elif change >= 20:
                st.success("Great news: revenue grew 20% or more.")
            else:
                st.info("Revenue is fairly steady.")
            st.write(f"📈 Biggest gain: **{biggest_gain}** (+{pm['change'].max():,.0f})")
            st.write(f"📉 Biggest drop: **{biggest_drop}** ({pm['change'].min():,.0f})")
    else:
        st.info("Not enough full months of data to compare yet.")

with tab2:
    left, right = st.columns(2)
    with left:
        st.subheader("Top 5 products")
        fig2 = px.bar(top_products.reset_index(), x="amount", y="product",
                      orientation="h", labels={"amount": "Revenue", "product": ""})
        fig2.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    with right:
        st.subheader("Top customers")
        if top_customers is not None:
            fig3 = px.pie(top_customers.reset_index(), names="customer",
                          values="amount", hole=0.4)
            fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No customer column in this file.")

with tab3:
    st.subheader("Ask a question about your business")
    st.caption("Try: Why did revenue change last month? Which product should I focus on?")
    question = st.text_input("Your question")

    if st.button("Ask", type="primary") and question:
        if not api_key:
            st.warning("Paste your Groq API key in the sidebar first.")
        else:
            with st.spinner("Thinking..."):
                try:
                    client = Groq(api_key=api_key)
                    reply = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        max_tokens=800,
                        messages=[
                            {"role": "system", "content": (
                                "You are a business assistant for a small business owner. "
                                "Answer using ONLY the data summary provided. "
                                "If the data can't answer the question, say so. "
                                "Never invent numbers. Use simple, plain language "
                                "and finish with one practical suggestion."
                            )},
                            {"role": "user",
                             "content": f"Data summary:\n{summary}\n\nQuestion: {question}"},
                        ],
                    )
                    answer = reply.choices[0].message.content
                    with st.container(border=True):
                        st.write(answer.replace("$", "\\$"))
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

with tab4:
    st.caption(f"{len(df)} rows loaded")
    st.dataframe(df, use_container_width=True)
