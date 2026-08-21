import os
from langchain_community.utilities import SQLDatabase
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage


class Text2SQLEngine:
    def __init__(self):
        """Text2SQL 엔진 초기화"""
        # Supabase 데이터베이스 연결
        self.db = SQLDatabase.from_uri(os.getenv("SUPABASE_DB_URL"))

        # LLM 초기화
        self.llm = init_chat_model("gpt-5.4-mini")

        # 데이터베이스 스키마 정보 캐싱
        self.schema_info = self.db.get_table_info()

    def generate_sql(self, question: str, feedback: str = None) -> str:
        """
        자연어 질문을 SQL 쿼리로 변환

        Args:
            question: 사용자의 자연어 질문
            feedback: 이전 시도의 오류 피드백 (재시도 시)

        Returns:
            생성된 SQL 쿼리
        """
        system_prompt = f"""
당신은 PostgreSQL 전문가입니다.
사용자의 질문을 정확한 SQL 쿼리로 변환하세요.

<database_schema>
{self.schema_info}
</database_schema>

<table_descriptions>
- population: 전국 시도별 인구 통계. 지역 컬럼은 "행정구역별(읍면동)", 연도별 인구 컬럼은 "2018"부터 "2022"까지입니다.
- "GRDP": 전국 시도·시군구별 지역내총생산 통계. 지역 컬럼은 "행정구역별(1)", 세부 지역 컬럼은 "행정구역별(2)"입니다.
- "GRDP"의 "2018"부터 "2022"는 당해년가격(명목), "2018_1"부터 "2022_1"은 기준년가격(실질) 값입니다.
- "GRDP"에서 시도 합계를 조회할 때는 "행정구역별(2)" = '소계' 조건을 사용합니다.
</table_descriptions>

<rules>
- PostgreSQL 문법을 사용하세요
- SELECT 쿼리만 생성하세요 (INSERT, UPDATE, DELETE 금지)
- 결과는 최대 10개로 제한하세요 (LIMIT 10)
- SQL 쿼리만 반환하고, 설명은 포함하지 마세요
- 코드 블록(```)이나 'sql' 키워드 없이 순수 쿼리만 반환하세요
- NULL 값을 주의해서 처리하세요
- 존재하지 않는 컬럼을 사용하지 마세요
- JOIN이 필요한 경우 적절히 사용하세요
- 한글 및 숫자로 된 테이블명과 컬럼명은 반드시 큰따옴표로 감싸세요
- 값이 '-'인 행은 계산에서 제외하고, 계산할 값은 ::numeric으로 변환하세요
- 인구와 GRDP를 결합할 때 동일한 연도를 사용하고 지역명을 기준으로 JOIN하세요
- 증감률 계산 시 NULLIF를 사용하여 0으로 나누는 오류를 방지하세요
- 세미콜론(;)으로 쿼리를 종료하세요
</rules>
"""

        if feedback:
            system_prompt += f"\n\n이전 시도의 오류:\n{feedback}\n\n위 오류를 고려하여 쿼리를 수정하세요."

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question)
        ]

        response = self.llm.invoke(messages)
        sql_query = response.content.strip()

        # 코드 블록 제거
        if sql_query.startswith("```"):
            lines = sql_query.split("\n")
            sql_query = "\n".join(lines[1:-1]) if len(lines) > 2 else sql_query
            sql_query = sql_query.replace("sql", "").strip()

        return sql_query

    def execute_sql(self, sql_query: str) -> tuple[str, str]:
        """
        SQL 쿼리 실행

        Args:
            sql_query: 실행할 SQL 쿼리

        Returns:
            (결과 문자열, 오류 메시지) 튜플
        """
        try:
            result = self.db.run(sql_query)
            return result, None
        except Exception as e:
            error_msg = str(e)
            return None, error_msg

    def query(self, question: str, previous_error: str = None) -> dict:
        """
        질문에 대한 SQL 생성 및 실행

        Args:
            question: 사용자 질문
            previous_error: 이전 시도의 오류 (재시도 시)

        Returns:
            결과 딕셔너리 (sql_query, result, error)
        """
        # SQL 생성
        sql_query = self.generate_sql(question, feedback=previous_error)

        # SQL 실행
        result, error = self.execute_sql(sql_query)

        return {
            "sql_query": sql_query,
            "result": result,
            "error": error
        }

    def is_empty_result(self, result: str) -> bool:
        """
        결과가 비어있는지 확인

        Args:
            result: SQL 실행 결과

        Returns:
            결과가 비어있으면 True
        """
        if not result:
            return True

        # 빈 결과 패턴 확인
        empty_patterns = ["[]", "()", "no rows", "0 rows"]
        result_lower = result.lower().strip()

        return any(pattern in result_lower for pattern in empty_patterns)


def get_text2sql_engine() -> Text2SQLEngine:
    """Text2SQL 엔진 인스턴스 반환"""
    return Text2SQLEngine()
