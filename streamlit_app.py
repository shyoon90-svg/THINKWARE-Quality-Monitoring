import streamlit as st
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager, rc
import altair as alt

# --- 페이지 설정 ---
st.set_page_config(layout='wide', page_title='품질 관제 대시보드')

# --- 폰트 설정 ---
def setup_korean_font():
    font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    if not os.path.exists(font_path):
        os.system('sudo apt-get install -y fonts-nanum')
    font_manager.fontManager.addfont(font_path)
    prop = font_manager.FontProperties(fname=font_path)
    rc('font', family=prop.get_name())
    plt.rcParams['axes.unicode_minus'] = False

setup_korean_font()

# --- 유틸리티 함수 ---
def get_month_week(dt):
    first_day = dt.replace(day=1)
    dom = dt.day
    adjusted_dom = dom + first_day.weekday()
    week_num = int(np.ceil(adjusted_dom / 7.0))
    return f"{dt.month}월 {week_num}주차"

def calculate_advanced_risk_v2(df_target, model_name, df_main):
    if df_target.empty: return 0.0, "✅", "정상", 0.0
    shipment = df_main[df_main['모델명'] == model_name]['출하수량'].values
    shipment_val = shipment[0] if len(shipment) > 0 else 1000
    defect_rate = (len(df_target) / shipment_val) * 100
    rate_score = defect_rate * 50
    severity_weights = {'발화': 15, '연기': 15, '부풀음': 10, '파손': 8, '타는냄새': 10}
    symptom_score = df_target['불량증상'].map(severity_weights).fillna(1).sum() / len(df_target) * 10
    max_week = df_target['접수주차'].max()
    recent_count = len(df_target[df_target['접수주차'] == max_week])
    trend_factor = (recent_count + 1) * 2
    total_score = (rate_score + symptom_score) * trend_factor
    status_icon, status_text = "✅", "정상"
    if total_score > 100: status_icon, status_text = "🔴", "위험"
    elif total_score > 40: status_icon, status_text = "🟡", "주의"
    return float(total_score), status_icon, status_text, float(defect_rate)

# --- 데이터 로드 ---
@st.cache_data
def load_all_data():
    df = pd.read_csv('df_defective.csv')
    df['접수일'] = pd.to_datetime(df['접수일'])
    df['월주차'] = df['접수일'].apply(get_month_week)
    df['접수월'] = df['접수일'].dt.to_period('M').astype(str)
    df['모델명'] = df['모델명'].astype(str).str.strip().str.upper()
    df_main = pd.read_csv('MainModel.csv')
    df_main['모델명'] = df_main['모델명'].astype(str).str.strip().str.upper()
    return df, df_main

df_data, df_main = load_all_data()
current_week = df_data['접수주차'].max()
current_mw = df_data[df_data['접수주차'] == current_week]['월주차'].iloc[0]

# --- 사이드바 ---
st.sidebar.title("🛡️ 시장 품질 이슈 대시 보드")
menu = st.sidebar.selectbox("메뉴 선택", ["1. 주요 모델 현황", "2. 이슈 접수 트랜드", "3. 모델별 상세 분석"])

# --- [메뉴 1] 주요 모델 현황 ---
if "1." in menu:
    st.title("📋 주요 프로젝트 모델 현황 (Worst 순)")
    model_stats = []
    for model in df_main['모델명'].unique():
        m_df = df_data[df_data['모델명'] == model]
        score, icon, status, rate = calculate_advanced_risk_v2(m_df, model, df_main)
        w_count = len(m_df[m_df['접수주차'] == current_week])
        main_row = df_main[df_main['모델명'] == model].iloc[0]
        model_stats.append({'위험도': icon, '모델명': model, '상태': status, '출시년월': main_row['출시년월'], '출하수량': int(main_row['출하수량']), '불량률(%)': round(rate, 2), '금주불량': int(w_count), '전체불량': len(m_df), 'risk_score': score})

    summary_df = pd.DataFrame(model_stats).sort_values(by='risk_score', ascending=False)
    st.dataframe(summary_df.drop(columns=['risk_score']), use_container_width=True, hide_index=True)

    st.subheader("🔍 모델별 상세 리포트 (Detail View)")
    for _, row in summary_df.head(5).iterrows():
        with st.expander(f"{row['위험도']} {row['모델명']} 상세 분석 결과 - {row['상태']}"):
            m_df = df_data[df_data['모델명'] == row['모델명']]
            c1, c2, c3 = st.columns(3)
            c1.metric("전체 불량", f"{row['전체불량']} 건")
            c2.metric("금주 발생", f"{row['금주불량']} 건")
            c3.metric("불량률", f"{row['불량률(%)']}% ")

            g1, g2 = st.columns(2)
            with g1:
                st.write("**📅 주간별 발생 추이**")
                w_trend = m_df.groupby(['접수주차', '월주차']).size().reset_index(name='건수').sort_values('접수주차')
                st.line_chart(w_trend.set_index('월주차')['건수'])
            with g2:
                st.write("**📈 사용기간별 발생 추이**")
                u_trend = m_df.groupby('사용기간(개월)').size().reset_index(name='건수')
                st.line_chart(u_trend.set_index('사용기간(개월)'))

            st.divider()
            st.write("**🚫 불량 증상 TOP 5 및 발생 트렌드**")
            ts1, ts2 = st.columns([1, 2])
            top5_s = m_df['불량증상'].value_counts().head(5)
            with ts1: st.table(top5_s)
            with ts2:
                s_trend = m_df[m_df['불량증상'].isin(top5_s.index)].groupby(['월주차','접수주차','불량증상']).size().reset_index(name='건수')
                s_pivot = s_trend.sort_values('접수주차').pivot_table(index='월주차', columns='불량증상', values='건수', fill_value=0)
                st.line_chart(s_pivot)

# --- [메뉴 2] 이슈 접수 트랜드 ---
elif "2." in menu:
    st.title("🚨 리스크 통합 트렌드 분석 (TOP 50)")
    st.write("불량 건수가 가장 많은 모델부터 내림차순으로 표시합니다.")
    st.subheader("📊 전체 기간 누적 불량 건수 TOP 50 (좌측부터 내림차순)")

    # 막대 그래프용 데이터 (TOP 50)
    counts_df = df_data['모델명'].value_counts().sort_values(ascending=False).head(50).reset_index()
    counts_df.columns = ['모델명', '건수']

    chart = alt.Chart(counts_df).mark_bar().encode(
        x=alt.X('모델명:N', sort='-y', title='모델명'),
        y=alt.Y('건수:Q', title='접수 건수'),
        color=alt.Color('건수:Q', scale=alt.Scale(scheme='reds'), legend=None),
        tooltip=['모델명', '건수']
    ).properties(height=450)

    st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("📈 모델별 발생 추이 트렌드 (전체 모델 검색 가능)")

    # 선그래프용 모델 필터: 전체 모델 리스트 제공
    all_models_list = sorted(df_data['모델명'].unique().tolist())
    # 기본 선택값은 여전히 TOP 5 모델로 설정
    top5_default = counts_df['모델명'].head(5).tolist()
    selected_models = st.multiselect("분석할 모델을 선택하세요 (전체 리스트)", options=all_models_list, default=top5_default)

    if selected_models:
        t_trend = df_data[df_data['모델명'].isin(selected_models)].groupby(['접수월', '모델명']).size().reset_index(name='건수')
        t_pivot = t_trend.pivot_table(index='접수월', columns='모델명', values='건수', fill_value=0)
        st.line_chart(t_pivot, use_container_width=True)
    else:
        st.warning("모델을 최소 하나 이상 선택해주세요.")

# --- [메뉴 3] 모델별 상세 분석 ---
elif "3." in menu:
    st.title("🔬 모델별 상세 분석")
    model_options = ["전체 모델"] + sorted(df_data['모델명'].unique().tolist())
    sel_model = st.sidebar.selectbox("모델 선택", model_options)

    if sel_model == "전체 모델":
        df_target = df_data
        title_prefix = "전체 모델"
    else:
        df_target = df_data[df_data['모델명'] == sel_model]
        title_prefix = sel_model

    col_w, col_u = st.columns(2)
    with col_w:
        st.write(f"**📅 {title_prefix} 주간별 발생 추이**")
        wt = df_target.groupby(['접수주차', '월주차']).size().reset_index(name='건수').sort_values('접수주차')
        st.line_chart(wt.set_index('월주차')['건수'])
    with col_u:
        st.write(f"**📈 {title_prefix} 사용기간별 발생 추이**")
        ut = df_target.groupby('사용기간(개월)').size().reset_index(name='건수')
        st.line_chart(ut.set_index('사용기간(개월)'))

    st.divider()
    st.write("**📊 상세 분석 데이터 (TOP 5)**")
    st1, st2 = st.columns(2)
    with st1:
        st.write("**🚫 불량 증상 TOP 5**")
        st.table(df_target['불량증상'].value_counts().head(5))
    with st2:
        st.write("**🛠️ 엔지니어 원인 TOP 5**")
        st.table(df_target['엔지니어_확인'].value_counts().head(5))
