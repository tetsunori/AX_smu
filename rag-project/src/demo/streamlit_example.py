import os
import sys
from pathlib import Path

# src 디렉토리를 Python 경로에 추가
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

import streamlit as st
from dotenv import load_dotenv
from ai import create_graph

# 환경 변수 로드
load_dotenv()

graph = create_graph()

def init_session_state():
    """세션 상태 초기화"""
    if "messages" not in st.session_state:
        st.session_state.messages = []


def display_message(role: str, content: str, workflow_info: dict = None):
    """메시지 표시"""
    with st.chat_message(role):
        st.markdown(content)

        # 워크플로 정보가 있으면 표시 (assistant 메시지에만)
        if role == "assistant" and workflow_info:
            display_workflow_info(workflow_info)


def display_workflow_info(result: dict):
    """워크플로 정보 표시"""
    with st.expander("🔍 워크플로 정보"):
        col1, col2 = st.columns(2)

        with col1:
            st.metric("의도", result.get("intent", "N/A"))

            if result.get("retry_count"):
                st.metric("재시도 횟수", result["retry_count"])

        with col2:
            if result.get("vector_results"):
                st.metric("검색된 문서", len(result["vector_results"]))

            if result.get("db_results"):
                st.info("DB 검색 수행됨")

        # 벡터 검색 결과 상세 표시
        if result.get("vector_results"):
            st.markdown("#### 📄 검색된 문서")
            for i, doc in enumerate(result["vector_results"], 1):
                with st.expander(f"문서 {i}: {doc.metadata.get('source', '알 수 없음')}"):
                    # 메타데이터 표시
                    meta_cols = st.columns(3)
                    with meta_cols[0]:
                        st.caption(f"📖 페이지: {doc.metadata.get('page', 'N/A')}")
                    with meta_cols[1]:
                        if doc.metadata.get('category'):
                            st.caption(f"🏷️ 카테고리: {doc.metadata.get('category')}")
                    with meta_cols[2]:
                        if doc.metadata.get('score'):
                            st.caption(f"⭐ 점수: {doc.metadata.get('score', 0):.3f}")

                    # 문서 내용 표시
                    st.markdown("**내용:**")
                    st.text(doc.page_content[:500] + ("..." if len(doc.page_content) > 500 else ""))

        # SQL 쿼리 표시
        if result.get("sql_query"):
            st.code(result["sql_query"], language="sql")

        # 재작성된 쿼리 표시
        if result.get("rewritten_query"):
            st.info(f"재작성된 쿼리: {result['rewritten_query']}")

        # 오류 표시
        if result.get("error"):
            st.error(f"오류: {result['error']}")


def main():
    """메인 함수"""
    st.set_page_config(
        page_title="인구·GRDP 통계 AI",
        page_icon="📊",
        layout="wide"
    )

    st.title("📊 전국 인구·GRDP 통계 AI")
    st.markdown("---")

    # 사이드바 - 환경 변수 확인
    with st.sidebar:
        st.header("⚙️ 설정 확인")

        required_vars = {
            "OPENAI_API_KEY": "OpenAI API",
            "SUPABASE_DB_URL": "Supabase DB"
        }

        for var, name in required_vars.items():
            if os.getenv(var):
                st.success(f"✓ {name}")
            else:
                st.error(f"✗ {name}")

        st.markdown("---")
        st.header("📖 사용 방법")
        st.markdown("""
        **일반 질문:**
        - "안녕하세요"
        - "고마워"

        **통계 검색:**
        - "2022년 인구가 가장 많은 지역 5곳은?"
        - "2022년 지역별 1인당 명목 GRDP를 알려줘"
        - "경기도와 충남의 인구와 GRDP를 비교해줘"
        - "2021년에서 2022년 사이 인구와 실질 GRDP 증감률을 비교해줘"
        """)

        if st.button("대화 초기화", type="secondary"):
            st.session_state.messages = []
            st.rerun()

    # 세션 상태 초기화
    init_session_state()

    # 이전 메시지 표시
    for message in st.session_state.messages:
        display_message(
            message["role"],
            message["content"],
            message.get("workflow_info")  # 워크플로 정보가 있으면 전달
        )

    # 사용자 입력
    if prompt := st.chat_input("질문을 입력하세요..."):
        # 사용자 메시지 표시 및 저장
        display_message("user", prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 워크플로 실행
        with st.chat_message("assistant"):
            with st.spinner("생각 중..."):
                try:
                    # 그래프 실행
                    result = graph.invoke({
                        "messages": [{"role": "user", "content": prompt}]
                    })

                    # 답변 표시 (messages의 마지막 AIMessage에서 추출)
                    messages = result.get("messages", [])
                    if messages:
                        # 마지막 메시지에서 content 추출
                        last_message = messages[-1]
                        answer = last_message.content if hasattr(last_message, 'content') else str(last_message)
                    else:
                        answer = "죄송합니다. 답변을 생성할 수 없습니다."

                    st.markdown(answer)

                    # 워크플로 정보 표시
                    display_workflow_info(result)

                    # 어시스턴트 메시지와 워크플로 정보 함께 저장
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "workflow_info": result  # 워크플로 정보 저장
                    })

                except Exception as e:
                    error_msg = f"오류가 발생했습니다: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })


if __name__ == "__main__":
    main()
