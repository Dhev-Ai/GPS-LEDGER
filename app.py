import os
import datetime as dt
from typing import List, Optional
import hashlib
import pathlib

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import streamlit as st

# Database path for SQLite
DB_PATH = pathlib.Path(__file__).parent / "gps_ledger.db"

st.set_page_config(
    page_title="GPS Ledger · Expense Studio",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY_COLOR = "#7c3aed"
ACCENT_COLOR = "#0ea5e9"
BACKGROUND_GRADIENT = "linear-gradient(135deg, #0f172a 0%, #1d1b52 50%, #0b1120 100%)"
CURRENCY = "₹"  # Indian Rupees

# Default expense categories
DEFAULT_EXPENSE_CATEGORIES = [
    "🍔 Food & Dining",
    "🛒 Shopping",
    "🚗 Transport",
    "🏠 Housing & Rent",
    "💡 Utilities & Bills",
    "🎓 Education",
    "🏥 Healthcare",
    "🎬 Entertainment",
    "✈️ Travel",
    "👕 Clothing",
    "💼 Business",
    "🎁 Gifts",
    "📱 Subscriptions",
    "🏋️ Fitness",
    "📦 Miscellaneous"
]

# Default income categories
DEFAULT_INCOME_CATEGORIES = [
    "💰 Salary",
    "💼 Freelance",
    "📈 Investments",
    "🏦 Interest",
    "🎁 Gifts Received",
    "💵 Bonus",
    "🏠 Rental Income",
    "📊 Dividends",
    "💻 Side Business",
    "🎯 Commission",
    "💸 Refunds",
    "🎲 Lottery/Winnings",
    "📦 Other Income"
]

# Combined for backward compatibility
DEFAULT_CATEGORIES = DEFAULT_EXPENSE_CATEGORIES


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@st.cache_resource(show_spinner=False)
def get_engine():
    # Use SQLite for simplicity and cloud deployment
    url = f"sqlite:///{DB_PATH}"
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(engine):
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        color TEXT DEFAULT '#38bdf8',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        transaction_type TEXT DEFAULT 'expense',
        occurred_on DATE NOT NULL,
        description TEXT NOT NULL,
        category_id INTEGER,
        payment_method TEXT DEFAULT 'card',
        amount DECIMAL(12,2) NOT NULL,
        tags TEXT,
        receipt_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category_id INTEGER,
        month_start DATE NOT NULL,
        monthly_limit DECIMAL(12,2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, category_id, month_start),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS savings_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        goal_name TEXT NOT NULL,
        target_amount DECIMAL(12,2) NOT NULL,
        current_amount DECIMAL(12,2) DEFAULT 0,
        deadline DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """
    with engine.connect() as conn:
        for statement in ddl.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))
        conn.commit()
    
    # Migration: Add transaction_type column if it doesn't exist (for existing databases)
    with engine.connect() as conn:
        # Check if transaction_type column exists
        result = conn.execute(text("PRAGMA table_info(transactions)"))
        columns = [row[1] for row in result.fetchall()]
        if "transaction_type" not in columns:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN transaction_type TEXT DEFAULT 'expense'"))
            conn.commit()


def register_user(engine, username: str, email: str, password: str) -> tuple:
    password_hash = hash_password(password)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO users (username, email, password_hash)
                    VALUES (:username, :email, :password_hash)
                """),
                {"username": username, "email": email, "password_hash": password_hash}
            )
            user_id = conn.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username}
            ).scalar()
        return True, user_id, "Registration successful!"
    except Exception as e:
        if "UNIQUE" in str(e).upper() or "Duplicate" in str(e):
            return False, None, "Username or email already exists!"
        return False, None, f"Registration failed: {str(e)}"


def authenticate_user(engine, username: str, password: str) -> tuple:
    password_hash = hash_password(password)
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, username, email FROM users 
                WHERE username = :username AND password_hash = :password_hash
            """),
            {"username": username, "password_hash": password_hash}
        ).fetchone()
    if result:
        return True, {"id": result[0], "username": result[1], "email": result[2]}
    return False, None


def login_page(engine):
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {BACKGROUND_GRADIENT};
            color: #e2e8f0;
        }}
        .auth-container {{
            max-width: 400px;
            margin: 50px auto;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 25px 50px rgba(0,0,0,0.4);
        }}
        .title-glow {{
            background: linear-gradient(90deg, {PRIMARY_COLOR}, {ACCENT_COLOR});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<h1 class="title-glow">💸 GPS Ledger</h1>', unsafe_allow_html=True)
        st.markdown('<p style="text-align: center; color: #94a3b8;">Your personal expense studio</p>', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔐 Login", "📝 Sign Up"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                login_btn = st.form_submit_button("Login", use_container_width=True)
                
                if login_btn:
                    if username and password:
                        success, user = authenticate_user(engine, username, password)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user = user
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password!")
                    else:
                        st.warning("Please fill in all fields!")
        
        with tab2:
            with st.form("signup_form"):
                new_username = st.text_input("Username", placeholder="Choose a username", key="reg_user")
                new_email = st.text_input("Email", placeholder="Enter your email", key="reg_email")
                new_password = st.text_input("Password", type="password", placeholder="Create a password", key="reg_pass")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
                signup_btn = st.form_submit_button("Sign Up", use_container_width=True)
                
                if signup_btn:
                    if new_username and new_email and new_password and confirm_password:
                        if new_password != confirm_password:
                            st.error("Passwords do not match!")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters!")
                        elif "@" not in new_email:
                            st.error("Please enter a valid email!")
                        else:
                            success, user_id, message = register_user(engine, new_username, new_email, new_password)
                            if success:
                                st.success(message + " Please login.")
                            else:
                                st.error(message)
                    else:
                        st.warning("Please fill in all fields!")


def upsert_category(engine, user_id: int, name: str, color: str = "#38bdf8") -> Optional[int]:
    if not name:
        return None
    with engine.begin() as conn:
        # Check if category exists
        existing = conn.execute(
            text("SELECT id FROM categories WHERE user_id = :user_id AND name = :name"),
            {"user_id": user_id, "name": name.strip()}
        ).scalar()
        
        if existing:
            conn.execute(
                text("UPDATE categories SET color = :color WHERE id = :id"),
                {"color": color, "id": existing}
            )
            return existing
        else:
            conn.execute(
                text("""
                    INSERT INTO categories (user_id, name, color)
                    VALUES (:user_id, :name, :color)
                """),
                {"user_id": user_id, "name": name.strip(), "color": color},
            )
            cat_id = conn.execute(
                text("SELECT id FROM categories WHERE user_id = :user_id AND name = :name"),
                {"user_id": user_id, "name": name.strip()}
            ).scalar()
            return cat_id


def insert_transaction(
    engine,
    user_id: int,
    transaction_type: str,
    occurred_on: dt.date,
    description: str,
    amount: float,
    category_id: Optional[int],
    payment_method: str,
    tags: str,
    receipt_url: str,
):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transactions
                (user_id, transaction_type, occurred_on, description, amount, category_id, payment_method, tags, receipt_url)
                VALUES (:user_id, :transaction_type, :occurred_on, :description, :amount, :category_id, :payment_method, :tags, :receipt_url)
                """
            ),
            {
                "user_id": user_id,
                "transaction_type": transaction_type,
                "occurred_on": occurred_on,
                "description": description,
                "amount": amount,
                "category_id": category_id,
                "payment_method": payment_method,
                "tags": tags,
                "receipt_url": receipt_url,
            },
        )


def upsert_budget(engine, user_id: int, category_id: int, month_start: dt.date, monthly_limit: float):
    with engine.begin() as conn:
        # Check if budget exists
        existing = conn.execute(
            text("SELECT id FROM budgets WHERE user_id = :user_id AND category_id = :category_id AND month_start = :month_start"),
            {"user_id": user_id, "category_id": category_id, "month_start": month_start}
        ).scalar()
        
        if existing:
            conn.execute(
                text("UPDATE budgets SET monthly_limit = :monthly_limit WHERE id = :id"),
                {"monthly_limit": monthly_limit, "id": existing}
            )
        else:
            conn.execute(
                text("""
                    INSERT INTO budgets (user_id, category_id, month_start, monthly_limit)
                    VALUES (:user_id, :category_id, :month_start, :monthly_limit)
                """),
                {"user_id": user_id, "category_id": category_id, "month_start": month_start, "monthly_limit": monthly_limit},
            )


def add_savings_goal(engine, user_id: int, goal_name: str, target_amount: float, deadline: dt.date):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO savings_goals (user_id, goal_name, target_amount, deadline)
                VALUES (:user_id, :goal_name, :target_amount, :deadline)
            """),
            {"user_id": user_id, "goal_name": goal_name, "target_amount": target_amount, "deadline": deadline}
        )


def update_savings_goal(engine, goal_id: int, amount: float):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE savings_goals SET current_amount = current_amount + :amount WHERE id = :goal_id"),
            {"goal_id": goal_id, "amount": amount}
        )


def delete_transaction(engine, transaction_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": transaction_id})


def delete_budget(engine, budget_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM budgets WHERE id = :id"), {"id": budget_id})


@st.cache_data(ttl=120, show_spinner=False)
def load_table(_engine, query: str, params: dict = None) -> pd.DataFrame:
    with _engine.connect() as conn:
        if params:
            return pd.read_sql(text(query), conn, params=params)
        return pd.read_sql(text(query), conn)


def layout_hero():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {BACKGROUND_GRADIENT};
            color: #e2e8f0;
        }}
        .glass {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.35);
            margin-bottom: 1rem;
        }}
        .title-glow {{
            background: linear-gradient(90deg, {PRIMARY_COLOR}, {ACCENT_COLOR});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{
            color: #94a3b8;
            font-size: 1rem;
        }}
        .metric-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 8px;
        }}
        .stTabs [data-baseweb="tab"] {{
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 10px 20px;
        }}
        .stTabs [aria-selected="true"] {{
            background: linear-gradient(90deg, {PRIMARY_COLOR}, {ACCENT_COLOR});
        }}
        .stExpander {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
        }}
        /* Hide 'Press Enter to submit form' text */
        .stForm > div:first-child > div:first-child > div > small {{
            display: none !important;
        }}
        div[data-testid="InputInstructions"] {{
            display: none !important;
        }}
        </style>
        <div class="glass">
            <h1 class="title-glow">💸 GPS Ledger</h1>
            <p class="subtitle">Your personal expense studio with live budgets, analytics, and insights.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_cards(df: pd.DataFrame):
    today = dt.date.today()
    month_start = today.replace(day=1)
    
    if not df.empty:
        df["occurred_on"] = pd.to_datetime(df["occurred_on"])
    
    month_df = df[df["occurred_on"] >= pd.Timestamp(month_start)] if not df.empty else df
    
    # Separate income and expenses
    if "transaction_type" in df.columns:
        expense_df = month_df[month_df["transaction_type"] == "expense"] if not month_df.empty else month_df
        income_df = month_df[month_df["transaction_type"] == "income"] if not month_df.empty else month_df
    else:
        expense_df = month_df
        income_df = pd.DataFrame()
    
    total_expenses = expense_df["amount"].sum() if not expense_df.empty else 0
    total_income = income_df["amount"].sum() if not income_df.empty else 0
    net_balance = total_income - total_expenses
    
    avg_daily = expense_df.groupby("occurred_on")["amount"].sum().mean() if not expense_df.empty else 0
    total_transactions = len(month_df) if not month_df.empty else 0
    top_cat = (
        expense_df.groupby("category")["amount"].sum().sort_values(ascending=False).reset_index().iloc[0]
        if not expense_df.empty and len(expense_df) > 0
        else None
    )

    cols = st.columns(5)
    cols[0].metric("💰 Income", f"{CURRENCY}{total_income:,.2f}", help="Total income this month")
    cols[1].metric("💸 Expenses", f"{CURRENCY}{total_expenses:,.2f}", help="Total spending this month")
    
    # Net balance with color indicator
    delta_color = "normal" if net_balance >= 0 else "inverse"
    cols[2].metric("📊 Net Balance", f"{CURRENCY}{abs(net_balance):,.2f}", 
                   delta=f"{'Profit' if net_balance >= 0 else 'Loss'}",
                   delta_color=delta_color,
                   help="Income minus Expenses")
    
    cols[3].metric("📝 Transactions", f"{total_transactions}", help="Number of transactions this month")
    cols[4].metric(
        "🏆 Top Expense",
        f"{top_cat['category'].split(' ')[-1] if ' ' in str(top_cat['category']) else top_cat['category']}" if top_cat is not None else "—",
        f"{CURRENCY}{top_cat['amount']:,.0f}" if top_cat is not None else None,
        help="Highest spending category"
    )


def trend_section(df: pd.DataFrame):
    if df.empty:
        st.info("Add transactions to see trends.")
        return

    roll = (
        df.groupby("occurred_on")["amount"].sum().rolling(7).mean().reset_index().rename(columns={"amount": "rolling"})
    )
    trend = df.groupby("occurred_on")["amount"].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=trend["occurred_on"], y=trend["amount"], name="Daily spend", marker_color=ACCENT_COLOR))
    fig.add_trace(go.Scatter(x=roll["occurred_on"], y=roll["rolling"], name="7d smooth", line=dict(color=PRIMARY_COLOR, width=3)))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=360,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)


def category_pie(df: pd.DataFrame):
    if df.empty:
        st.info("No category data yet.")
        return
    
    cat_data = df.groupby("category")["amount"].sum().reset_index()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 🥧 Spending by Category")
        fig = px.pie(
            cat_data, 
            names="category", 
            values="amount", 
            hole=0.45, 
            color_discrete_sequence=px.colors.qualitative.Bold
        )
        fig.update_layout(template="plotly_dark", height=340, margin=dict(l=0, r=0, t=10, b=0))
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True, theme=None)
    
    with col2:
        st.markdown("##### 📊 Category Breakdown")
        fig2 = px.bar(
            cat_data.sort_values("amount", ascending=True),
            x="amount",
            y="category",
            orientation='h',
            color="amount",
            color_continuous_scale="Viridis"
        )
        fig2.update_layout(
            template="plotly_dark",
            height=340,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False,
            coloraxis_showscale=False
        )
        st.plotly_chart(fig2, use_container_width=True, theme=None)


def budget_burndown(df_tx: pd.DataFrame, df_budgets: pd.DataFrame):
    if df_budgets.empty:
        st.info("💡 Set up budgets in the 'Budgets & Goals' tab to track your spending.")
        return
    
    today = dt.date.today()
    month_start = today.replace(day=1)
    month_end = (month_start + pd.offsets.MonthEnd(1)).date()
    
    # Handle empty transactions gracefully
    if df_tx.empty:
        merged = df_budgets.copy()
        merged["amount"] = 0
        merged["remaining"] = merged["monthly_limit"]
        merged["percentage"] = 0
    else:
        # Convert dates safely
        df_tx_copy = df_tx.copy()
        df_tx_copy["occurred_on"] = pd.to_datetime(df_tx_copy["occurred_on"])
        
        tx_month = df_tx_copy[
            (df_tx_copy["occurred_on"] >= pd.Timestamp(month_start)) & 
            (df_tx_copy["occurred_on"] <= pd.Timestamp(month_end))
        ]
        
        if tx_month.empty:
            merged = df_budgets.copy()
            merged["amount"] = 0
            merged["remaining"] = merged["monthly_limit"]
            merged["percentage"] = 0
        else:
            by_cat = tx_month.groupby("category")["amount"].sum().reset_index()
            merged = df_budgets.merge(by_cat, on="category", how="left").fillna({"amount": 0})
            merged["remaining"] = merged["monthly_limit"] - merged["amount"]
            merged["percentage"] = (merged["amount"] / merged["monthly_limit"] * 100).clip(0, 150)
    
    # Show budget status indicators
    st.markdown("##### 📊 Budget Status")
    
    # Check for any over-budget categories and show bold warning
    over_budget_cats = merged[merged["amount"] > merged["monthly_limit"]]
    if not over_budget_cats.empty:
        total_overspent = (over_budget_cats["amount"] - over_budget_cats["monthly_limit"]).sum()
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.3)); 
        padding: 1rem; border-radius: 12px; border: 2px solid #ef4444; margin-bottom: 1rem;">
            <h3 style="color: #fca5a5; margin: 0;">⚠️ Over Budget Alert!</h3>
            <p style="font-size: 1.5rem; font-weight: bold; color: #ffffff; margin: 0.5rem 0;">
                You have overspent by <span style="color: #ef4444; font-size: 2rem;">{CURRENCY}{total_overspent:,.0f}</span>
            </p>
            <p style="color: #fca5a5; margin: 0;">Categories over budget: {', '.join(over_budget_cats['category'].tolist())}</p>
        </div>
        """, unsafe_allow_html=True)
    
    status_cols = st.columns(min(len(merged), 4))
    for idx, (_, row) in enumerate(merged.iterrows()):
        col_idx = idx % 4
        pct = row["percentage"]
        extra_spent = row["amount"] - row["monthly_limit"] if row["amount"] > row["monthly_limit"] else 0
        
        if pct >= 100:
            status = "🔴 Over Budget"
            delta_color = "inverse"
            delta_text = f"+{CURRENCY}{extra_spent:,.0f} over!"
        elif pct >= 80:
            status = "🟡 Near Limit"
            delta_color = "off"
            delta_text = f"{pct:.0f}% used"
        else:
            status = "🟢 On Track"
            delta_color = "normal"
            delta_text = f"{pct:.0f}% used"
        
        with status_cols[col_idx]:
            cat_name = row['category'].split(' ')[-1] if ' ' in str(row['category']) else row['category']
            st.metric(
                label=cat_name[:12],
                value=f"{CURRENCY}{row['amount']:,.0f}",
                delta=delta_text,
                delta_color=delta_color
            )
            if extra_spent > 0:
                st.markdown(f"<p style='color: #ef4444; font-weight: bold; font-size: 0.9rem; margin-top: -10px;'>🔥 {CURRENCY}{extra_spent:,.0f} EXTRA</p>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📉 Budget vs Spending")
        fig = px.bar(
            merged,
            x="category",
            y=["amount", "remaining"],
            barmode="stack",
            color_discrete_sequence=[ACCENT_COLOR, "#10b981"],
            labels={"value": "INR (₹)", "variable": ""},
        )
        fig.update_layout(template="plotly_dark", height=360, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True, theme=None)
    
    with col2:
        st.markdown("##### 🎯 Budget Utilization")
        fig2 = go.Figure()
        for _, row in merged.iterrows():
            pct = min(row["percentage"], 150)  # Cap display at 150%
            color = "#10b981" if row["percentage"] < 80 else ("#f59e0b" if row["percentage"] < 100 else "#ef4444")
            fig2.add_trace(go.Bar(
                x=[pct],
                y=[row["category"]],
                orientation='h',
                marker_color=color,
                text=f"{row['percentage']:.0f}%",
                textposition='inside',
                showlegend=False
            ))
        fig2.update_layout(
            template="plotly_dark",
            height=360,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(range=[0, 150], title="% Used"),
            yaxis=dict(title="")
        )
        fig2.add_vline(x=100, line_dash="dash", line_color="red", annotation_text="Limit")
        st.plotly_chart(fig2, use_container_width=True, theme=None)


def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    st.sidebar.subheader("🔍 Filters")
    
    # Handle date conversion safely
    df_dates = pd.to_datetime(df["occurred_on"])
    min_date = df_dates.min().date() if hasattr(df_dates.min(), 'date') else df_dates.min()
    max_date = df_dates.max().date() if hasattr(df_dates.max(), 'date') else df_dates.max()
    
    # Ensure min_date and max_date are date objects
    if isinstance(min_date, pd.Timestamp):
        min_date = min_date.date()
    if isinstance(max_date, pd.Timestamp):
        max_date = max_date.date()
    
    date_range = st.sidebar.date_input("📅 Date range", [min_date, max_date])
    if len(date_range) == 2:
        start, end = date_range
    else:
        start, end = min_date, max_date
    
    cats = st.sidebar.multiselect("📁 Categories", sorted(df["category"].dropna().unique().tolist()))
    payment = st.sidebar.multiselect("💳 Payment Method", sorted(df["payment_method"].dropna().unique().tolist()))
    
    amt_min = float(df["amount"].min())
    amt_max = float(df["amount"].max())
    if amt_min == amt_max:
        amt_max = amt_min + 1
    min_amt, max_amt = st.sidebar.slider("💰 Amount range", amt_min, amt_max, (amt_min, amt_max))

    filtered = df.copy()
    filtered["occurred_on"] = pd.to_datetime(filtered["occurred_on"])
    filtered = filtered[(filtered["occurred_on"] >= pd.Timestamp(start)) & (filtered["occurred_on"] <= pd.Timestamp(end))]
    if cats:
        filtered = filtered[filtered["category"].isin(cats)]
    if payment:
        filtered = filtered[filtered["payment_method"].isin(payment)]
    filtered = filtered[(filtered["amount"] >= min_amt) & (filtered["amount"] <= max_amt)]
    return filtered


def add_transaction_form(engine, user_id: int, categories: List[str]):
    with st.expander("➕ Add Transaction", expanded=True):
        st.markdown("""<style>
        .stForm {background: rgba(255,255,255,0.02); border-radius: 12px; padding: 1rem;}
        </style>""", unsafe_allow_html=True)
        
        # Transaction type tabs
        tx_tab1, tx_tab2 = st.tabs(["💸 Expense", "💰 Income"])
        
        with tx_tab1:
            # Combine user categories with expense defaults
            expense_categories = list(dict.fromkeys(categories + DEFAULT_EXPENSE_CATEGORIES))
            
            with st.form("add_expense"):
                cols = st.columns(2)
                occurred_on = cols[0].date_input("📅 Date", dt.date.today(), key="exp_date")
                amount = cols[1].number_input(f"💵 Amount ({CURRENCY})", min_value=0.0, step=0.01, format="%.2f", key="exp_amount")
                
                description = st.text_input("📝 Description", placeholder="What did you spend on?", key="exp_desc")
                
                category_name = st.selectbox(
                    "📁 Category", 
                    options=expense_categories,
                    help="Select a category for your expense",
                    key="exp_cat"
                )
                
                col1, col2 = st.columns(2)
                payment_method = col1.selectbox(
                    "💳 Payment Method", 
                    ["💳 Card", "💵 Cash", "🏦 Bank Transfer", "📱 UPI", "👛 Wallet", "₿ Crypto"],
                    key="exp_payment"
                )
                tags = col2.text_input("🏷️ Tags", placeholder="e.g., urgent, monthly", key="exp_tags")
                
                receipt_url = st.text_input("🔗 Receipt URL (optional)", placeholder="https://...", key="exp_receipt")

                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    submitted = st.form_submit_button("💸 Save Expense", use_container_width=True, type="primary")
                
                if submitted:
                    if amount <= 0:
                        st.error("⚠️ Please enter a valid amount greater than 0")
                    else:
                        cat_id = upsert_category(engine, user_id, category_name)
                        clean_payment = payment_method.split(" ", 1)[-1] if " " in payment_method else payment_method
                        insert_transaction(
                            engine,
                            user_id,
                            "expense",
                            occurred_on,
                            description.strip() or "Untitled",
                            float(amount),
                            cat_id,
                            clean_payment.lower(),
                            tags,
                            receipt_url,
                        )
                        st.success("✅ Expense saved successfully!")
                        st.cache_data.clear()
                        st.rerun()
        
        with tx_tab2:
            # Income form
            with st.form("add_income"):
                cols = st.columns(2)
                inc_occurred_on = cols[0].date_input("📅 Date", dt.date.today(), key="inc_date")
                inc_amount = cols[1].number_input(f"💵 Amount ({CURRENCY})", min_value=0.0, step=0.01, format="%.2f", key="inc_amount")
                
                inc_description = st.text_input("📝 Description", placeholder="Source of income", key="inc_desc")
                
                inc_category_name = st.selectbox(
                    "📁 Income Source", 
                    options=DEFAULT_INCOME_CATEGORIES,
                    help="Select the source of your income",
                    key="inc_cat"
                )
                
                col1, col2 = st.columns(2)
                inc_payment_method = col1.selectbox(
                    "💳 Received Via", 
                    ["🏦 Bank Transfer", "💵 Cash", "📱 UPI", "💳 Card", "👛 Wallet", "₿ Crypto", "📄 Cheque"],
                    key="inc_payment"
                )
                inc_tags = col2.text_input("🏷️ Tags", placeholder="e.g., monthly, bonus", key="inc_tags")

                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    inc_submitted = st.form_submit_button("💰 Save Income", use_container_width=True, type="primary")
                
                if inc_submitted:
                    if inc_amount <= 0:
                        st.error("⚠️ Please enter a valid amount greater than 0")
                    else:
                        cat_id = upsert_category(engine, user_id, inc_category_name)
                        clean_payment = inc_payment_method.split(" ", 1)[-1] if " " in inc_payment_method else inc_payment_method
                        insert_transaction(
                            engine,
                            user_id,
                            "income",
                            inc_occurred_on,
                            inc_description.strip() or "Income",
                            float(inc_amount),
                            cat_id,
                            clean_payment.lower(),
                            inc_tags,
                            "",
                        )
                        st.success("✅ Income saved successfully!")
                        st.cache_data.clear()
                        st.rerun()


def budget_form(engine, user_id: int, categories: List[str]):
    # Combine user categories with defaults
    all_categories = list(dict.fromkeys(categories + DEFAULT_CATEGORIES))
    
    with st.expander("💰 Set Monthly Budget"):
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(14, 165, 233, 0.1)); 
        padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
        📊 <strong>Budget Tip:</strong> Set realistic limits based on your spending history.
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("budget"):
            col1, col2 = st.columns(2)
            month = col1.date_input("📅 Budget Month", dt.date.today().replace(day=1))
            monthly_limit = col2.number_input(f"💵 Monthly Limit ({CURRENCY})", min_value=0.0, step=10.0, format="%.2f")
            
            category_name = st.selectbox(
                "📁 Category", 
                options=all_categories,
                help="Choose which category to set a budget for"
            )
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                submitted = st.form_submit_button("💾 Save Budget", use_container_width=True, type="primary")
            
            if submitted:
                if monthly_limit <= 0:
                    st.error("⚠️ Please enter a valid budget amount")
                else:
                    cat_id = upsert_category(engine, user_id, category_name)
                    upsert_budget(engine, user_id, cat_id, month, float(monthly_limit))
                    st.success("✅ Budget saved successfully!")
                    st.cache_data.clear()
                    st.rerun()


def savings_goal_form(engine, user_id: int):
    with st.expander("🎯 Savings Goals"):
        tab1, tab2 = st.tabs(["Add Goal", "Update Progress"])
        
        with tab1:
            with st.form("add_goal"):
                goal_name = st.text_input("Goal name (e.g., Vacation, Emergency Fund)")
                target_amount = st.number_input(f"Target amount ({CURRENCY})", min_value=0.0, step=100.0)
                deadline = st.date_input("Target date", dt.date.today() + dt.timedelta(days=365))
                
                if st.form_submit_button("🎯 Create Goal", use_container_width=True):
                    if goal_name and target_amount > 0:
                        add_savings_goal(engine, user_id, goal_name, target_amount, deadline)
                        st.success("✅ Goal created!")
                        st.cache_data.clear()
                    else:
                        st.warning("Please fill in goal name and target amount!")


def analytics_section(df: pd.DataFrame):
    if df.empty:
        st.info("Add transactions to see analytics.")
        return
    
    st.subheader("📈 Advanced Analytics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("##### Weekly Spending Pattern")
        df_copy = df.copy()
        df_copy["day_of_week"] = pd.to_datetime(df_copy["occurred_on"]).dt.day_name()
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekly = df_copy.groupby("day_of_week")["amount"].sum().reindex(day_order).fillna(0).reset_index()
        fig = px.bar(weekly, x="day_of_week", y="amount", color="amount", color_continuous_scale="Plasma")
        fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True, theme=None)
    
    with col2:
        st.markdown("##### Monthly Trend")
        df_copy = df.copy()
        df_copy["month"] = pd.to_datetime(df_copy["occurred_on"]).dt.to_period("M").astype(str)
        monthly = df_copy.groupby("month")["amount"].sum().reset_index()
        fig = px.line(monthly, x="month", y="amount", markers=True, line_shape="spline")
        fig.update_traces(line_color=PRIMARY_COLOR, line_width=3)
        fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True, theme=None)
    
    with col3:
        st.markdown("##### Payment Methods")
        payment_data = df.groupby("payment_method")["amount"].sum().reset_index()
        fig = px.pie(payment_data, names="payment_method", values="amount", hole=0.5, color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True, theme=None)


def expense_heatmap(df: pd.DataFrame):
    if df.empty:
        return
    
    st.markdown("##### 🗓️ Spending Heatmap")
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["occurred_on"])
    df_copy["week"] = df_copy["date"].dt.isocalendar().week
    df_copy["day"] = df_copy["date"].dt.day_name()
    
    pivot = df_copy.pivot_table(values="amount", index="day", columns="week", aggfunc="sum", fill_value=0)
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex(day_order)
    
    fig = px.imshow(pivot, color_continuous_scale="Viridis", aspect="auto")
    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True, theme=None)


def main():
    # Initialize session state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user" not in st.session_state:
        st.session_state.user = None
    
    engine = get_engine()
    try:
        init_db(engine)
    except Exception as exc:
        st.error(f"Database error: {exc}")
        st.stop()
    
    # Show login page if not logged in
    if not st.session_state.logged_in:
        login_page(engine)
        return
    
    # User is logged in - show main app
    user_id = st.session_state.user["id"]
    username = st.session_state.user["username"]
    
    # Sidebar with user info
    with st.sidebar:
        st.markdown(f"### 👤 Welcome, {username}!")
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.success("✅ Connected to MySQL")

    df_tx = load_table(
        engine,
        f"""
        SELECT t.id, t.occurred_on, t.description, t.amount, t.payment_method, t.tags, t.receipt_url,
               COALESCE(t.transaction_type, 'expense') AS transaction_type,
               COALESCE(c.name, 'Uncategorized') AS category
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = {user_id}
        ORDER BY t.occurred_on DESC, t.created_at DESC
        """,
    )

    df_budgets = load_table(
        engine,
        f"""
        SELECT b.id, COALESCE(c.name, 'Uncategorized') AS category, b.month_start, b.monthly_limit
        FROM budgets b
        LEFT JOIN categories c ON b.category_id = c.id
        WHERE b.user_id = {user_id}
        ORDER BY b.month_start DESC
        """,
    )

    df_goals = load_table(
        engine,
        f"""
        SELECT id, goal_name, target_amount, current_amount, deadline
        FROM savings_goals
        WHERE user_id = {user_id}
        ORDER BY deadline ASC
        """,
    )

    layout_hero()
    
    categories = sorted(df_tx["category"].dropna().unique().tolist()) if not df_tx.empty else []
    
    # Main tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "➕ Add Data", "💰 Budgets & Goals", "📋 Ledger"])
    
    with tab1:
        filtered = filter_data(df_tx)
        metric_cards(filtered)
        
        st.markdown("### 📈 Spending Trends")
        trend_section(filtered)
        
        st.markdown("### 🥧 Category Analysis")
        category_pie(filtered)
        
        analytics_section(filtered)
        expense_heatmap(filtered)
    
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            add_transaction_form(engine, user_id, categories)
        with col2:
            st.markdown("### 📝 Quick Stats")
            if not df_tx.empty:
                st.metric("Total Transactions", len(df_tx))
                st.metric("Total Spent", f"{CURRENCY}{df_tx['amount'].sum():,.2f}")
                st.metric("Categories Used", df_tx['category'].nunique())
            else:
                st.info("No transactions yet. Add your first one!")
    
    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            budget_form(engine, user_id, categories if categories else ["Food", "Transport", "Entertainment", "Shopping", "Bills"])
            
            if not df_budgets.empty:
                st.markdown("### 📋 Current Budgets")
                st.dataframe(
                    df_budgets[["category", "month_start", "monthly_limit"]],
                    use_container_width=True,
                    hide_index=True
                )
        
        with col2:
            savings_goal_form(engine, user_id)
            
            if not df_goals.empty:
                st.markdown("### 🎯 Your Goals")
                for _, goal in df_goals.iterrows():
                    progress = (goal["current_amount"] / goal["target_amount"]) * 100 if goal["target_amount"] > 0 else 0
                    st.markdown(f"**{goal['goal_name']}**")
                    st.progress(min(progress / 100, 1.0))
                    st.caption(f"{CURRENCY}{goal['current_amount']:,.0f} / {CURRENCY}{goal['target_amount']:,.0f} ({progress:.1f}%)")
        
        st.markdown("### 📉 Budget Burndown")
        budget_burndown(df_tx, df_budgets)
    
    with tab4:
        st.subheader("📋 Transaction Ledger")
        if df_tx.empty:
            st.info("No transactions yet. Start adding your expenses!")
        else:
            # Add type indicator with emoji
            display_df = df_tx.copy()
            display_df["type"] = display_df["transaction_type"].apply(
                lambda x: "💸 Expense" if x == "expense" else "💰 Income"
            )
            st.dataframe(
                display_df[["occurred_on", "type", "description", "category", "amount", "payment_method", "tags"]],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()
