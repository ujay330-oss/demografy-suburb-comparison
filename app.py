import streamlit as st
import pipeline
import plotly.graph_objects as go
from datetime import datetime, timezone
import folium
from streamlit_folium import st_folium
import concurrent.futures as cf


def format_timestamp(ts_string) -> str:
    """Converts ISO timestamp or datetime object to human-readable format."""
    if not ts_string:
        return 'Unknown'
    try:
        if isinstance(ts_string, datetime):
            ts = ts_string.replace(tzinfo=timezone.utc) if ts_string.tzinfo is None else ts_string
        else:
            # Parse then explicitly set UTC since Supabase returns naive timestamps
            ts = datetime.fromisoformat(str(ts_string).replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)  # ← this is the fix

        now  = datetime.now(timezone.utc)
        diff = now - ts
        days  = diff.days
        hours = diff.seconds // 3600

        if days == 0 and hours == 0:
            return 'Just now'
        elif days == 0:
            return f'{hours} hour{"s" if hours > 1 else ""} ago'
        elif days == 1:
            return 'Yesterday'
        elif days < 30:
            return f'{days} days ago'
        elif days < 365:
            months = days // 30
            return f'{months} month{"s" if months > 1 else ""} ago'
        else:
            return ts.strftime('%d %b %Y')
    except Exception as e:
        print(f"format_timestamp error: {e} — raw value: '{ts_string}'")
        return 'Unknown'


st.set_page_config(
    page_title='Demografy - Suburb Comparator',
    page_icon='🏙️',
    layout='wide'
)

logo_path = 'demografy_logo1.png'
st.logo(image=logo_path, size="large")

st.title('🏙️ Suburb Comparison', width='stretch')
st.caption("Ready to find your next postcode? Just enter the names of your desired suburbs and let us compare them for you! :mag_right:")

# ── Top-level constants ────────────────────────────────────────
METRICS = {
    'dining_score':     '🍽️  Dining Out',
    'parks_score':      '🌳  Parks & Gardens',
    'wellness_score':   '💪  Wellness & Fitness',
    'childcare_score':  '👶  Childcare',
    'transport_score':  '🚆  Transport',
    'shopping_score':   '🛍️  Shopping',
    'education_score':  '🎓  Education',
    'healthcare_score': '🏥  Healthcare',
}

SLIDER_CATEGORIES = {
    'dining_score':     ('🍽️  Dining Out',         5),
    'parks_score':      ('🌳  Parks & Gardens',    5),
    'wellness_score':   ('💪  Wellness & Fitness',  5),
    'childcare_score':  ('👶  Childcare',           5),
    'transport_score':  ('🚆  Transport',           5),
    'shopping_score':   ('🛍️  Shopping',            5),
    'education_score':  ('🎓  Education',           5),
    'healthcare_score': ('🏥  Healthcare',          5),
}

COLOR_A = "#298c8c"
COLOR_B = "#800074"

METRIC_KEYS = list(METRICS.keys())


# ── Helper function ────────────────────────────────────────────
def compute_weighted_score(metrics: dict, weights: dict) -> float:
    """
    Computes a personalised livability score using user-defined weights.
    Formula: Σ(score × weight) / Σ(weights)
    Returns a value between 0 and 100.
    """
    total_weighted = 0
    total_weight   = 0
    for key, weight in weights.items():
        score          = metrics.get(key, 0)
        total_weighted += score * weight
        total_weight   += weight
    if total_weight == 0:
        return 0
    return round(total_weighted / total_weight, 1)


# ── Suburb inputs ──────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    suburb_a = st.text_input('Suburb A', placeholder='e.g. Bondi')
with col2:
    suburb_b = st.text_input('Suburb B', placeholder='e.g. Chatswood')

state = st.selectbox('State', ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT'])

st.divider()

# ── Preference sliders — set BEFORE clicking compare ──────────
st.markdown('#### 🎯 Personalise your livability score')
st.caption('Drag each slider to reflect how important each category is to you. 0 = not important, 10 = essential.')

weights   = {}
row1_keys = METRIC_KEYS[:4]
row2_keys = METRIC_KEYS[4:]

cols = st.columns(4)
for col, key in zip(cols, row1_keys):
    label, default = SLIDER_CATEGORIES[key]
    with col:
        weights[key] = st.slider(
            label, min_value=0, max_value=10,
            value=default, key=f'weight_{key}'
        )

cols = st.columns(4)
for col, key in zip(cols, row2_keys):
    label, default = SLIDER_CATEGORIES[key]
    with col:
        weights[key] = st.slider(
            label, min_value=0, max_value=10,
            value=default, key=f'weight_{key}'
        )

st.divider()

# ── Compare button ─────────────────────────────────────────────
if st.button('Compare Suburbs', type='primary'):
    if not suburb_a or not suburb_b:
        st.warning('Please enter both suburb names.')
    elif suburb_a.strip().lower() == suburb_b.strip().lower():
        st.warning('Please enter two different suburbs.')
    else:
        # Clear previous session state before new fetch
        for key in ['results', 'suburb_a_clean', 'suburb_b_clean']:
            st.session_state.pop(key, None)

        suburb_a_clean = suburb_a.strip().title()
        suburb_b_clean = suburb_b.strip().title()

        results  = {}
        progress = st.progress(0, text='Starting...')

        progress.progress(10, text=f'Fetching data for {suburb_a_clean} and {suburb_b_clean}...')

        errors = {}

        def fetch(suburb):
            try:
                results[suburb] = pipeline.fetch_suburb_if_needed(suburb, state)
            except ValueError as e:
                errors[suburb] = str(e)

        with cf.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(fetch, suburb_a_clean): suburb_a_clean,
                executor.submit(fetch, suburb_b_clean): suburb_b_clean,
            }
            cf.wait(futures)

        # Handle any errors
        if errors:
            progress.empty()
            for suburb, msg in errors.items():
                st.error(msg)
            st.stop()

        progress.progress(90, text='Almost done...')

        progress.progress(100, text='Done!')

        # Persist results to session state
        st.session_state['results']        = results
        st.session_state['suburb_a_clean'] = suburb_a_clean
        st.session_state['suburb_b_clean'] = suburb_b_clean


# ── Render results (runs on every rerun including slider moves) ─
if 'results' in st.session_state:
    results        = st.session_state['results']
    suburb_a_clean = st.session_state['suburb_a_clean']
    suburb_b_clean = st.session_state['suburb_b_clean']

    # ── Source badges ──────────────────────────────────────────
    col1, col2 = st.columns(2)
    for col, suburb in zip([col1, col2], [suburb_a_clean, suburb_b_clean]):
        with col:
            src = results[suburb].get('source', 'unknown')
            ts  = results[suburb].get('fetched_at', '')
            age = format_timestamp(ts)
            if src == 'cache':
                st.success(f'✅ {suburb} — loaded from cache')
            else:
                st.info(f'🌐 {suburb} — freshly fetched from Google API')
            st.caption(f'🕐 Data last updated: {age}')

    # ── Weighted KPI cards ─────────────────────────────────────
    weighted_a = compute_weighted_score(results[suburb_a_clean], weights)
    weighted_b = compute_weighted_score(results[suburb_b_clean], weights)

    st.markdown("""
        <style>
        [data-testid="stMetric"] { text-align: center; }
        [data-testid="stMetricLabel"] { display: flex; justify-content: center; width: 100%; }
        [data-testid="stMetricLabel"] > div { justify-content: center; width: 100%; }
        [data-testid="stMetricLabel"] p { text-align: center; width: 100%; }
        [data-testid="stMetricValue"] { display: flex; justify-content: center; width: 100%; }
        [data-testid="stMetricDelta"] { display: flex; justify-content: center; width: 100%; }
        [data-testid="stMetricDelta"] > div { justify-content: center; }
        </style>
    """, unsafe_allow_html=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            label=f'⭐ {suburb_a_clean} — Personalised Score',
            value=f'{weighted_a}/100',
            delta=f'{round(weighted_a - weighted_b, 1)} vs {suburb_b_clean}'
        )
    with col2:
        st.metric(
            label=f'⭐ {suburb_b_clean} — Personalised Score',
            value=f'{weighted_b}/100',
            delta=f'{round(weighted_b - weighted_a, 1)} vs {suburb_a_clean}'
        )

    st.divider()

    # ── Raw bar scores ─────────────────────────────────────────
    # Bars show true suburb quality (0-100)
    # Weights only affect the personalised KPI score above
    # Sort by descending average score
    categories = list(METRICS.values())
    scores_a   = [results[suburb_a_clean].get(k, 0) for k in METRIC_KEYS]
    scores_b   = [results[suburb_b_clean].get(k, 0) for k in METRIC_KEYS]

    combined = list(zip(METRIC_KEYS, categories, scores_a, scores_b))
    combined.sort(key=lambda x: (x[2] + x[3]) / 2, reverse=True)
    _, categories, scores_a, scores_b = zip(*combined)
    categories = list(categories)
    scores_a   = list(scores_a)
    scores_b   = list(scores_b)

    # ── Butterfly chart ────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Bar(
        name=suburb_a_clean,
        y=categories,
        x=[-s for s in scores_a],
        orientation='h',
        marker=dict(color=COLOR_A, line=dict(width=0)),
        text=[f'{s}' for s in scores_a],
        textposition='outside',
        textfont=dict(size=11, color=COLOR_A),
        hovertemplate=(
            '<b>%{y}</b><br>'
            + suburb_a_clean + ': %{text}/100'
            + '<extra></extra>'
        ),
    ))

    fig.add_trace(go.Bar(
        name=suburb_b_clean,
        y=categories,
        x=scores_b,
        orientation='h',
        marker=dict(color=COLOR_B, line=dict(width=0)),
        text=[f'{s}' for s in scores_b],
        textposition='outside',
        textfont=dict(size=11, color=COLOR_B),
        hovertemplate=(
            '<b>%{y}</b><br>'
            + suburb_b_clean + ': %{text}/100'
            + '<extra></extra>'
        ),
    ))

    fig.update_layout(
        barmode='overlay',
        height=440,
        margin=dict(l=10, r=10, t=40, b=20),
        xaxis=dict(
            range=[-115, 115],
            tickvals=[-100, -75, -50, -25, 0, 25, 50, 75, 100],
            ticktext=['100', '75', '50', '25', '0', '25', '50', '75', '100'],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.06)',
            zeroline=True,
            zerolinecolor='rgba(0,0,0,0.2)',
            zerolinewidth=2,
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            showgrid=False,
            automargin=True,
            tickfont=dict(size=13),
        ),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5,
            font=dict(size=12),
        ),
        bargap=0.35,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family='sans-serif'),
    )

    fig.add_annotation(
        x=-55, y=1.07, xref='x', yref='paper',
        text=f'← {suburb_a_clean}',
        showarrow=False,
        font=dict(size=13, color=COLOR_A),
        xanchor='center'
    )
    fig.add_annotation(
        x=55, y=1.07, xref='x', yref='paper',
        text=f'{suburb_b_clean} →',
        showarrow=False,
        font=dict(size=13, color=COLOR_B),
        xanchor='center'
    )

    st.plotly_chart(fig, width='stretch')
    st.caption(
        'Bar length shows raw suburb quality (0–100) based on place counts within 2.8 km. '
        'Categories are sorted in descending order. '
        'The KPI Card above shows personalised score reflecting your priorities.'
    )

    # ── Map view ───────────────────────────────────────────────
    st.divider()
    st.markdown('#### 📍 Suburb Locations')

    lat_a = results[suburb_a_clean].get('latitude')
    lng_a = results[suburb_a_clean].get('longitude')
    lat_b = results[suburb_b_clean].get('latitude')
    lng_b = results[suburb_b_clean].get('longitude')

    if lat_a and lat_b:
        centre_lat = (lat_a + lat_b) / 2
        centre_lng = (lng_a + lng_b) / 2

        m = folium.Map(
            location=[centre_lat, centre_lng],
            zoom_start=11,
            tiles='CartoDB positron'
        )

        folium.Marker(
            location=[lat_a, lng_a],
            popup=folium.Popup(
                f'<b>{suburb_a_clean}</b><br>Personalised Score: {weighted_a}/100',
                max_width=200
            ),
            tooltip=suburb_a_clean,
            icon=folium.Icon(color='green', icon='home', prefix='fa')
        ).add_to(m)

        folium.Marker(
            location=[lat_b, lng_b],
            popup=folium.Popup(
                f'<b>{suburb_b_clean}</b><br>Personalised Score: {weighted_b}/100',
                max_width=200
            ),
            tooltip=suburb_b_clean,
            icon=folium.Icon(color='purple', icon='home', prefix='fa')
        ).add_to(m)

        folium.PolyLine(
            locations=[[lat_a, lng_a], [lat_b, lng_b]],
            color='#888780',
            weight=1.5,
            dash_array='6'
        ).add_to(m)

        st_folium(m, width='stretch', height=380, returned_objects=[])

    else:
        st.info(
            'Map unavailable — re-search the suburbs to populate location data. '
            'This happens when suburbs were cached before coordinates were added.'
        )

    # ── Leads breakdown ────────────────────────────────────────
    st.divider()
    st.markdown('#### Where each suburb leads')
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f'**{suburb_a_clean}**')
        leads = [
            (cat, sa, sb)
            for cat, sa, sb in zip(categories, scores_a, scores_b)
            if sa > sb
        ]
        if leads:
            for cat, sa, sb in sorted(leads, key=lambda x: x[1] - x[2], reverse=True):
                diff = round(sa - sb, 1)
                st.success(f'**{cat}** — {sa} vs {sb} (+{diff})')
        else:
            st.info(f'{suburb_a_clean} does not lead in any category')

    with col2:
        st.markdown(f'**{suburb_b_clean}**')
        leads = [
            (cat, sa, sb)
            for cat, sa, sb in zip(categories, scores_a, scores_b)
            if sb > sa
        ]
        if leads:
            for cat, sa, sb in sorted(leads, key=lambda x: x[2] - x[1], reverse=True):
                diff = round(sb - sa, 1)
                st.success(f'**{cat}** — {sb} vs {sa} (+{diff})')
        else:
            st.info(f'{suburb_b_clean} does not lead in any category')