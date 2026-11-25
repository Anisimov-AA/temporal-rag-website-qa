import re

ASKS_VALUE = re.compile(r"\b(rate|rates|apr|apy|fee|fees|dividend|interest)\b", re.I)
HAS_VALUE = re.compile(r"\d\s?%|\$\s?\d|\bpercent\b|\b\d+\.\d+\b|\b(free|waived|none)\b|\bno\b[\w\s-]{0,20}\b(fee|fees|charge|charges|cost)\b", re.I)
LIMIT = re.compile(r"\b(up to|within|more than|no more than|exceed|by)\s+\d+(\.\d+)?\s?%", re.I)
ASKS_LINK = re.compile(r"\b(link|url|page|website|site)\b|\bwhere\b.*\b(find|see|look)\b", re.I)


def check_the_answer(question, reply):
    value = HAS_VALUE.search(LIMIT.sub("", reply.answer))
    if reply.known and ASKS_VALUE.search(question) and not ASKS_LINK.search(question) and not value:
        return reply.model_copy(update={"known": False})
    return reply
