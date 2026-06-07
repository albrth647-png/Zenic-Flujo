"""Workflow Determinista — CRM Models"""

STAGES = ["new", "contacted", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]

STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}
