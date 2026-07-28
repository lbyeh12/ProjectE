"""
ProjectE 대시보드.

실행:
    streamlit run dashboard/app.py

두 개의 탭으로 구성:
  - 실시간: Spark Streaming 이 채우는 product_stats / traffic_stats / raw_events
  - 배치:   Airflow daily_etl 이 채우는 daily_metrics
"""
import streamlit as st

from db import (
    get_current_visitors,
    get_daily_metrics,
    get_realtime_revenue_today,
    get_recent_traffic,
    get_top_products,
)

st.set_page_config(page_title="ProjectE 대시보드", layout="wide")

st.title("ProjectE 데이터 플랫폼 대시보드")

tab_realtime, tab_batch = st.tabs(["실시간", "배치 (일별 지표)"])


# ============================================================
# 실시간 탭
# ============================================================
# 이 블록만 10초마다 부분적으로 다시 실행된다 (페이지 전체 rerun이 아님).
# time.sleep()+st.rerun() 방식은 위젯 상태가 꼬여 데이터가 없다고
# 잘못 표시되는 문제가 있어, st.fragment(run_every=...) 로 안전하게 갱신한다.
@st.fragment(run_every="10s")
def render_realtime_tab():
    st.caption("Spark Streaming 이 Kafka 이벤트를 실시간으로 집계한 결과입니다.")

    # --- 상단 지표 카드 ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("현재 접속자 (최근 5분)", get_current_visitors(minutes=5))
    with c2:
        st.metric("오늘 누적 매출", f"£{get_realtime_revenue_today():,.2f}")
    with c3:
        traffic_df = get_recent_traffic(minutes=60)
        recent_events = int(traffic_df["event_count"].sum()) if not traffic_df.empty else 0
        st.metric("최근 1시간 이벤트 수", f"{recent_events:,}")

    st.divider()

    # --- 실시간 인기 상품 ---
    st.subheader("실시간 인기 상품")
    top_products = get_top_products(limit=10)

    # Spark 가 product_stats 를 매 배치마다 TRUNCATE 후 다시 채우는 방식이라,
    # 하필 그 찰나에 조회하면 순간적으로 빈 결과가 온다.
    # 이번 조회가 비었어도 직전에 성공했던 결과가 있으면 그걸 보여줘서
    # "데이터가 없습니다"가 깜빡이는 것을 막는다.
    if top_products.empty and "last_top_products" in st.session_state:
        top_products = st.session_state["last_top_products"]
        st.caption("⏳ 갱신 중 잠깐 비어 보일 수 있어 직전 결과를 표시합니다.")
    elif not top_products.empty:
        st.session_state["last_top_products"] = top_products

    if top_products.empty:
        st.info("아직 집계된 상품 데이터가 없습니다. Spark Streaming 이 실행 중인지 확인하세요.")
    else:
        left, right = st.columns([2, 3])
        with left:
            st.dataframe(
                top_products.rename(columns={
                    "product_id": "상품ID", "description": "상품명",
                    "view_count": "조회수", "purchase_count": "구매수", "revenue": "매출",
                }),
                width="stretch",
                hide_index=True,
            )
        with right:
            chart_df = top_products.set_index("product_id")[["purchase_count"]]
            st.bar_chart(chart_df)

    st.divider()

    # --- 시간대별 이벤트 (분당 트래픽) ---
    st.subheader("시간대별 이벤트 (1분 단위)")
    if traffic_df.empty:
        st.info(
            "아직 집계된 트래픽 데이터가 없습니다.\n\n"
            "traffic_stats 는 Spark가 1분 윈도우를 확정한 뒤 저장하며, "
            "워터마크(10분) 때문에 이벤트 발생 후 10분 이상 지나야 나타납니다."
        )
    else:
        chart_df = traffic_df.copy()
        # 시각을 'MM-DD HH:MM' 문자열로 바꿔 축이 과도하게 쪼개지지 않게 한다.
        chart_df["시각"] = chart_df["window_start"].dt.strftime("%m-%d %H:%M")
        chart_df = chart_df.set_index("시각")
        st.line_chart(chart_df[["unique_users", "event_count"]])
        st.area_chart(chart_df[["revenue"]])


with tab_realtime:
    st.caption("이 탭은 10초마다 자동으로 갱신됩니다.")
    render_realtime_tab()

# ============================================================
# 배치 탭
# ============================================================
with tab_batch:
    st.caption("Airflow daily_etl DAG 이 매일 계산한 일별 지표입니다.")

    daily_df = get_daily_metrics(days=30)

    if daily_df.empty:
        st.info("아직 daily_metrics 데이터가 없습니다. Airflow에서 daily_etl DAG을 실행하세요.")
    else:
        daily_df = daily_df.sort_values("metric_date")

        latest = daily_df.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("최근 DAU", int(latest["dau"]))
        c2.metric("최근 전환율", f"{latest['conversion_rate']:.1%}")
        c3.metric("최근 매출", f"£{latest['revenue']:,.2f}")
        c4.metric("최근 이벤트 수", f"{int(latest['event_count']):,}")

        st.divider()

        # 차트용 데이터: metric_date를 'YYYY-MM-DD' 문자열로 바꿔 카테고리 축으로 만든다.
        # (DATE 타입 그대로 두면 Streamlit이 시간 축으로 해석해 하루를 시간 단위로 쪼갬)
        chart_df = daily_df.copy()
        chart_df["날짜"] = chart_df["metric_date"].astype(str)
        chart_df = chart_df.set_index("날짜")

        st.subheader("DAU 추이")
        st.line_chart(chart_df[["dau"]])

        st.subheader("전환율 추이")
        st.line_chart(chart_df[["conversion_rate"]])

        st.subheader("일별 매출")
        st.bar_chart(chart_df[["revenue"]])

        st.subheader("원본 데이터")
        st.dataframe(
            daily_df.rename(columns={
                "metric_date": "날짜", "dau": "DAU", "view_count": "조회수",
                "purchase_count": "구매수", "conversion_rate": "전환율",
                "revenue": "매출", "event_count": "총 이벤트",
            }).sort_values("날짜", ascending=False),
            width="stretch",
            hide_index=True,
        )