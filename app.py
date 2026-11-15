import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.model import ROOT, load_config, compare, best, sensitivity, evaluate

st.set_page_config(page_title='Recycling Policy Lab', layout='wide')
st.title('Recycling Policy Lab')
st.warning('정책 실험 결과는 모두 합성·가정(D등급)입니다. 실제 한국 정책 효과 추정이 아닙니다.')
config = load_config()
config['common']['time_value'] = st.sidebar.slider('가정: 시간가치(원/시간)', 0, 30000, 10000, 1000)
target = st.sidebar.slider('가정: 최소 최종 재활용률(%) — 현행 이상 적용', 0, 100, 0)/100
table = compare(config, target)
st.metric('제약 충족 최소비용 대안', best(table) or '충족 대안 없음')
st.caption('등록된 유한 시나리오 중 선택합니다. C는 안전·법규 미검증 탐색안으로 추천에서 제외합니다.')
st.dataframe(table, hide_index=True)
st.download_button('비교 결과 CSV', table.to_csv(index=False).encode('utf-8-sig'), 'scenarios.csv', 'text/csv')
costs = table.melt(id_vars=['id'], value_vars=['household','collection','sorting','reprocessing','disposal','producer_real'], var_name='cost', value_name='KRW/year')
st.plotly_chart(px.bar(costs, x='id', y='KRW/year', color='cost'), width='stretch')
st.plotly_chart(px.scatter(table, x='final_rate', y='social_cost', color='id', symbol='feasible'), width='stretch')
selected = st.selectbox('물질수지 시나리오', table.id)
scenario = next(s for s in config['scenarios'] if s['id'] == selected)
_, flows = evaluate(config, scenario)
st.dataframe(flows, hide_index=True)
st.plotly_chart(go.Figure(go.Sankey(node=dict(label=['발생','수거','선별','재생원료','미수거','선별잔재','공정손실']), link=dict(source=[0,0,1,1,2,2], target=[1,4,2,5,3,6], value=[flows.collected.sum(),flows.uncollected.sum(),flows.sorted.sum(),flows.sorting_loss.sum(),flows.recycled.sum(),flows.processing_loss.sum()]))), width='stretch')
st.subheader('민감도: 기준값의 0.5 / 1 / 1.5배')
st.plotly_chart(px.line(sensitivity(config), x='factor', y='social_cost', color='id', facet_col='parameter'), width='stretch')
st.subheader('공식 통계 현황 — 시뮬레이션 입력과 별도')
trend = pd.read_csv(ROOT / 'data/processed/korea_waste_trend.csv')
st.plotly_chart(px.line(trend, x='reference_year', y='value', markers=True, labels={'value':'생활계폐기물 발생량(t/일)'}), width='stretch')
st.caption('생활계 전체 통계는 가정의 4개 재활용 품목과 범위가 달라 기준선 보정에 사용하지 않습니다.')
st.dataframe(pd.read_csv(ROOT / 'data/sources.csv'), hide_index=True)
