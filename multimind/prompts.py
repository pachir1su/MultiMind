REFINEMENT_TEMPLATE = """다음 프롬프트를 각 Worker LLM에 맞게 최적화하세요.
설명·인사·사족 없이 JSON만 출력하세요.

프롬프트: {user_prompt}
Workers: {worker_list}

정확히 이 형식으로 출력 (JSON 외 텍스트 절대 금지):
{json_template}"""

SYNTHESIS_TEMPLATE = """당신은 멀티 LLM 오케스트레이터의 Head LLM입니다.
다음은 여러 Worker LLM들의 응답입니다. 이를 종합하여 최고의 최종 답변을 작성해주세요.

원래 사용자 프롬프트:
{user_prompt}

Worker LLM 응답들:
{worker_responses}

위 응답들의 장점을 결합하고, 불일치하는 부분은 가장 정확한 정보를 선택하여,
완결성 있는 최종 답변을 한국어로 작성해주세요."""
