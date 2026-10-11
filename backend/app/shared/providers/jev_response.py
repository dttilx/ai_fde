"""Validate official typed answers before normalizing them into routing hints."""

import math

from app.shared.providers.http_gateway import token_usage
from app.shared.providers.protocols import ProviderFailure


def number(value, low=0, high=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ProviderFailure("JEV_RESPONSE_INVALID")
    return value


def distribution(answer, keys):
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(keys):
        raise ProviderFailure("JEV_RESPONSE_INVALID")
    values = {k: number(v) for k, v in probabilities.items()}
    if abs(sum(values.values()) - 1) > 1e-6:
        raise ProviderFailure("JEV_RESPONSE_INVALID")
    number(answer.get("confidence"))
    return values


def parse_answers(body: dict, projection: dict):
    if body.get("model") != projection["model"]:
        raise ProviderFailure("MODEL_OR_MODE_MISMATCH")
    answers = body.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(projection["questions"]):
        raise ProviderFailure("JEV_RESPONSE_INVALID")
    for key, question in projection["questions"].items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ProviderFailure("JEV_RESPONSE_INVALID")
        if question["type"] == "noul":
            number(answer.get("noul"))
        elif question["type"] == "choice":
            probs = distribution(answer, question["criteria"])
            choice = answer.get("choice")
            if choice not in probs or probs[choice] < max(probs.values()):
                raise ProviderFailure("JEV_RESPONSE_INVALID")
        elif question["type"] == "score":
            criteria = question["criteria"]
            keys = [str(i) for i in range(len(criteria))]
            probs = distribution(answer, keys)
            legend = answer.get("legend")
            if legend != dict(zip(keys, criteria, strict=True)):
                raise ProviderFailure("JEV_RESPONSE_INVALID")
            score = number(answer.get("score"), high=len(criteria) - 1)
            expected = sum(int(k) * v for k, v in probs.items())
            if abs(score - expected) > 1e-6:
                raise ProviderFailure("JEV_RESPONSE_INVALID")
    return answers, token_usage(body)
