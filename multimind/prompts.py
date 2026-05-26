REFINEMENT_TEMPLATE = """당신은 멀티 LLM 오케스트레이터의 Head LLM입니다.
사용자의 원래 프롬프트를 받아서, 각 Worker LLM에게 최적화된 세부 프롬프트를 생성해주세요.

원래 프롬프트:
{user_prompt}

다음 Worker LLM들이 이 작업을 처리합니다: {worker_list}

각 LLM의 특성에 맞게 프롬프트를 조정하되, 핵심 목표는 동일하게 유지하세요.
반드시 아래 JSON 형식으로만 응답하세요 (JSON 이외의 텍스트 금지):

{json_template}"""

SYNTHESIS_TEMPLATE = """당신은 멀티 LLM 오케스트레이터의 Head LLM입니다.
다음은 여러 Worker LLM들의 응답입니다. 이를 종합하여 최고의 최종 답변을 작성해주세요.

원래 사용자 프롬프트:
{user_prompt}

Worker LLM 응답들:
{worker_responses}

위 응답들의 장점을 결합하고, 불일치하는 부분은 가장 정확한 정보를 선택하여,
완결성 있는 최종 답변을 한국어로 작성해주세요."""
