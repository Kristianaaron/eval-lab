You are given a structured service log as an attachment (one event per line: timestamp, level, service, node, code, latency_ms, request id, message). Answer the questions below using only the attached log.

q1: Between 2026-03-14T01:51:00Z (inclusive) and 2026-03-14T03:48:00Z (exclusive), which service has the most lines with level=ERROR? (If tied, the alphabetically last service name.)
q2: How many level=ERROR lines does that service have in the same window? Answer with an integer.
q3: Over the entire log, what is the highest latency_ms value on a level=WARN line from node=n12? Answer with an integer.

Reply with a single JSON object and nothing else, e.g. {"q1": "service-name", "q2": 12, "q3": 345}.
